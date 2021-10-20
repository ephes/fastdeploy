#!/usr/bin/env python

import asyncio
import json
import subprocess
import sys

from datetime import timedelta

import httpx

from pydantic import BaseSettings, Field

from .auth import create_access_token
from .config import settings


async def run_deploy(user):
    print("running deployment")
    access_token = create_access_token(data={"sub": user.name}, expires_delta=timedelta(minutes=30))
    environment = {"ACCESS_TOKEN": access_token, "DEPLOY_SCRIPT": "create_lines.py", "EVENT_URL": settings.event_url}
    command = [sys.executable, "-m", "app.tasks"]  # make relative imports work
    subprocess.Popen(command, start_new_session=True, env=environment)


class DeployTask(BaseSettings):
    deploy_script: str = Field(..., env="DEPLOY_SCRIPT")
    access_token: str = Field(..., env="ACCESS_TOKEN")
    event_url: str = Field(..., env="EVENT_URL")

    async def process_deploy_event(self, event):
        print("process..")
        headers = {"authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient() as client:
            for attempt in range(3):
                try:
                    r = await client.post(self.event_url, json=event, headers=headers)
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(3)
            print("response: ", r.status_code, r.json())

    async def run_deploy(self):
        command = f"{sys.executable} {settings.deploy_root / self.deploy_script}"
        print("command: ", command)
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        while True:
            data = await proc.stdout.readline()
            print("read data: ", data)
            if len(data) == 0:
                break

            decoded = data.decode("UTF-8")
            try:
                message = json.loads(decoded)
                print("data: ", data)
                await self.process_deploy_event(message)
            except json.decoder.JSONDecodeError:
                print("could not json decode: ", decoded)
                pass


if __name__ == "__main__":
    asyncio.run(DeployTask().run_deploy())