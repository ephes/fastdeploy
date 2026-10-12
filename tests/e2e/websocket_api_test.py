import asyncio
import time
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect, WebSocketState

from deploy.adapters.websocket import ConnectionManager
from deploy.auth import create_access_token, get_password_hash
from deploy.bootstrap import bootstrap, get_bus
from deploy.domain import model
from deploy.entrypoints.fastapi_app import app as fastapi_app
from deploy.service_layer import unit_of_work


@pytest.fixture
def cm():
    return ConnectionManager()


@pytest.fixture
def ws_client(cm, services_filesystem):
    """
    Test client whose websocket endpoint uses a fresh connection manager and
    an in-memory unit of work containing one user.
    """
    uow = unit_of_work.InMemoryUnitOfWork()
    uow.users._users.append(model.User(id=1, name="user", password=get_password_hash("password")))

    async def noop_publish(*args):
        pass

    bus = asyncio.run(
        bootstrap(
            start_orm=False,
            create_db_and_tables=False,
            uow=uow,
            connection_manager=cm,
            publish=noop_publish,
            fs=services_filesystem,
        )
    )
    fastapi_app.dependency_overrides[get_bus] = lambda: bus
    with TestClient(fastapi_app) as client:
        yield client
    fastapi_app.dependency_overrides.pop(get_bus, None)


def user_token(name="user"):
    return create_access_token({"type": "user", "user": name}, timedelta(minutes=5))


def ws_path(client_id):
    return f"/deployments/ws/{client_id}"


def test_websocket_service_token_is_rejected_and_connection_released(ws_client, cm):
    client_id = uuid4()
    service_token = create_access_token({"type": "service", "service": "fastdeploytest"}, timedelta(minutes=5))
    with ws_client.websocket_connect(ws_path(client_id)) as ws:
        ws.send_json({"access_token": service_token})
        assert ws.receive_json()["status"] == "failure"
        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
        assert excinfo.value.code == 1008

    assert cm.all_connections == {}
    assert cm.active_connections == {}


def test_websocket_deleted_user_token_is_rejected_and_connection_released(ws_client, cm):
    client_id = uuid4()
    with ws_client.websocket_connect(ws_path(client_id)) as ws:
        ws.send_json({"access_token": user_token("deleted")})
        assert ws.receive_json()["status"] == "failure"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

    assert cm.all_connections == {}


def test_websocket_duplicate_client_id_cannot_take_over(ws_client, cm):
    client_id = uuid4()
    with ws_client.websocket_connect(ws_path(client_id)) as victim:
        victim.send_json({"access_token": user_token()})
        assert victim.receive_json()["status"] == "success"
        victim_connection = cm.all_connections[client_id]

        with pytest.raises(WebSocketDisconnect) as excinfo:  # noqa: SIM117
            with ws_client.websocket_connect(ws_path(client_id)) as attacker:
                attacker.receive_json()
        assert excinfo.value.code == 1008

        # the victim is still connected, authenticated and receives broadcasts
        assert cm.all_connections[client_id] is victim_connection
        assert cm.active_connections[client_id] is victim_connection
        victim.send_json({"ping": True})
        assert victim.receive_json() == {"message": "message from backend!"}

    assert cm.all_connections == {}
    assert cm.expiry_tasks == {}


def test_websocket_unauthenticated_client_cannot_trigger_broadcast(ws_client, cm):
    broadcasts = []

    async def record(message):
        broadcasts.append(message)

    cm.broadcast = record
    with ws_client.websocket_connect(ws_path(uuid4())) as ws:
        ws.send_json({"ping": True})
        ws.send_json({"ping": True})
    # the endpoint finishes the cleanup after the client is gone
    assert cm.all_connections == {}
    assert broadcasts == []


def test_websocket_client_id_is_reusable_after_disconnect(ws_client, cm):
    client_id = uuid4()
    for _ in range(2):
        with ws_client.websocket_connect(ws_path(client_id)) as ws:
            ws.send_json({"access_token": user_token()})
            assert ws.receive_json()["status"] == "success"
    assert cm.all_connections == {}
    assert cm.expiry_tasks == {}


def test_websocket_without_token_is_closed_after_the_authentication_deadline(ws_client, cm, monkeypatch):
    monkeypatch.setattr("deploy.entrypoints.fastapi_app.settings.websocket_auth_timeout_seconds", 0.2)
    with ws_client.websocket_connect(ws_path(uuid4())) as ws:
        ws.send_json({"ping": True})  # traffic without a token does not keep it open
        assert ws.receive_json() == {
            "type": "authentication",
            "status": "failure",
            "detail": "authentication timeout",
        }
        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
    assert excinfo.value.code == 1008
    assert cm.all_connections == {}


def test_websocket_with_token_stays_open_after_the_authentication_deadline(ws_client, cm, monkeypatch):
    monkeypatch.setattr("deploy.entrypoints.fastapi_app.settings.websocket_auth_timeout_seconds", 0.2)
    client_id = uuid4()
    with ws_client.websocket_connect(ws_path(client_id)) as ws:
        ws.send_json({"access_token": user_token()})
        assert ws.receive_json()["status"] == "success"
        time.sleep(0.6)
        assert cm.is_authenticated(client_id)
        ws.send_json({"ping": True})  # still served


def test_websocket_endpoint_returns_when_the_client_never_reads(cm, monkeypatch):
    """
    Neither the timeout notification nor the close can be sent: the endpoint
    still has to return, which is what releases the connection.
    """
    from deploy.adapters import websocket as websocket_module
    from deploy.entrypoints import fastapi_app as app_module

    monkeypatch.setattr(app_module.settings, "websocket_auth_timeout_seconds", 0.05)
    monkeypatch.setattr(websocket_module, "AUTH_TIMEOUT_CLOSE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(app_module, "WEBSOCKET_CLOSE_TIMEOUT_SECONDS", 0.05)

    class SilentWebsocket:
        """Accepts, never delivers a message and never gets a frame out."""

        client_state = application_state = WebSocketState.CONNECTED

        async def accept(self):
            pass

        async def receive_json(self):
            await asyncio.sleep(3600)

        async def send_json(self, message):
            await asyncio.sleep(3600)

        async def close(self, code=1000):
            await asyncio.sleep(3600)

    class StubBus:
        uow = None

    bus = StubBus()
    bus.cm = cm

    async def run():
        await asyncio.wait_for(app_module.websocket_endpoint(SilentWebsocket(), uuid4(), bus), timeout=5)

    asyncio.run(run())
    assert cm.all_connections == {}
