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
