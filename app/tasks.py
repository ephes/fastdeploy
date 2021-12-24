#!/usr/bin/env python

import asyncio
import json
import os
import subprocess
import sys

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import httpx

from pydantic import BaseSettings, Field

from .auth import create_access_token
from .config import settings
from .models import Deployment, Step


async def run_deploy(environment):  # pragma no cover
    command = [sys.executable, "-m", "app.tasks"]  # make relative imports work
    subprocess.Popen(command, start_new_session=True, env=environment)


def get_deploy_environment(deployment: Deployment, steps: list[Step], deploy_script: str) -> dict:
    data = {
        "type": "deployment",
        "deployment": deployment.id,
    }
    access_token = create_access_token(data=data, expires_delta=timedelta(minutes=30))
    environment = {
        "ACCESS_TOKEN": access_token,
        "DEPLOY_SCRIPT": deploy_script,
        "STEPS_URL": settings.steps_url,
        "DEPLOYMENT_FINISH_URL": settings.deployment_finish_url,
    }
    if ssh_auth_sock := os.environ.get("SSH_AUTH_SOCK"):
        environment["SSH_AUTH_SOCK"] = ssh_auth_sock
    return environment


class DeployTask(BaseSettings):
    """
    Run a complete deployment for a service:
      - get deploy token and steps via environment variables
      - run deploy script in a new process reading json from stdout
      - update/post steps in the database
    """

    deploy_script: str = Field(..., env="DEPLOY_SCRIPT")
    steps: list[Step] = Field([], env="STEPS")
    access_token: str = Field(..., env="ACCESS_TOKEN")
    steps_url: str = Field(..., env="STEPS_URL")
    deployment_finish_url: str = Field(..., env="DEPLOYMENT_FINISH_URL")
    current_step_index: int = 0
    attempts: int = 3
    sleep_on_fail: float = 3.0
    client: Any = None

    @property
    def headers(self):
        return {"authorization": f"Bearer {self.access_token}"}

    async def send_step(self, method, step_url, step):
        for _ in range(self.attempts):
            try:
                r = await method(step_url, json=json.loads(step.json()))
                r.raise_for_status()
                break
            except httpx.HTTPStatusError:
                await asyncio.sleep(self.sleep_on_fail)

    async def put_step(self, step):
        step_url = urljoin(self.steps_url, str(step.id))
        await self.send_step(self.client.put, step_url, step)

    async def finish_deployment(self) -> None:
        r = await self.client.put(self.deployment_finish_url)
        r.raise_for_status()

    @property
    def has_more_steps(self):
        # True if there are still unprocessed steps
        return self.current_step_index < len(self.steps)

    @property
    def current_step(self):
        if self.has_more_steps:
            return self.steps[self.current_step_index]

    async def start_step(self, step):
        step.started = datetime.utcnow()
        step.state = "running"
        await self.put_step(step)

    async def finish_step(self, current_step, step_result):
        step = Step(**step_result)
        step.finished = datetime.utcnow()
        if len(step_result.get("error_message", "")) > 0:
            step.message = step_result["error_message"]
        if current_step is None:
            await self.send_step(self.client.post, self.steps_url, step)
        else:
            step.id = current_step.id  # step from stdout deploy has no id -> take it from current step
            step.started = current_step.started
            await self.put_step(step)
            self.current_step_index += 1
            if self.current_step is not None and step.state == "success":
                await self.start_step(self.current_step)

    async def deploy_steps(self):
        sudo_command = f"sudo -u {settings.sudo_user}"
        deploy_command = str(settings.services_root / self.deploy_script)
        command = f"{sudo_command} {deploy_command}"
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        if self.current_step is not None:
            await self.start_step(self.current_step)
        while True:
            data = await proc.stdout.readline()  # type: ignore
            if len(data) == 0:
                break

            decoded = data.decode("UTF-8")
            try:
                step_result = json.loads(decoded)
            except json.decoder.JSONDecodeError:
                continue
            # if name is None there's no way to find the
            # corresponding step in the database -> skip
            result_name = step_result.get("name")
            if result_name is None:
                # should not happen
                print("step result not put/posted: ", step_result)
                continue
            # On the happy path, the if condition below will be true
            # and the current step will be marked as finished. Post a
            # new step in all other cases.
            current_step = None
            if self.current_step is not None and result_name == self.current_step.name:
                current_step = self.current_step
            await self.finish_step(current_step, step_result)

    async def run_deploy(self):
        try:
            await self.deploy_steps()
        finally:
            await self.finish_deployment()


async def run_deploy_task():  # pragma: no cover
    deploy_task = DeployTask()
    async with httpx.AsyncClient(headers=deploy_task.headers) as client:
        deploy_task.client = client
        await deploy_task.run_deploy()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run_deploy_task())
