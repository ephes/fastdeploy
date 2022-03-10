#!/usr/bin/env python

import asyncio
import json
import os
import subprocess
import sys

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from pydantic import BaseModel, BaseSettings, Field

from .auth import create_access_token
from .config import settings
from .domain.model import Deployment, Step


def run_deploy(environment):  # pragma no cover
    command = [sys.executable, "-m", "deploy.tasks"]  # make relative imports work
    subprocess.Popen(command, start_new_session=True, env=environment)


class DeploymentContext(BaseModel):
    """
    Pass some context for a deployment. For example when deploying a new
    podcast, we need to pass the domain name and the port of the application
    server.
    """

    env: dict = {}


def get_deploy_environment(deployment: Deployment, deploy_script: str) -> dict:
    payload = {
        "type": "deployment",
        "deployment": deployment.id,
    }
    access_token = create_access_token(payload=payload, expires_delta=timedelta(minutes=30))
    environment = {
        "ACCESS_TOKEN": access_token,
        "DEPLOY_SCRIPT": deploy_script,
        "STEPS_URL": settings.steps_url,
        "DEPLOYMENT_FINISH_URL": settings.deployment_finish_url,
        "CONTEXT": DeploymentContext(**deployment.context).json(),
        "PATH_FOR_DEPLOY": settings.path_for_deploy,
    }
    if ssh_auth_sock := os.environ.get("SSH_AUTH_SOCK"):
        environment["SSH_AUTH_SOCK"] = ssh_auth_sock
    return environment


class DeployTask(BaseSettings):
    """
    Run a complete deployment for a service:
      - get deploy token and steps via environment variables
      - run deploy script in a new process reading json from stdout
      - post finished steps back to application server
    """

    deploy_script: str = Field(..., env="DEPLOY_SCRIPT")
    access_token: str = Field(..., env="ACCESS_TOKEN")
    steps_url: str = Field(..., env="STEPS_URL")
    deployment_finish_url: str = Field(..., env="DEPLOYMENT_FINISH_URL")
    context: DeploymentContext = Field(..., env="CONTEXT")
    path_for_deploy: str = Field(..., env="PATH_FOR_DEPLOY")
    attempts: int = 3
    sleep_on_fail: float = 3.0
    client: Any = None

    @property
    def headers(self):
        return {"authorization": f"Bearer {self.access_token}"}

    async def send_step(self, step_url, step):
        for _ in range(self.attempts):
            try:
                r = await self.client.post(step_url, json=json.loads(step.json()))
                r.raise_for_status()
                break
            except httpx.HTTPStatusError:
                await asyncio.sleep(self.sleep_on_fail)

    async def finish_deployment(self) -> None:
        r = await self.client.put(self.deployment_finish_url)
        r.raise_for_status()

    async def finish_step(self, step_result):
        step = Step(**step_result)
        step.finished = datetime.now(timezone.utc)
        if len(step_result.get("error_message", "")) > 0:
            step.message = step_result["error_message"]
        await self.send_step(self.steps_url, step)

    async def deploy_steps(self):
        sudo_command = f"sudo -u {settings.sudo_user}"
        deploy_command = str(settings.services_root / self.deploy_script)
        command = f"{sudo_command} --preserve-env {deploy_command}"
        env = os.environ.copy()
        env["PATH"] = self.path_for_deploy
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        while True:
            started = datetime.now(timezone.utc)
            data = await proc.stdout.readline()  # type: ignore
            # FIXME log returned data properly
            # print("from deploy script:", data.decode("utf-8"))
            if len(data) == 0:
                break

            decoded = data.decode("UTF-8")
            try:
                step_result = json.loads(decoded)
            except json.decoder.JSONDecodeError:
                continue
            # if name is None there's something wrong -> skip
            result_name = step_result.get("name")
            if result_name is None:
                # should not happen
                print("step result not posted: ", step_result)
                continue
            step_result["started"] = started
            await self.finish_step(step_result)

    async def run_deploy(self):
        try:
            await self.deploy_steps()
        finally:
            await self.finish_deployment()


async def run_deploy_task():  # pragma: no cover
    deploy_task = DeployTask()  # type: ignore
    async with httpx.AsyncClient(headers=deploy_task.headers) as client:
        deploy_task.client = client
        await deploy_task.run_deploy()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run_deploy_task())
