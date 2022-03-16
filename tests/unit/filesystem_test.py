import json

import pytest


def test_list_only_directories(services_filesystem):
    regular_file = services_filesystem.root / "regular_file.txt"
    regular_file.touch()
    assert services_filesystem.list() == []


def test_config_has_to_be_dict(services_filesystem):
    service_path = services_filesystem.root / "service"
    service_path.mkdir()
    config_path = service_path / "config.json"
    with config_path.open("w") as config_file:
        config_file.write("[]")
    with pytest.raises(TypeError):
        services_filesystem.get_config_by_name("service")


def test_get_no_steps_from_playbook(services_filesystem):
    service_path = services_filesystem.root / "service"
    service_path.mkdir()
    playbook_path = service_path / "playbook.yml"
    with playbook_path.open("w") as playbook_file:
        playbook_file.write("- hosts: localhost\n")
    config_path = service_path / "config.json"
    with config_path.open("w") as config_file:
        config = {"ansible_playbook": str(playbook_path)}
        config_file.write(json.dumps(config))
    config = services_filesystem.get_config_by_name("service")
    assert config["steps"] == []


def test_get_steps_from_playbook_happy(services_filesystem):
    service_path = services_filesystem.root / "service"
    service_path.mkdir()
    playbook_path = service_path / "playbook.yml"
    with playbook_path.open("w") as playbook_file:
        playbook_file.write("- hosts: localhost\n" "  tasks:\n" "    - name: task1\n")
    config_path = service_path / "config.json"
    with config_path.open("w") as config_file:
        config = {"ansible_playbook": str(playbook_path)}
        config_file.write(json.dumps(config))
    config = services_filesystem.get_config_by_name("service")
    assert config["steps"] == [{"name": "Gathering Facts"}, {"name": "task1"}]
