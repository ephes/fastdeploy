import asyncio
import os
import subprocess
import sys

from datetime import timedelta

import typer

from httpx import Client
from rich import print as rprint
from rich.prompt import Prompt

from app import database
from app.auth import create_access_token, get_password_hash
from app.config import settings
from app.filesystem import working_directory
from app.main import app as fastapi_app
from app.models import Service, User


database.create_db_and_tables()
app = typer.Typer()


@app.command()
def createuser():
    username = Prompt.ask("Enter username", default=os.environ.get("USER", "fastdeploy"))
    password = Prompt.ask("Enter password", password=True)
    rprint(f"creating user {username}")
    user = User(name=username, password=get_password_hash(password))
    user_in_db = asyncio.run(database.repository.add_user(user))
    rprint(f"created user with id: {user_in_db.id}")


@app.command()
def create_initial_user():
    database.create_db_and_tables()
    username = os.environ["INITIAL_USER_NAME"]
    password_hash = os.environ["INITIAL_PASSWORD_HASH"]
    if user := asyncio.run(database.repository.get_user_by_name(username)):
        rprint(f"user {username} already exists")
        sys.exit(0)
    rprint(f"creating user {username}")
    user = User(name=username, password=password_hash)
    user_in_db = asyncio.run(database.repository.add_user(user))
    rprint(f"created user with id: {user_in_db.id}")


@app.command()
def createservice(username: str, name: str, collect: str, deploy: str):
    """Use api of application server to be able to update ServiceList on clients via websocket."""
    rprint(f"creating service as user {username}: {name} {collect} {deploy}")
    print("url create service: ", fastapi_app.url_path_for("create_service"))
    access_token = create_access_token({"type": "user", "user": username}, timedelta(minutes=5))
    service = Service(name=name, collect=collect, deploy=deploy)
    with Client(base_url="http://localhost:8000/") as client:
        r = client.post(
            fastapi_app.url_path_for("create_service"),
            headers={"authorization": f"Bearer {access_token}"},
            json=service.dict(),
        )
    rprint("r status code: ", r.status_code)
    rprint(f"created service with id: {r.json()['id']}")


@app.command()
def update():
    """
    Update the development environment by calling:
    - pip-compile
    - pip-sync
    - npm update
    """
    subprocess.call(
        [
            "pip-compile",
            "--generate-hashes",
            "app/requirements/production.in",
            "app/requirements/develop.in",
            "--output-file",
            "app/requirements/develop.txt",
        ]
    )
    subprocess.call(["pip-sync", "app/requirements/develop.txt"])
    with working_directory(settings.project_root / "frontend"):
        subprocess.call(["npm", "update"])


@app.command()
def notebook():
    """
    Start the notebook server.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = ".."
    subprocess.call(["jupyter", "notebook", "--notebook-dir", "notebooks"], env=env)


@app.command()
def test():
    """
    Run the tests:
    - run backend tests via pytest
    - fun frontend tests via jest
    """
    subprocess.call([sys.executable, "-m", "pytest"])
    with working_directory(settings.project_root / "frontend"):
        subprocess.call(["npm", "run", "test"])


if __name__ == "__main__":
    app()
