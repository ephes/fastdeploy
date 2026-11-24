from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from deploy.entrypoints.routers import users

pytestmark = pytest.mark.asyncio


@pytest.fixture
def issuance(monkeypatch):
    app = FastAPI()
    app.include_router(users.router)
    uow = object()
    app.dependency_overrides[users.Bus] = lambda: SimpleNamespace(uow=uow)
    app.dependency_overrides[users.get_current_active_user] = lambda: users.User(name="synthetic-admin")
    monkeypatch.setattr(users.settings, "service_token_admin_users", ["synthetic-admin"])
    issuer = AsyncMock(
        return_value=("dummy-token", SimpleNamespace(jti="dummy-id", expires_at=datetime(2030, 1, 1, tzinfo=UTC)))
    )
    monkeypatch.setattr(users.auth, "issue_service_token_for_existing", issuer)
    return app, issuer, uow


@pytest.mark.parametrize("days", [True, False, "2", 2.0, 1.5, 0, users.settings.service_token_max_expire_days + 1])
async def test_invalid_service_token_days_are_rejected_before_issuance(issuance, days):
    app, issuer, _ = issuance
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/service-token", json={"service": "synthetic-service", "origin": "test", "expiration_in_days": days}
        )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "expiration_in_days"]
    issuer.assert_not_awaited()


@pytest.mark.parametrize("days", [None, 1, users.settings.service_token_max_expire_days])
async def test_default_and_integer_service_token_days_issue_once(issuance, days):
    app, issuer, uow = issuance
    body = {"service": "synthetic-service", "origin": "test"}
    if days is not None:
        body["expiration_in_days"] = days
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/service-token", json=body)
    assert response.status_code == 200
    assert response.json()["service_token"] == "dummy-token"
    issuer.assert_awaited_once_with(
        service="synthetic-service", origin="test", user="synthetic-admin", days=1 if days is None else days, uow=uow
    )
