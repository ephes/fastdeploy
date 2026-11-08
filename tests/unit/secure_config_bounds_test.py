"""Private configuration reads are bounded and fail closed before task startup."""

import json
from unittest.mock import Mock

import pytest

from deploy import secure_config, tasks
from deploy.secure_config import SecureConfig, get_config_from_env

LIMIT = 1024 * 1024
INVALID = "Invalid deployment configuration"


def config():
    return {
        "deployment_id": "synthetic",
        "access_token": "token-sentinel",
        "deploy_script": "/synthetic/script",
        "steps_url": "http://synthetic/steps",
        "deployment_finish_url": "http://synthetic/finish",
        "context": {"env": {"SYNTHETIC": "value"}},
        "path_for_deploy": "/bin",
    }


def private_file(tmp_path, raw):
    path = tmp_path / "input.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


@pytest.mark.parametrize("grow_after_open", [False, True])
def test_config_budget_covers_actual_descriptor_bytes(tmp_path, monkeypatch, grow_after_open):
    raw = json.dumps(config()).encode()
    path = private_file(tmp_path, raw if grow_after_open else raw + b" " * LIMIT)
    opened = secure_config._open_config
    if grow_after_open:

        def grow(path, flags):
            fd = opened(path, flags)
            with path.open("ab") as file:
                file.write(b" " * LIMIT)
            return fd

        monkeypatch.setattr(secure_config, "_open_config", grow)
    with pytest.raises(ValueError, match=f"^{INVALID}$"):
        SecureConfig(tmp_path).read_deployment_config(path)


@pytest.mark.parametrize(
    "raw", [b"[]", b"null", b'"token-sentinel"', b"42", b'{"token-sentinel": "\xff"}', b'{"token-sentinel":']
)
def test_invalid_encoding_json_and_root_are_normalized(tmp_path, raw):
    path = private_file(tmp_path, raw)
    with pytest.raises(ValueError, match=f"^{INVALID}$"):
        SecureConfig(tmp_path).read_deployment_config(path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("deployment_id", 42),
        ("access_token", None),
        ("deploy_script", []),
        ("steps_url", {}),
        ("deployment_finish_url", False),
        ("path_for_deploy", 3),
        ("context", []),
        ("context", {"env": []}),
        ("ssh_auth_sock", 3),
    ],
)
def test_invalid_field_shapes_refuse(tmp_path, field, value):
    data = config()
    data[field] = value
    path = private_file(tmp_path, json.dumps(data).encode())
    with pytest.raises(ValueError, match=f"^{INVALID}$"):
        SecureConfig(tmp_path).read_deployment_config(path)


def test_missing_required_field_refuses(tmp_path):
    data = config()
    del data["deploy_script"]
    path = private_file(tmp_path, json.dumps(data).encode())
    with pytest.raises(ValueError, match=f"^{INVALID}$"):
        SecureConfig(tmp_path).read_deployment_config(path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [b"[]", b" " * (LIMIT + 1), b'{"access_token":"token-sentinel"}', b'"\xff"'],
    ids=["array", "oversized", "missing-fields", "invalid-utf8"],
)
async def test_invalid_config_never_falls_back_to_environment_or_starts_task(tmp_path, monkeypatch, caplog, raw):
    path = private_file(tmp_path, raw)
    monkeypatch.setenv("DEPLOY_CONFIG_FILE", str(path))
    startup = Mock(side_effect=AssertionError("task must not start"))
    monkeypatch.setattr(tasks, "DeployTask", startup)
    with pytest.raises(ValueError, match=f"^{INVALID}$"):
        await tasks.run_deploy_task()
    startup.assert_not_called()
    assert "token-sentinel" not in caplog.text
    assert str(path) not in caplog.text


def test_generated_config_roundtrips(tmp_path, monkeypatch):
    handler = SecureConfig(tmp_path)
    expected = config() | {"ssh_auth_sock": "/synthetic/agent.sock"}
    path = handler.create_deployment_config(**expected)
    monkeypatch.setenv("DEPLOY_CONFIG_FILE", str(path))
    try:
        assert get_config_from_env() == expected
    finally:
        assert handler.cleanup_config(path)


def test_oversized_generated_config_refuses_before_file_creation(tmp_path):
    data = config()
    # ASCII escaping/indentation are included in the wire budget.
    data["context"] = {"env": {"value": "\u2603" * (LIMIT // 6)}}
    with pytest.raises(ValueError, match=f"^{INVALID}$"):
        SecureConfig(tmp_path).create_deployment_config(**data)
    assert not list(tmp_path.glob("deploy_*.json"))


def test_empty_config_path_does_not_fall_back(monkeypatch):
    monkeypatch.setenv("DEPLOY_CONFIG_FILE", "")
    with pytest.raises(ValueError, match=f"^{INVALID}$"):
        get_config_from_env()
