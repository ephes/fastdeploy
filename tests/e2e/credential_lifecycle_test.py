"""Credential boundaries through HTTP, using synthetic in-memory records."""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from deploy.auth import token_to_payload
from deploy.config import settings

pytestmark = [pytest.mark.asyncio, pytest.mark.db("in_memory")]


@pytest.mark.parametrize("jti_known", [True, False])
@pytest.mark.parametrize("admins", [[], ["another-admin"]])
async def test_non_admin_cannot_revoke_or_probe_service_tokens(
    app, bus, valid_access_token_in_db, valid_service_token_in_db, monkeypatch, jti_known, admins
):
    monkeypatch.setattr(settings, "service_token_admin_users", admins)
    jti = token_to_payload(valid_service_token_in_db)["jti"]
    async with bus.uow:
        record = await bus.uow.service_tokens.get_by_jti(jti)
    with patch.object(bus, "handle", wraps=bus.handle) as handle:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/service-token/{jti if jti_known else 'unknown'}",
                headers={"authorization": f"Bearer {valid_access_token_in_db}"},
            )
    assert response.status_code == 403
    assert response.json() == {"detail": "Service token revocation requires an administrator"}
    handle.assert_not_called()
    assert record.revoked_at is None


async def test_admin_revocation_is_idempotent(app, valid_access_token_in_db, valid_service_token_in_db, monkeypatch):
    monkeypatch.setattr(settings, "service_token_admin_users", ["user"])
    jti = token_to_payload(valid_service_token_in_db)["jti"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.delete(
            f"/service-token/{jti}", headers={"authorization": f"Bearer {valid_access_token_in_db}"}
        )
        second = await client.delete(
            f"/service-token/{jti}", headers={"authorization": f"Bearer {valid_access_token_in_db}"}
        )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


@pytest.mark.parametrize("credential_type", ["service", "deployment"])
async def test_revocation_refuses_non_user_credentials(
    app, bus, valid_service_token_in_db, valid_deploy_token_in_db, credential_type, monkeypatch
):
    monkeypatch.setattr(settings, "service_token_admin_users", ["user"])
    credential = valid_service_token_in_db if credential_type == "service" else valid_deploy_token_in_db
    with patch.object(bus, "handle", wraps=bus.handle) as handle:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete("/service-token/unknown", headers={"authorization": f"Bearer {credential}"})
    assert response.status_code == 401
    handle.assert_not_called()


def assert_private_response(response):
    assert response.headers["cache-control"] == "private, no-store"
    assert "authorization" in {value.strip().lower() for value in response.headers["vary"].split(",")}


async def test_secret_bearing_http_responses_are_not_stored(
    app, service_in_db, deployed_service_in_db, valid_access_token_in_db, user_in_db, password, monkeypatch
):
    from datetime import timedelta

    from deploy.auth import create_access_token

    monkeypatch.setattr(settings, "service_token_admin_users", ["user"])
    config_credential = create_access_token({"type": "config"}, timedelta(minutes=5))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = [
            await client.post("/token", data={"username": user_in_db.name, "password": password}),
            await client.post(
                "/service-token",
                json={"service": service_in_db.name, "origin": "fixture"},
                headers={"authorization": f"Bearer {valid_access_token_in_db}"},
            ),
            await client.get("/services/", headers={"authorization": f"Bearer {valid_access_token_in_db}"}),
            await client.get("/deployed-services/", headers={"authorization": f"Bearer {config_credential}"}),
        ]
    for response in responses:
        assert response.status_code == 200
        assert_private_response(response)
    assert responses[0].json()["access_token"]
    assert responses[1].json()["service_token"]
    assert responses[2].json()[0]["data"] == service_in_db.data
    assert responses[3].json()[0]["config"] == deployed_service_in_db.config


@pytest.mark.parametrize("path", ["/services/", "/deployed-services/", "/service-token", "/token"])
async def test_secret_response_policy_includes_authentication_errors(app, path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        if path == "/token":
            response = await client.post(path, data={"username": "unknown", "password": "wrong"})
        elif path == "/service-token":
            response = await client.post(path, json={"service": "fixture", "origin": "fixture"})
        else:
            response = await client.get(path)
    assert response.status_code == 401
    assert_private_response(response)


async def test_config_response_rechecks_same_credentials_after_expiry(app, deployed_service_in_db, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from deploy import auth
    from deploy.auth import create_access_token

    credential = create_access_token({"type": "config"}, timedelta(minutes=5))
    headers = {"authorization": f"Bearer {credential}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/deployed-services/", headers=headers)
        assert first.status_code == 200
        assert_private_response(first)

        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(timezone.utc) + timedelta(minutes=10)

        monkeypatch.setattr(auth, "datetime", Later)
        second = await client.get("/deployed-services/", headers=headers)
    assert second.status_code == 401
    assert_private_response(second)
    assert "config" not in second.text


async def test_private_response_policy_preserves_cors_vary(app, valid_access_token_in_db):
    headers = {"authorization": f"Bearer {valid_access_token_in_db}", "origin": settings.origins[0]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/services/", headers=headers)
    assert response.status_code == 200
    assert_private_response(response)
    assert "origin" in {value.strip().lower() for value in response.headers["vary"].split(",")}
