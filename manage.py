import os

import typer

from rich import print as rprint
from rich.prompt import Prompt

from app import database
from app.models import create_service, create_user


database.create_db_and_tables()
app = typer.Typer()


@app.command()
def createuser():
    username = Prompt.ask("Enter username", default=os.environ.get("USER", "fastdeploy"))
    password = Prompt.ask("Enter password", password=True)
    rprint(f"creating user {username}")
    create_user(username, password)


@app.command()
def createservice(name: str, collect: str, deploy: str):
    rprint(f"creating service {name} {collect} {deploy}")
    create_service(name, collect, deploy)


if __name__ == "__main__":
    app()