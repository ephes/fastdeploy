from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from deploy.auth import create_access_token
from deploy.config import settings

pytestmark = [pytest.mark.asyncio, pytest.mark.db("in_memory")]


@pytest.mark.parametrize("value", [None, [], {}, True, 1, 1.5, " ", "x\x00y", "x" * 256])
@pytest.mark.parametrize("claim", ["user", "service", "jti", "origin"])
async def test_bad_string_claims_refuse_before_lookup(app, bus, monkeypatch, value, claim):
    monkeypatch.setattr(settings, "legacy_service_tokens_accepted_until", None)
    lookup = AsyncMock(side_effect=AssertionError("repository must not be reached"))
    for repo, method in [
        (bus.uow.users, "get"),
        (bus.uow.services, "get_by_name"),
        (bus.uow.service_tokens, "get_by_jti"),
    ]:
        monkeypatch.setattr(repo, method, lookup)
    payload = {"type": "service", "user": "user", "service": "svc", "jti": "record", "origin": "test", claim: value}
    token = create_access_token(payload)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/deployments/", headers={"Authorization": f"Bearer {token}"}, json={"env": {}})
    assert response.status_code == 401
    lookup.assert_not_awaited()


@pytest.mark.parametrize(
    "kind,value",
    [
        ("user", []),
        ("user", True),
        ("user", "x" * 256),
        ("deployment", []),
        ("deployment", {}),
        ("deployment", True),
        ("deployment", "1"),
        ("deployment", 0),
        ("deployment", -1),
        ("deployment", 2**31),
    ],
)
async def test_bad_user_and_deployment_identity(app, bus, monkeypatch, kind, value):
    lookup = AsyncMock(side_effect=AssertionError("repository must not be reached"))
    monkeypatch.setattr(bus.uow.users, "get", lookup)
    monkeypatch.setattr(bus.uow.deployments, "get", lookup)
    token = create_access_token({"type": kind, kind: value})
    path = "/services/" if kind == "user" else "/deployments/1/finish"
    # Use real auth dependencies on a test-only route for deployment credentials.
    from fastapi import Depends

    from deploy.entrypoints.dependencies import get_current_active_deployment

    if kind == "deployment":
        from fastapi import FastAPI

        from deploy.bootstrap import get_bus

        probe = FastAPI()
        probe.dependency_overrides[get_bus] = lambda: bus

        @probe.get("/probe")
        async def endpoint(deployment=Depends(get_current_active_deployment)):
            return {}

        target, path = probe, "/probe"
    else:
        target = app
    async with AsyncClient(transport=ASGITransport(app=target), base_url="http://test") as client:
        response = await client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    lookup.assert_not_awaited()
