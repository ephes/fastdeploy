import contextlib
import json
import os

from pathlib import Path

import yaml

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
    directories = []
    for entry_path in path.iterdir():
        if entry_path.is_dir():
            directories.append(entry_path.name)
    return directories


def get_steps_from_playbook(path_from_config: str) -> list[dict]:
    """
    Avoid mismatch between list of steps and ansible by getting
    the steps directly from the playbook.
    """
    playbook_path = settings.project_root / path_from_config
    with playbook_path.open("r") as playbook_file:
        parsed = yaml.safe_load(playbook_file)
    steps = []
    if "tasks" in parsed[0]:
        # workaround for ansible-galaxy (just roles, no tasks)
        steps = [{"name": task["name"]} for task in parsed[0]["tasks"] if "name" in task]
        steps.insert(0, {"name": "Gathering Facts"})
    return steps


def get_service_config(service_name: str) -> dict:
    """Returns a dictionary with the service configuration."""
    config_path = settings.services_root / service_name / "config.json"
    data_dict = {}
    with config_path.open() as config_file:
        data_dict = json.load(config_file)
    if not isinstance(data_dict, dict):
        raise TypeError("config is not a dict")
    # if ansible_playbook is set, read steps directly from playbook
    if "ansible_playbook" in data_dict:
        data_dict["steps"] = get_steps_from_playbook(data_dict["ansible_playbook"])
    return data_dict
