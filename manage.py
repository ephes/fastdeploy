import os
import subprocess

from datetime import timedelta

import typer

from httpx import Client
from rich import print as rprint
from rich.prompt import Prompt

from app import database
from app.auth import create_access_token, get_password_hash
from app.main import app as fastapi_app
from app.models import Service, User


database.create_db_and_tables()
app = typer.Typer()


@app.command()
def createuser():
    username = Prompt.ask("Enter username", default=os.environ.get("USER", "fastdeploy"))
    password = Prompt.ask("Enter password", password=True)
    rprint(f"creating user {username}")
    user = User(username=username, password=get_password_hash(password))
    user_in_db = database.repository.add_user(user)
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


if __name__ == "__main__":
    app()
