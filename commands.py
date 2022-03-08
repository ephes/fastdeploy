import asyncio
import json
import os
import platform
import subprocess
import sys

from datetime import timedelta
from pathlib import Path

import typer
import uvicorn

from httpx import Client
from rich import print as rprint
from rich.prompt import Prompt

from deploy.adapters.filesystem import working_directory
from deploy.auth import create_access_token, get_password_hash
from deploy.bootstrap import bootstrap
from deploy.config import settings
from deploy.domain import model


CWD = str(Path(__file__).parent.resolve())
cli = typer.Typer()


async def createuser_async(username, password_hash):
    bus = await bootstrap()
    # user has to be created after the orm mappers were started
    user = model.User(name=username, password=password_hash)
    async with bus.uow as uow:
        await uow.users.add(user)
        await uow.commit()
    return user


@cli.command()
def createuser():
    """
    Create a new user. Username and password are either set via
    environment variables, to create an initial user via ansible for example,
    or interactively via the command line.
    """
    try:
        username = os.environ["INITIAL_USER_NAME"]
        password_hash = os.environ["INITIAL_PASSWORD_HASH"]
    except KeyError:
        username = Prompt.ask("Enter username", default=os.environ.get("USER", "fastdeploy"))
        password_hash = get_password_hash(Prompt.ask("Enter password", password=True))
    rprint(f"creating user {username}")
    try:
        user = asyncio.run(createuser_async(username, password_hash))
    except Exception as e:
        rprint(f"failed to create user {username}")
        rprint(f"{e}")
        sys.exit(1)
    rprint(f"created user with id: {user.id}")


@cli.command()
def syncservices(username: str):
    """
    Sync services from filesystem with services in database. Username is required
    to be able to authenticate with the API. And have the application server send
    events to clients via websocket.
    """
    rprint(f"syncing services as user: {username}")
    access_token = create_access_token({"type": "user", "user": username}, timedelta(minutes=5))
    with Client(headers={"authorization": f"Bearer {access_token}"}) as client:
        response = client.post(settings.sync_services_url, follow_redirects=True)
        response.raise_for_status()
        rprint("services synced")


@cli.command()
def update():
    """
    Update the development environment by calling:
    - pip-compile production.in develop.in -> develop.txt
    - pip-compile production.in -> production.txt
    - pip-sync develop.txt
    - npm update
    """
    base_command = [
        sys.executable,
        "-m",
        "piptools",
        "compile",
        "--upgrade",
        "--allow-unsafe",
        "--generate-hashes",
        "deploy/requirements/production.in",
    ]
    subprocess.call(  # develop + production
        [
            *base_command,
            "deploy/requirements/develop.in",
            "--output-file",
            "deploy/requirements/develop.txt",
        ]
    )
    subprocess.call(  # production only
        [
            *base_command,
            "--output-file",
            "deploy/requirements/production.txt",
        ]
    )
    subprocess.call([sys.executable, "-m", "piptools", "sync", "deploy/requirements/develop.txt"])
    with working_directory(settings.project_root / "frontend"):
        subprocess.call(["npm", "update"])


@cli.command()
def notebook():
    """
    Start the notebook server.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = CWD
    rprint("added pythonpath: ", env["PYTHONPATH"])
    subprocess.call(["jupyter", "notebook", "--notebook-dir", "notebooks"], env=env)


@cli.command()
def jupyterlab():
    """
    Start a jupyterlab server.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = CWD
    rprint("added pythonpath: ", env["PYTHONPATH"])
    subprocess.call(["jupyter-lab"], env=env)


@cli.command()
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


@cli.command()
def coverage():
    """
    Run and show coverage.
    """
    subprocess.call(["coverage", "run"])
    subprocess.call(["coverage", "html"])
    subprocess.call(["open", "htmlcov/index.html"])


# ---------- DOCUMENTATION mkdocs ---------------------------------------------
@cli.command()
def docs(
    serve: bool = True,
    build: bool = False,
    clean: bool = False,
    openapi: bool = False,
    doc_path: Path = Path(CWD) / "docs",
    site_path: Path = Path(CWD) / "site",
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
def docs_build(site_path: Path = Path(CWD) / "site"):
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
def docs_openapi(doc_path: Path = Path(CWD) / "docs"):
    """load new openapi.json into mkdocs"""
    from deploy.entrypoints.fastapi_app import app as fastapi_app

    open_api_schema = fastapi_app.openapi()
    with open(doc_path / "openapi.json", "w") as file:
        json.dump(open_api_schema, file, indent=4)
    rprint(f"Updated {doc_path / 'openapi.json'}.")


@cli.command()
def docs_serve():
    """serve mkdocs"""
    command = "mkdocs serve"
    subprocess.run(command.split(), cwd=CWD, env=None, shell=False)


@cli.command()
def docs_clean(site_path: Path = Path(CWD) / "site"):
    """Delete the site_path directory recursively."""

    def rm_tree(path: Path):
        """Recursively delete the directory tree."""
        for child in path.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                rm_tree(child)
        path.rmdir()

    rprint("Deletes .site/")
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
        "deploy.entrypoints.fastapi_app:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=reload,
    )


if __name__ == "__main__":
    cli()
