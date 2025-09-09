#!/usr/bin/env python

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from .auth import create_access_token
from .config import settings
from .domain.model import Deployment, Step
from .secure_config import SecureConfig, get_config_from_env


def run_deploy(environment):  # pragma no cover
    """Run deployment in a subprocess with secure configuration."""
    # Create secure configuration file
    secure_config = SecureConfig()

    # Extract deployment ID from environment or generate one
    deployment_id = environment.get("DEPLOYMENT_ID", "deploy_" + str(datetime.now(timezone.utc).timestamp()))

    # Create secure config file with sensitive data
    config_path = secure_config.create_deployment_config(
        deployment_id=deployment_id,
        access_token=environment.get("ACCESS_TOKEN", ""),
        deploy_script=environment.get("DEPLOY_SCRIPT", ""),
        steps_url=environment.get("STEPS_URL", ""),
        deployment_finish_url=environment.get("DEPLOYMENT_FINISH_URL", ""),
        context=json.loads(environment.get("CONTEXT", "{}")),
        path_for_deploy=environment.get("PATH_FOR_DEPLOY", ""),
        ssh_auth_sock=environment.get("SSH_AUTH_SOCK"),
    )

    # Create minimal environment with only config file path
    clean_env = {
        "DEPLOY_CONFIG_FILE": str(config_path),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    }

    command = [sys.executable, "-m", "deploy.tasks"]  # make relative imports work
    subprocess.Popen(command, start_new_session=True, env=clean_env)


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
        "CONTEXT": DeploymentContext(**deployment.context).model_dump_json(),
        "PATH_FOR_DEPLOY": settings.path_for_deploy,
    }
    if ssh_auth_sock := os.environ.get("SSH_AUTH_SOCK"):
        environment["SSH_AUTH_SOCK"] = ssh_auth_sock
    return environment


MAX_ASYNCIO_STDOUT_SIZE = 1024 * 1024 * 10  # 10 MiB output -> raise exception on bigger output
MAX_STEP_MESSAGE_SIZE = 4096


class DeployTask(BaseSettings):
    """
    Run a complete deployment for a service:
      - get deploy token and steps via environment variables
      - run deploy script in a new process reading json from stdout
      - post finished steps back to application server
    """

    model_config = SettingsConfigDict(env_file=None)

    deploy_script: str
    access_token: str
    steps_url: str
    deployment_finish_url: str
    context: DeploymentContext
    path_for_deploy: str
    attempts: int = 3
    sleep_on_fail: float = 3.0
    client: Any = None

    @property
    def headers(self):
        return {"authorization": f"Bearer {self.access_token}"}

    @staticmethod
    def limit_message_size(step):
        if len(step.message) > MAX_STEP_MESSAGE_SIZE:
            step.message = step.message[:MAX_STEP_MESSAGE_SIZE]
        return step

    async def send_step(self, step_url, step):
        step = self.limit_message_size(step)
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
        """Run deployment steps with secure configuration."""
        sudo_command = f"sudo -u {settings.sudo_user}"
        # Handle absolute vs relative paths
        if self.deploy_script.startswith("/"):
            deploy_command = self.deploy_script
        else:
            deploy_command = str(settings.services_root / self.deploy_script)

        # Create secure config file for subprocess
        secure_config = SecureConfig()
        config_path = secure_config.create_deployment_config(
            deployment_id=getattr(self, "deployment_id", "deploy_subprocess"),
            access_token=self.access_token,
            deploy_script=self.deploy_script,
            steps_url=self.steps_url,
            deployment_finish_url=self.deployment_finish_url,
            context=self.context.model_dump(),
            path_for_deploy=self.path_for_deploy,
            ssh_auth_sock=os.environ.get("SSH_AUTH_SOCK"),
        )

        # Pass config file path as argument instead of using --preserve-env
        command = f"{sudo_command} {deploy_command} --config {config_path}"

        # Minimal environment without sensitive data
        env = {
            "PATH": self.path_for_deploy,
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
            "DEPLOY_CONFIG_FILE": str(config_path),
        }

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                limit=MAX_ASYNCIO_STDOUT_SIZE,
                env=env,
            )
            while True:
                print("proc: ", proc.stdout)
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

        # Cleanup config file after deployment
        finally:
            if "config_path" in locals():
                secure_config.cleanup_config(config_path)

    async def run_deploy(self):
        try:
            await self.deploy_steps()
        except Exception as e:
            # If some unknown exception happens, we need to finish the deployment
            # as failed and therefore have at least one failed step. Which we create
            # here. We also append the exception message to the step.
            message = f"deployment failed: {e}"
            step_result = {
                "name": "failed step",
                "error_message": message,
                "state": "failure",
                "started": datetime.now(timezone.utc),
            }
            await self.finish_step(step_result)
            raise e
        finally:
            await self.finish_deployment()


async def run_deploy_task():  # pragma: no cover
    """Run deployment task, reading config from secure file if available."""
    # Try to read configuration from secure file first
    config_data = get_config_from_env()

    if config_data:
        # Use configuration from secure file
        deploy_task = DeployTask(
            deploy_script=config_data.get("deploy_script", ""),
            access_token=config_data.get("access_token", ""),
            steps_url=config_data.get("steps_url", ""),
            deployment_finish_url=config_data.get("deployment_finish_url", ""),
            context=DeploymentContext(**config_data.get("context", {})),
            path_for_deploy=config_data.get("path_for_deploy", ""),
        )
    else:
        # Fallback to environment variables (for backward compatibility)
        deploy_task = DeployTask()  # type: ignore

    async with httpx.AsyncClient(headers=deploy_task.headers) as client:
        deploy_task.client = client
        await deploy_task.run_deploy()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run_deploy_task())
