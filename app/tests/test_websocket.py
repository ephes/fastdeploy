from uuid import uuid4

import pytest

from app.websocket import ConnectionManager


@pytest.mark.asyncio
async def test_websocket_connect(stub_websocket):
    cm = ConnectionManager()
    client_id = uuid4()
    await cm.connect(client_id, stub_websocket)
    assert client_id in cm.all_connections
    assert stub_websocket.has_accepted


def test_websocket_disconnect(stub_websocket):
    cm = ConnectionManager()
    client_id = uuid4()

    # inactive connection
    cm.all_connections[client_id] = stub_websocket

    cm.disconnect(client_id)

    assert client_id not in cm.all_connections

    # active connection
    cm.all_connections[client_id] = stub_websocket
    cm.active_connections[client_id] = stub_websocket

    cm.disconnect(client_id)

    assert client_id not in cm.all_connections
    assert client_id not in cm.active_connections


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
async def test_websocket_authenticate_valid_token(valid_access_token_in_db, stub_websocket):
    cm = ConnectionManager()
    client_id = uuid4()
    cm.all_connections[client_id] = stub_websocket

    # make sure connection was not authenticated already
    assert client_id not in cm.active_connections

    await cm.authenticate(client_id, valid_access_token_in_db)

    assert client_id in cm.active_connections
    assert "successful" in stub_websocket.sent[0]["detail"]


@pytest.mark.asyncio
async def test_broadcast_only_to_active_connections(stub_websocket, test_message):
    client_id = uuid4()
    cm = ConnectionManager()
    cm.all_connections[client_id] = stub_websocket

    await cm.broadcast(test_message)

    assert test_message.json() not in stub_websocket.sent

    cm.active_connections[client_id] = stub_websocket
    await cm.broadcast(test_message)
    assert test_message.json() in stub_websocket.sent
