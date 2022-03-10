from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from fastapi import WebSocket
from pydantic import BaseModel

from deploy.auth import create_access_token
from deploy.websocket import ConnectionManager


pytestmark = pytest.mark.asyncio


@pytest.fixture
def stub_websocket():
    class StubWebsocket:
        sent = []
        has_accepted = False

        async def send_json(self, message):
            self.sent.append(message)

        async def send_text(self, message):
            self.sent.append(message)

        async def accept(self):
            self.has_accepted = True

    return StubWebsocket()


async def test_websocket_connect(bus, stub_websocket):
    cm = ConnectionManager(bus)
    client_id = uuid4()
    await cm.connect(client_id, stub_websocket)
    assert client_id in cm.all_connections
    assert stub_websocket.has_accepted


async def test_websocket_disconnect(bus, stub_websocket):
    cm = ConnectionManager(bus)
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


@pytest.fixture
def invalid_access_token(user):
    return create_access_token({"type": "user", "user": user.name}, timedelta(minutes=-5))


async def test_websocket_authenticate_invalid_token(bus, invalid_access_token, stub_websocket):
    cm = ConnectionManager(bus)
    client_id = uuid4()
    cm.all_connections[client_id] = stub_websocket

    # make sure connection was not authenticated already
    assert client_id not in cm.active_connections

    await cm.authenticate(client_id, invalid_access_token)

    assert client_id not in cm.active_connections
    assert "failed" in stub_websocket.sent[0]["detail"]


async def test_websocket_authenticate_valid_token(bus, valid_access_token_in_db, stub_websocket):
    cm = ConnectionManager(bus)
    client_id = uuid4()
    cm.all_connections[client_id] = stub_websocket

    # mock close on expire to avoid cm.close was never awaited warning
    async def do_nothing(*args, **kwargs):
        ...

    cm.close_on_expire = do_nothing

    # make sure connection was not authenticated already
    assert client_id not in cm.active_connections

    await cm.authenticate(client_id, valid_access_token_in_db)

    assert client_id in cm.active_connections
    assert "successful" in stub_websocket.sent[0]["detail"]


@pytest.fixture
def test_message():
    class Message(BaseModel):
        test: str = "message"

    return Message()


async def test_broadcast_only_to_active_connections(bus, stub_websocket, test_message):
    client_id = uuid4()
    cm = ConnectionManager(bus)
    cm.all_connections[client_id] = stub_websocket

    await cm.broadcast(test_message)

    assert test_message.json() not in stub_websocket.sent

    cm.active_connections[client_id] = stub_websocket
    await cm.broadcast(test_message)
    assert test_message.json() in stub_websocket.sent


async def test_close_websocket_on_expire(bus):
    class StubWebsocket(WebSocket):
        def __init__(self):
            self.closed = False
            self.sent = []

        async def send_json(self, message):
            self.sent.append(message)

        async def close(self):
            self.closed = True

    websocket = StubWebsocket()
    client_id = uuid4()
    cm = ConnectionManager(bus)
    cm.all_connections[client_id] = websocket

    await cm.close_on_expire(client_id, datetime.now(timezone.utc))
    assert websocket.closed
    assert "expired" in websocket.sent[0]["detail"]
