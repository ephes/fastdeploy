import os
import subprocess

import typer

from rich import print as rprint
from rich.prompt import Prompt

from app import database
from app.auth import get_password_hash
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
def createservice(name: str, collect: str, deploy: str):
    rprint(f"creating service {name} {collect} {deploy}")
    service = Service(name=name, collect=collect, deploy=deploy)
    service_in_db = database.repository.add_service(service)
    rprint(f"created service with id: {service_in_db.id}")


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
