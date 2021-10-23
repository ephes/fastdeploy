from uuid import uuid4

import pytest

from app.websocket import ConnectionManager


@pytest.mark.asyncio
async def test_websocket_authenticate_invalid_token(invalid_access_token, stub_websocket):
    cm = ConnectionManager()
    client_id = uuid4()
    cm.all_connections[client_id] = stub_websocket

    # make sure connection was not authenticated already
    assert client_id not in cm.active_connections

    await cm.authenticate(client_id, invalid_access_token)

    assert client_id not in cm.active_connections
    assert "failed" in stub_websocket.sent[0]["detail"]


@pytest.mark.asyncio
async def test_websocket_authenticate_valid_token(valid_access_token, stub_websocket):
    cm = ConnectionManager()
    client_id = uuid4()
    cm.all_connections[client_id] = stub_websocket

    # make sure connection was not authenticated already
    assert client_id not in cm.active_connections

    await cm.authenticate(client_id, valid_access_token)

    assert client_id in cm.active_connections
    assert "successful" in stub_websocket.sent[0]["detail"]
