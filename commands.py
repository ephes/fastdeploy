import asyncio
import os
import subprocess
import sys
import platform
import json

from datetime import timedelta
from pathlib import Path

import typer
import uvicorn

from httpx import Client
from rich import print as rprint
from rich.prompt import Prompt

from app import database
from app.auth import create_access_token, get_password_hash
from app.config import settings
from app.filesystem import working_directory
from app.main import app as fastapi_app
from app.models import Service, User


CWD = '.'

database.create_db_and_tables()
cli = app = typer.Typer()


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
            sys.executable,
            "-m",
            "piptools",
            "compile",
            "--generate-hashes",
            "app/requirements/production.in",
            "app/requirements/develop.in",
            "--output-file",
            "app/requirements/develop.txt",
        ]
    )
    subprocess.call([sys.executable, "-m", "piptools", "sync", "app/requirements/develop.txt"])
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
        npm = "npm" if not platform.system() == "Windows" else "npm.cmd"
        subprocess.call([npm, "run", "test"])



# ---------- DOCUMENTATION mkdocs ---------------------------------------------
@cli.command()
def docs(
    serve: bool = True,
    build: bool = False,
    clean: bool = False,
    openapi: bool = False,
    doc_path: Path = Path(CWD) / 'docs',
    site_path: Path = Path(CWD) / 'site',
):
    """
    default: mkdocs serve
    --build: clean, openapi and `mkdocs build`
    --clean: delete the site-folder
    --openapi: generate a fresh openapi.json
    """
    if openapi:
        docs_openapi(doc_path=doc_path)
    elif build:
        docs_build(site_path=site_path)
    elif clean:
        docs_clean(site_path=site_path)
    elif serve:
        if not (doc_path / "openapi.json").exists():
            docs_openapi(doc_path=doc_path)
        docs_serve()

@cli.command()
def docs_build(site_path: Path = Path(CWD) / 'site'):
    """
    build mkdocs

    cleans old docs in doc_path
    gets a new openapi-spec
    builds new docs to ./site
    """
    docs_clean(site_path=site_path)
    docs_openapi()
    command = "mkdocs build"
    subprocess.run(command.split(), cwd=CWD, env=None, shell=False)

@cli.command()
def docs_openapi(doc_path: Path = Path(CWD) / 'docs'):
    """load new openapi.json into mkdocs"""
    from app.main import app
    open_api_schema = app.openapi()
    with open(doc_path / "openapi.json", "w") as file:
        json.dump(open_api_schema, file, indent=4)
    rprint(f"Updated {doc_path / 'openapi.json'}.")

@cli.command()
def docs_serve():
    """serve mkdocs"""
    command = "mkdocs serve"
    subprocess.run(command.split(), cwd=CWD, env=None, shell=False)

@cli.command()
def docs_clean(site_path: Path = Path(CWD) / 'site'):
    """Delete the site_path directory recursively."""
    def rm_tree(path: Path):
        """Recursively delete the directory tree."""
        for child in path.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                rm_tree(child)
        path.rmdir()
    rprint(f"Deletes .site/")
    if site_path.exists():
        rm_tree(site_path)


# ---------- MANAGE THE SERVER ------------------------------------------------
@cli.command()
def up(port: int = 8000, host: str = "127.0.0.1", log_level: str = "info", reload: bool = True, docs: bool = False):
    """= run (start the devserver)"""
    run(port=port, host=host, log_level=log_level, reload=reload, docs=docs)

@cli.command()
def serve(port: int = 8000, host: str = "127.0.0.1", log_level: str = "info", reload: bool = True, docs: bool = False):
    """= run (start the devserver)"""
    run(port=port, host=host, log_level=log_level, reload=reload, docs=docs)

@cli.command()
def run(
    port: int = 8000,
    host: str = "127.0.0.1",
    log_level: str = "info",
    reload: bool = True,
    docs: bool = False,
):  # pragma: no cover
    """
    Run the API server.
    if --docs: run the mkdocs server instead.

    You may run uvicorn over gunicorn to allow multiple workers.
    (on windows fcntl is not available, -> ModuleNotFoundError: No module named 'fcntl')
    https://www.uvicorn.org/#running-with-gunicorn
    
    gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker
    """
    if docs:
        docs_serve()
        return

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=reload,
    )


if __name__ == "__main__":
    app()
