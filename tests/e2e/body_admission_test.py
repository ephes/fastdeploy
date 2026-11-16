"""Admit synthetic raw bytes before JSON, forms, credentials or storage."""

import asyncio
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from deploy.entrypoints import fastapi_app

pytestmark = [pytest.mark.asyncio, pytest.mark.db("in_memory")]


@pytest.mark.parametrize(
    "path,content_type",
    [
        ("/deployments/", "application/json"),
        ("/steps/", "application/json"),
        ("/token", "application/x-www-form-urlencoded"),
    ],
)
@pytest.mark.parametrize("length", [None, "1", "2097152"])
async def test_actual_bytes_refused_before_parse_and_auth(app, bus, path, content_type, length):
    async def chunks():
        for _ in range(17):
            yield b" " * 65536

    headers = {"content-type": content_type}
    if length is not None:
        headers["content-length"] = length
    with (
        patch.object(Request, "json", side_effect=AssertionError("JSON parse reached")),
        patch.object(Request, "form", side_effect=AssertionError("form parse reached")),
        patch.object(bus.uow.users, "get", side_effect=AssertionError("storage reached")),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(path, content=chunks(), headers=headers)
    assert response.status_code == 413
    assert response.headers["cache-control"] == "private, no-store"


async def test_body_deadline_covers_all_chunks(app, monkeypatch):
    monkeypatch.setattr(fastapi_app, "HTTP_BODY_TIMEOUT_SECONDS", 0.05, raising=False)

    async def chunks():
        for _ in range(5):
            await asyncio.sleep(0.02)
            yield b" "

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/steps/", content=chunks(), headers={"content-type": "application/json"})
    assert response.status_code == 408
    assert response.headers["cache-control"] == "private, no-store"


async def test_small_invalid_json_still_uses_framework_validation(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/steps/", content=b"{", headers={"content-type": "application/json"})
    assert response.status_code == 422
