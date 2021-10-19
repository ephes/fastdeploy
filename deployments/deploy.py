#!/usr/bin/env python

import asyncio
import json

from pathlib import Path

from pydantic import BaseSettings, Field


class TaskSettings(BaseSettings):
    deploy_script: str = Field(..., env="DEPLOY_SCRIPT")
    access_token: str = Field(..., env="ACCESS_TOKEN")
    deploy_directory: Path = Path(__file__).resolve(strict=True).parent


async def run_deploy():
    settings = TaskSettings()
    proc = await asyncio.create_subprocess_shell(
        str(settings.deploy_directory / settings.deploy_script),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    while True:
        data = await proc.stdout.readline()
        if len(data) == 0:
            break

        decoded = data.decode("UTF-8")
        try:
            data = json.loads(decoded)
            print("data: ", data)
        except json.decoder.JSONDecodeError:
            print("could not json decode: ", decoded)
            pass


if __name__ == "__main__":
    asyncio.run(run_deploy())
