import asyncio
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def bootstrap():
    """
    Called when first non-standard lib import fails.
    """
    if not (Path.cwd() / ".venv").exists():
        print("No .venv found, creating one using uv...")
        subprocess.run(["uv", "venv", ".venv"], check=True)
        print("Please activate the virtual environment and run the script again.")
        sys.exit(1)

    print("Sync requirements via uv...")
    subprocess.run(["uv", "sync"], check=True)


try:
    import typer
except ImportError:
    bootstrap()
    import typer

sys.path.insert(0, "src")

import uvicorn  # noqa

from rich import print as rprint  # noqa
from rich.prompt import Prompt  # noqa

from deploy.adapters.filesystem import working_directory  # noqa
from deploy.auth import get_password_hash  # noqa
from deploy.bootstrap import get_bus_for_cli  # noqa
from deploy.config import settings  # noqa
from deploy.domain import commands, events  # noqa


CWD = str(Path(__file__).parent.resolve())
cli = typer.Typer()


async def createuser_async(username, password_hash) -> events.UserCreated:
    bus = await get_bus_for_cli()

    class UserCreatedHandler:
        user_event: events.UserCreated

        async def __call__(self, event: events.UserCreated):
            self.user_event = event

    handle_user_created = UserCreatedHandler()

    bus.event_handlers[events.UserCreated].append(handle_user_created)
    cmd = commands.CreateUser(username=username, password_hash=password_hash)
    await bus.handle(cmd)
    await bus.uow.close()
    return handle_user_created.user_event


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
        user_created = asyncio.run(createuser_async(username, password_hash))
        rprint("created: ", user_created)
    except Exception as e:
        rprint(f"failed to create user {username}")
        rprint(f"{e}")
        sys.exit(0)


async def _syncservices() -> None:
    bus = await get_bus_for_cli()
    cmd = commands.SyncServices()
    await bus.handle(cmd)
    await bus.uow.close()


@cli.command()
def syncservices():
    """
    Sync services from filesystem with services in database.
    """
    rprint("syncing services")
    asyncio.run(_syncservices())
    rprint("services synced")


@cli.command()
def update(upgrade: bool = typer.Option(True, "--upgrade/--no-upgrade")):
    """
    Update the backend requirements using uv.
    Update the frontend requirements using npm.
    """
    print("Updating requirements via uv...")
    subprocess.call(["uv", "lock", "--upgrade"])
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
    - run frontend tests via vitest
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

    gunicorn deploy.entrypoints.fastapi_app:app --workers 4 --worker-class uvicorn.workers.UvicornWorker
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


def deploy(environment):
    """
    Use ansible-playbook to deploy the site to the staging server.
    """
    deploy_root = Path(__file__).parent / "ansible"
    with working_directory(deploy_root):
        subprocess.call(["ansible-playbook", "deploy.yml", "--limit", environment])


@cli.command()
def deploy_staging():
    """Deploy to staging environment."""
    deploy("staging")


@cli.command()
def deploy_production():
    """Deploy to production environment."""
    deploy("production")


if __name__ == "__main__":
    cli()
