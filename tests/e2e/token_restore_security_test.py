"""Authorization and restore admission, exercised through the production API."""

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from deploy.auth import create_access_token, token_to_payload
from deploy.config import RestorePolicy, settings
from deploy.domain import model
from deploy.secure_config import SecureConfig

pytestmark = [pytest.mark.asyncio, pytest.mark.db("in_memory")]


@pytest.fixture(autouse=True)
def config_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("deploy.tasks.SecureConfig", lambda: SecureConfig(tmp_path))


@pytest.fixture
def restore_policy(monkeypatch):
    monkeypatch.setattr(
        settings,
        "restore_policies",
        {"fastdeploytest": RestorePolicy(bucket="backups", prefixes=["target/", "legacy-target/"])},
    )


async def post(app, path, credential, body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path, headers={"authorization": f"Bearer {credential}"}, json=body)


@pytest.mark.parametrize("admins,expected", [([], 403), (["somebody-else"], 403), (["user"], 200)])
async def test_only_configured_admin_can_issue(
    app, uow, service_in_db, valid_access_token_in_db, monkeypatch, admins, expected
):
    monkeypatch.setattr(settings, "service_token_admin_users", admins)
    response = await post(
        app, "/service-token", valid_access_token_in_db, {"service": service_in_db.name, "origin": "test"}
    )
    assert response.status_code == expected
    async with uow:
        records = await uow.service_tokens.list()
    assert len(records) == (1 if expected == 200 else 0)
    if expected == 403:
        assert response.json()["detail"] == "Service token issuance requires an administrator"


@patch("deploy.tasks.subprocess.Popen")
@pytest.mark.parametrize("action", ["deploy", "backup", "restore"])
async def test_start_uses_token_service_only(
    popen, app, uow, publisher, valid_service_token_in_db, service_in_db, restore_policy, action, monkeypatch
):
    # An already issued token remains valid even with no configured issuers.
    monkeypatch.setattr(settings, "service_token_admin_users", [])
    async with uow:
        foreign = model.Service(name="foreign", data={"deploy_script": "/foreign/runner.py"})
        await uow.services.add(foreign)
        await uow.commit()
    launched = []

    def capture_config(*args, **kwargs):
        from unittest.mock import MagicMock

        launched.append(json.loads(Path(kwargs["env"]["DEPLOY_CONFIG_FILE"]).read_text()))
        return MagicMock()

    popen.side_effect = capture_config
    env = {"ECHOPORT_ACTION": action}
    if action == "restore":
        env.update(ECHOPORT_BUCKET="backups", ECHOPORT_KEY="target/2026-10-20.tar.gz")
    response = await post(
        app,
        "/deployments/?service=foreign",
        valid_service_token_in_db,
        {"env": env, "service": "foreign", "service_id": foreign.id, "deploy_script": "/foreign/runner.py"},
    )
    assert response.status_code == 200
    assert response.json()["service_id"] == service_in_db.id
    popen.assert_called_once()
    assert launched[0]["deploy_script"] == service_in_db.get_deploy_script()
    assert launched[0]["context"] == {"env": env}
    async with uow:
        deployments = await uow.deployments.list()
    assert len(deployments) == 1
    assert deployments[0].service_id == service_in_db.id


@patch("deploy.tasks.subprocess.Popen")
async def test_signed_token_cannot_change_service_of_record(popen, app, valid_service_token_in_db):
    payload = token_to_payload(valid_service_token_in_db)
    payload["service"] = "foreign"
    credential = create_access_token(payload, timedelta(minutes=5))
    response = await post(app, "/deployments/", credential, {})
    assert response.status_code == 401
    popen.assert_not_called()


@patch("deploy.tasks.subprocess.Popen")
@pytest.mark.parametrize(
    "key",
    [
        "other/archive.tar.gz",
        "target-evil/archive.tar.gz",
        "legacy-target/",
        "legacy/archive.tar.gz",
        "target/../other.tar.gz",
        "target/a..tar.gz",
        "/target/archive.tar.gz",
        "https://target/archive.tar.gz",
        "target/https://evil/archive.tar.gz",
        "target/%2e%2e/archive.tar.gz",
        "target/./archive.tar.gz",
        "target//archive.tar.gz",
        "target/",
        "target/dir/",
        "target/dir\\archive.tar.gz",
        "target/a\n.tar.gz",
        None,
        123,
        [],
        {},
    ],
)
async def test_bad_restore_key_never_starts(
    popen, app, uow, publisher, valid_service_token_in_db, restore_policy, key
):
    response = await post(
        app,
        "/deployments/",
        valid_service_token_in_db,
        {"env": {"ECHOPORT_ACTION": "restore", "ECHOPORT_BUCKET": "backups", "ECHOPORT_KEY": key}},
    )
    assert response.status_code == 422
    assert "ECHOPORT_KEY" in response.json()["detail"]
    popen.assert_not_called()
    async with uow:
        assert await uow.deployments.list() == []
    assert publisher.events == []


@patch("deploy.tasks.subprocess.Popen")
@pytest.mark.parametrize(
    "env,configured",
    [
        ({"ECHOPORT_ACTION": "restore", "ECHOPORT_BUCKET": "backups", "ECHOPORT_KEY": "target/a.tar.gz"}, False),
        ({"ECHOPORT_ACTION": "restore", "ECHOPORT_BUCKET": "other", "ECHOPORT_KEY": "target/a.tar.gz"}, True),
        ({"ECHOPORT_ACTION": "restore", "ECHOPORT_KEY": "target/a.tar.gz"}, True),
        ({"ECHOPORT_ACTION": "restore", "ECHOPORT_BUCKET": "backups"}, True),
        ({"ECHOPORT_ACTION": " ReStOrE ", "ECHOPORT_BUCKET": "backups"}, True),
        ({"ECHOPORT_ACTION": "RESTORE"}, False),
        ({"ECHOPORT_KEY": "other/a.tar.gz", "ECHOPORT_BUCKET": "backups"}, True),
    ],
)
async def test_restore_requires_service_policy_bucket_and_key(
    popen, app, valid_service_token_in_db, restore_policy, monkeypatch, env, configured
):
    if not configured:
        monkeypatch.setattr(settings, "restore_policies", {})
    response = await post(app, "/deployments/", valid_service_token_in_db, {"env": env})
    assert response.status_code == 422
    popen.assert_not_called()


@patch("deploy.tasks.subprocess.Popen")
@pytest.mark.parametrize("key", ["target/2026-10-20T03-00-00.tar.gz", "legacy-target/2026-01-01T03-00-00.tar.gz"])
async def test_restore_below_any_configured_prefix_starts(
    popen, app, uow, publisher, valid_service_token_in_db, restore_policy, key
):
    env = {"ECHOPORT_ACTION": "restore", "ECHOPORT_BUCKET": "backups", "ECHOPORT_KEY": key}
    response = await post(app, "/deployments/", valid_service_token_in_db, {"env": env})
    assert response.status_code == 200
    popen.assert_called_once()
