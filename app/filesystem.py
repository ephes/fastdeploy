import contextlib
import json
import os

from pathlib import Path

from .config import settings


@contextlib.contextmanager
def working_directory(path):
    """Changes working directory and returns to previous on exit."""
    prev_cwd = Path.cwd().absolute()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(prev_cwd)


def get_directories(path: Path) -> list[str]:
    """Returns a list of directories in a given path."""
    for entry_path in path.iterdir():
        if entry_path.is_dir():
            yield entry_path.name


def get_service_config(service_name: str) -> dict:
    """Returns a dictionary with the service configuration."""
    config_path = settings.deploy_root / service_name / "config.json"
    data_dict = {}
    with config_path.open() as config_file:
        data_dict = json.load(config_file)
    return data_dict
