# ruff: noqa: F811  (imported pytest fixtures)
"""Signed malformed numeric dates are credential errors on real transports."""

import json
from uuid import uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from starlette.websockets import WebSocketDisconnect

from deploy.config import settings
from tests.e2e.websocket_api_test import cm, ws_client, ws_path  # noqa: F401


class ExponentJSON(json.JSONEncoder):
    def encode(self, value):
        return super().encode(value).replace("Infinity", "1e999")


def signed(claim, value, exponent=False):
    return jwt.encode(
        {"type": "user", "user": "user", "exp": 4102444800, claim: value},
        settings.secret_key,
        algorithm="HS256",
        json_encoder=ExponentJSON if exponent else None,
    )


BAD_DATES = [float("inf"), float("-inf"), float("nan"), True, 4102444800.5]


@pytest.mark.asyncio
@pytest.mark.db("in_memory")
@pytest.mark.parametrize("claim", ["iat", "exp"])
@pytest.mark.parametrize("value", BAD_DATES)
async def test_http_numeric_date_refusal(app, user_in_db, claim, value):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/users/me", headers={"authorization": f"Bearer {signed(claim, value)}"})
    assert response.status_code == 401


@pytest.mark.parametrize("claim", ["iat", "exp"])
@pytest.mark.parametrize("value", BAD_DATES)
def test_websocket_numeric_date_refusal(ws_client, cm, claim, value):
    with ws_client.websocket_connect(ws_path(uuid4())) as ws:
        ws.send_json({"access_token": signed(claim, value)})
        assert ws.receive_json()["status"] == "failure"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert cm.all_connections == {}


@pytest.mark.asyncio
@pytest.mark.db("in_memory")
@pytest.mark.parametrize("claim", ["iat", "exp"])
async def test_http_overflow_exponent(app, claim):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/users/me", headers={"authorization": f"Bearer {signed(claim, float('inf'), True)}"}
        )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.db("in_memory")
@pytest.mark.parametrize("value", [4102444800, 4102444800.0, "4102444800"])
async def test_integral_dates_remain_supported(app, user_in_db, value):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/users/me", headers={"authorization": f"Bearer {signed('exp', value)}"})
    assert response.status_code == 200
