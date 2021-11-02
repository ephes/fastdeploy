#!/usr/bin/env python

import asyncio
import json
import os
import subprocess
import sys

from datetime import timedelta
from typing import Any
from urllib.parse import urljoin

import httpx

from pydantic import BaseSettings, Field

from .auth import create_access_token
from .config import settings
from .models import Deployment, Service


async def run_deploy(environment):  # pragma no cover
    command = [sys.executable, "-m", "app.tasks"]  # make relative imports work
    subprocess.Popen(command, start_new_session=True, env=environment)


def get_deploy_environment(service: Service, deployment: Deployment):
    data = {
        "type": "deployment",
        "deployment": deployment.id,
    }
    access_token = create_access_token(data=data, expires_delta=timedelta(minutes=30))
    environment = {
        "ACCESS_TOKEN": access_token,
        "DEPLOY_SCRIPT": service.deploy,
        "COLLECT_SCRIPT": service.collect,
        "STEPS_URL": settings.steps_url,
        "SSH_AUTH_SOCK": os.environ["SSH_AUTH_SOCK"],
    }
    return environment


class DeployTask(BaseSettings):
    deploy_script: str = Field(..., env="DEPLOY_SCRIPT")
    collect_script: str = Field(..., env="COllECT_SCRIPT")
    access_token: str = Field(..., env="ACCESS_TOKEN")
    steps_url: str = Field(..., env="STEPS_URL")
    step_by_name: dict = {}
    attempts: int = 3
    sleep_on_fail: float = 3.0
    client: Any = None

    @property
    def headers(self):
        return {"authorization": f"Bearer {self.access_token}"}

    async def send_step(self, method, step_url, step):
        for attempt in range(self.attempts):
            try:
                await method(step_url, json=step)
                break
            except httpx.ConnectError:
                await asyncio.sleep(self.sleep_on_fail)

    async def process_deploy_step(self, step):
        if (collected_step := self.step_by_name.get(step["name"])) is not None:
            # update collected step
            step_url = urljoin(self.steps_url, str(collected_step["id"]))
            await self.send_step(self.client.put, step_url, step)
        else:
            # post new step
            await self.send_step(self.client.post, self.steps_url, step)

    async def post_collected_steps(self, steps):
        for step in steps:
            r = await self.client.post(self.steps_url, json=step)
            self.step_by_name[step["name"]] = r.json()

    async def collect_steps(self):
        command = str(settings.deploy_root / self.collect_script)
        proc = subprocess.run([command], check=False, text=True, stdout=subprocess.PIPE)
        steps = [step for step in json.loads(proc.stdout) if "name" in step]
        await self.post_collected_steps(steps)

    async def deploy_steps(self):
        command = str(settings.deploy_root / self.deploy_script)
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        while True:
            data = await proc.stdout.readline()
            if len(data) == 0:
                break

            decoded = data.decode("UTF-8")
            try:
                step = json.loads(decoded)
                if len(step.get("name", "")) > 0:
                    await self.process_deploy_step(step)
            except json.decoder.JSONDecodeError:
                pass

    async def run_deploy(self):
        await self.collect_steps()
        await self.deploy_steps()


async def run_deploy_task():  # pragma: no cover
    deploy_task = DeployTask()
    async with httpx.AsyncClient(headers=deploy_task.headers) as client:
        deploy_task.client = client
        await deploy_task.run_deploy()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run_deploy_task())
