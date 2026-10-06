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
    access_token = create_access_token(
        payload=payload,
        expires_delta=timedelta(minutes=settings.deployment_access_token_expire_minutes),
    )
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
    attempts: int = 4
    # Finishing the deployment gets more attempts: if it is lost, the deployment stays
    # active and blocks new deployments of the service until it becomes stale.
    finish_attempts: int = 6
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

    @staticmethod
    def log(message: str) -> None:
        """
        Report problems of the deploy task on stderr. The task runs detached from the
        API process, so stderr (for example the journal) is the only place left when
        reporting to the API fails. Never log tokens or step messages here.
        """
        print(f"fastdeploy deploy task: {message}", file=sys.stderr, flush=True)

    @staticmethod
    def is_retryable(error: Exception) -> bool:
        """Transport errors and server errors may go away (for example during an API restart), 4xx won't."""
        if isinstance(error, httpx.TransportError):
            return True
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code >= 500
        return False

    async def request_with_retries(self, method: str, url: str, *, attempts: int, **kwargs) -> None:
        """
        Send a request to the API, retrying transport errors and 5xx responses with
        exponential backoff. Raises the last error when all attempts failed or the
        error is not retryable.
        """
        for attempt in range(attempts):
            try:
                r = await getattr(self.client, method)(url, **kwargs)
                r.raise_for_status()
                return
            except httpx.HTTPError as e:
                if not self.is_retryable(e) or attempt == attempts - 1:
                    raise
                await asyncio.sleep(self.sleep_on_fail * 2**attempt)

    async def send_step(self, step_url, step, attempts: int | None = None) -> bool:
        """
        Post a step to the API. Never raises on HTTP problems, so a failed post does not
        abort reading the deploy script output. Returns whether the step was accepted.
        """
        step = self.limit_message_size(step)
        attempts = self.attempts if attempts is None else attempts
        try:
            await self.request_with_retries("post", step_url, attempts=attempts, json=json.loads(step.json()))
            return True
        except httpx.HTTPError as e:
            self.log(f"dropped step {step.name!r} ({step.state}): {type(e).__name__}: {e}")
            return False

    async def finish_deployment(self) -> None:
        await self.request_with_retries("put", self.deployment_finish_url, attempts=self.finish_attempts)

    @staticmethod
    def as_text(value: Any) -> str:
        """Step messages must be strings, but Ansible may report a list or dict as `msg`."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError):
            return str(value)

    async def finish_step(self, step_result, attempts: int | None = None) -> bool:
        step = Step(**step_result)
        step.finished = datetime.now(timezone.utc)
        step.message = self.as_text(step.message)
        error_message = self.as_text(step_result.get("error_message"))
        if len(error_message) > 0:
            step.message = error_message
        return await self.send_step(self.steps_url, step, attempts=attempts)

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
                started = datetime.now(timezone.utc)
                data = await proc.stdout.readline()
                if not data:
                    break

                # Do NOT check proc.returncode here. The process may have exited
                # but still have buffered stdout data that must be processed.
                # readline() returns empty only after all buffered output is read.

                decoded = data.decode("UTF-8")
                try:
                    step_result = json.loads(decoded)
                except json.decoder.JSONDecodeError:
                    continue
                if not isinstance(step_result, dict):
                    # valid JSON, but not a step result (for example a list) -> skip
                    continue
                # if name is None there's something wrong -> skip
                result_name = step_result.get("name")
                if result_name is None:
                    # should not happen
                    print("step result not posted: ", step_result)
                    continue
                step_result["started"] = started
                try:
                    await self.finish_step(step_result)
                except Exception as e:
                    # Keep draining stdout, otherwise the deploy script blocks on a full pipe.
                    self.log(f"could not report step {result_name!r}: {type(e).__name__}: {e}")

            return_code = await proc.wait()
            if return_code != 0:
                raise RuntimeError(f"deploy script exited with code {return_code}")

        # Cleanup config file after deployment
        finally:
            if "config_path" in locals():
                secure_config.cleanup_config(config_path)

    async def report_failure(self, error: BaseException) -> bool:
        """
        If the deployment fails, we need to finish it as failed and therefore have at
        least one failed step, which we create here. We also append the exception
        message to the step. Gets as many attempts as finishing the deployment. Never
        raises, so the original error is preserved. Returns whether the failed step was
        accepted by the API.
        """
        step_result = {
            "name": "failed step",
            "error_message": f"deployment failed: {str(error) or type(error).__name__}",
            "state": "failure",
            "started": datetime.now(timezone.utc),
        }
        try:
            return await self.finish_step(step_result, attempts=self.finish_attempts)
        except Exception as e:
            self.log(f"could not report failed step: {type(e).__name__}: {e}")
            return False

    async def run_deploy(self):
        failed = False
        failure_reported = False
        try:
            await self.deploy_steps()
        except BaseException as e:
            failed = True
            failure_reported = await self.report_failure(e)
            raise
        finally:
            if failed and not failure_reported:
                # Finishing now would remove the open steps and make the failed
                # deployment look successful. Leave it unfinished instead: it stops
                # blocking new deployments once it is stale.
                self.log("not finishing the deployment, because its failure could not be reported")
            else:
                try:
                    await self.finish_deployment()
                except Exception as e:
                    self.log(f"could not finish deployment: {type(e).__name__}: {e}")
                    if not failed:
                        raise


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
