import subprocess
import sys

from .config import settings


async def run_deploy():
    print("running deployment")
    environment = {"ACCESS_TOKEN": "foobarbaz", "DEPLOY_SCRIPT": "sample.sh"}
    command = [sys.executable, settings.project_root / "deployments" / "deploy.py"]
    subprocess.Popen(command, start_new_session=True, env=environment)
