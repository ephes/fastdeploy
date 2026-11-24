import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect, WebSocketState

from deploy.adapters.websocket import ConnectionManager
from deploy.auth import create_access_token, get_password_hash
from deploy.bootstrap import bootstrap, get_bus
from deploy.config import settings
from deploy.domain import model
from deploy.entrypoints.fastapi_app import app as fastapi_app
from deploy.service_layer import unit_of_work


@pytest.fixture
def cm(monkeypatch):
    from deploy.entrypoints import fastapi_app

    manager = ConnectionManager()
    monkeypatch.setattr(fastapi_app, "connection_manager", manager)
    return manager


@pytest.fixture
def ws_client(cm, services_filesystem):
    """
    Test client whose websocket endpoint uses a fresh connection manager and
    an in-memory unit of work containing one user.
    """
    uow = unit_of_work.InMemoryUnitOfWork()

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
        uow.users._users.append(model.User(id=1, name="user", password=get_password_hash("password")))
        yield client
    fastapi_app.dependency_overrides.pop(get_bus, None)


def user_token(name="user"):
    return create_access_token({"type": "user", "user": name}, timedelta(minutes=5))


def ws_path(client_id):
    return f"/deployments/ws/{client_id}"


@pytest.mark.parametrize(
    ("expiry_case", "http_status", "ws_status"),
    [
        ("integer", 200, "success"),
        ("legacy-string", 200, "success"),
        ("invalid", 401, "failure"),
        ("expired", 401, "failure"),
        ("missing", 200, "failure"),
        ("out-of-range", 200, "failure"),
    ],
)
def test_user_token_expiry_admission(
    ws_client: TestClient, expiry_case: str, http_status: int, ws_status: str
) -> None:
    now = int(datetime.now(timezone.utc).timestamp())
    expiries = {
        "integer": now + 300,
        "legacy-string": str(now + 300),
        "invalid": f"{now + 300}.5",
        "expired": str(now - 60),
        "out-of-range": 10**20,
    }
    payload: dict[str, str | int] = {"type": "user", "user": "user"}
    if expiry_case != "missing":
        payload["exp"] = expiries[expiry_case]
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.token_sign_algorithm)
    assert ws_client.get("/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == http_status

    with patch("deploy.auth.jwt.decode", wraps=jwt.decode) as decode:
        with ws_client.websocket_connect(ws_path(uuid4())) as ws:
            ws.send_json({"access_token": token})
            assert ws.receive_json()["status"] == ws_status
            if ws_status == "failure":
                assert_refused(ws, 1008)
        decode.assert_called_once()


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


# --- authentication deadline ---


@pytest.fixture
def short_auth_deadline(monkeypatch):
    monkeypatch.setattr("deploy.entrypoints.fastapi_app.settings.websocket_auth_timeout_seconds", 0.2)


def test_websocket_without_token_is_closed_after_the_authentication_deadline(ws_client, cm, short_auth_deadline):
    with ws_client.websocket_connect(ws_path(uuid4())) as ws:
        ws.send_json({"ping": True})  # traffic without a token does not keep it open
        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
    assert excinfo.value.code == 1008
    assert excinfo.value.reason == "authentication timeout"
    assert cm.all_connections == {}


def test_websocket_with_token_stays_open_after_the_authentication_deadline(ws_client, cm, short_auth_deadline):
    client_id = uuid4()
    with ws_client.websocket_connect(ws_path(client_id)) as ws:
        ws.send_json({"access_token": user_token()})
        assert ws.receive_json()["status"] == "success"
        time.sleep(0.6)
        assert cm.is_authenticated(client_id)
        ws.send_json({"access_token": user_token()})  # still served
        assert ws.receive_json()["status"] == "success"


def test_websocket_authentication_deadline_covers_verifying_the_token(ws_client, cm, short_auth_deadline, monkeypatch):
    """A token sent in time does not help if looking up its user outlasts the deadline."""
    lookup_cancelled = False

    async def slow_user_from_token_with_expiry(token, uow):
        nonlocal lookup_cancelled
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            lookup_cancelled = True
            raise

    monkeypatch.setattr("deploy.adapters.websocket.user_from_token_with_expiry", slow_user_from_token_with_expiry)
    client_id = uuid4()
    with ws_client.websocket_connect(ws_path(client_id)) as ws:
        ws.send_json({"access_token": user_token()})
        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
    assert excinfo.value.code == 1008
    assert lookup_cancelled
    assert not cm.is_authenticated(client_id)
    assert cm.all_connections == {}
    assert cm.expiry_tasks == {}


def test_websocket_endpoint_lets_a_close_within_the_budget_finish(cm, monkeypatch):
    """
    A close which finishes within the cleanup budget keeps its code and reason.
    """
    from deploy.entrypoints import fastapi_app as app_module

    monkeypatch.setattr(app_module.settings, "websocket_auth_timeout_seconds", 0.05)

    class SilentWebsocket:
        """Accepts, never delivers a message and takes its time to close."""

        client_state = application_state = WebSocketState.CONNECTED
        closed_with = None

        async def accept(self):
            pass

        async def receive(self):
            await asyncio.sleep(3600)

        async def close(self, code=1000, reason=None):
            await asyncio.sleep(0.3)
            self.closed_with = (code, reason)

    class StubBus:
        uow = None

    bus = StubBus()
    bus.cm = cm
    websocket = SilentWebsocket()

    asyncio.run(asyncio.wait_for(app_module.websocket_endpoint(websocket, uuid4(), bus), timeout=5))

    assert websocket.closed_with == (1008, "authentication timeout")
    assert cm.all_connections == {}


@pytest.mark.asyncio
async def test_endpoint_cleanup_cannot_wait_forever_for_close(cm, monkeypatch):
    from deploy.adapters import websocket as websocket_module
    from deploy.entrypoints import fastapi_app as app_module

    monkeypatch.setattr(app_module.settings, "websocket_auth_timeout_seconds", 0.01)
    monkeypatch.setattr(websocket_module, "SLOW_CLIENT_CLOSE_TIMEOUT_SECONDS", 0.01)

    class StuckSocket:
        client_state = application_state = WebSocketState.CONNECTED
        close_cancelled = False
        close_finished = False

        def __init__(self):
            self.release_close = asyncio.Event()

        async def accept(self):
            pass

        async def receive(self):
            await asyncio.Event().wait()

        async def close(self, code=1000, reason=None):
            try:
                await self.release_close.wait()
                self.close_finished = True
            except asyncio.CancelledError:
                self.close_cancelled = True
                raise

    class StubBus:
        uow = None

    bus = StubBus()
    bus.cm = cm
    socket = StuckSocket()
    await asyncio.wait_for(app_module.websocket_endpoint(socket, uuid4(), bus), 0.5)
    assert not socket.close_cancelled
    assert not socket.close_finished
    assert cm.all_connections == cm.expiry_tasks == {}
    pending = set(cm.close_tasks)
    assert pending
    socket.release_close.set()
    await asyncio.wait_for(asyncio.gather(*pending), 0.5)
    assert socket.close_finished
    assert not cm.close_tasks


# --- control frame and connection admission ---


@pytest.fixture
def token_lookups(monkeypatch):
    """Record every token that reaches credential verification."""
    from deploy.adapters import websocket as websocket_module

    seen = []
    real = websocket_module.user_from_token_with_expiry

    async def recording_user_from_token_with_expiry(token, uow):
        seen.append(token)
        return await real(token, uow)

    monkeypatch.setattr(websocket_module, "user_from_token_with_expiry", recording_user_from_token_with_expiry)
    return seen


def assert_refused(ws, code):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        ws.receive_json()
    assert excinfo.value.code == code


@pytest.mark.parametrize(
    ("frame", "code"),
    [
        pytest.param('{"access_token": "' + "a" * 9000 + '"}', 1009, id="oversized"),
        pytest.param("[" * 4000 + "]" * 4000, 1008, id="deeply-nested"),
        pytest.param('{"access_token": "x", "access_token": "y"}', 1008, id="duplicate-token-members"),
        pytest.param('{"access_token": 1}', 1008, id="non-string-token"),
        pytest.param('{"access_token": ""}', 1008, id="empty-token"),
        pytest.param('{"access_token": "' + "a" * 4097 + '"}', 1008, id="overlong-token"),
        pytest.param("not json", 1008, id="invalid-json"),
        pytest.param("[1, 2]", 1008, id="not-an-object"),
    ],
)
def test_websocket_refuses_inadmissible_frames_before_authentication(ws_client, cm, token_lookups, frame, code):
    with ws_client.websocket_connect(ws_path(uuid4())) as ws:
        ws.send_text(frame)
        assert_refused(ws, code)
    assert token_lookups == []
    assert cm.all_connections == {}


def test_websocket_refuses_binary_frames_before_authentication(ws_client, cm, token_lookups):
    with ws_client.websocket_connect(ws_path(uuid4())) as ws:
        ws.send_bytes(b'{"access_token": "x"}')
        assert_refused(ws, 1008)
    assert token_lookups == []
    assert cm.all_connections == {}


def test_websocket_refuses_inadmissible_frames_after_authentication(ws_client, cm, token_lookups):
    client_id = uuid4()
    with ws_client.websocket_connect(ws_path(client_id)) as ws:
        ws.send_json({"access_token": user_token()})
        assert ws.receive_json()["status"] == "success"
        ws.send_text('{"access_token": "x", "access_token": "y"}')
        assert_refused(ws, 1008)
    assert len(token_lookups) == 1
    assert cm.all_connections == cm.active_connections == {}


def test_websocket_admits_a_token_at_the_length_limit(ws_client, cm, token_lookups):
    with ws_client.websocket_connect(ws_path(uuid4())) as ws:
        ws.send_json({"access_token": "a" * 4096})
        assert ws.receive_json()["status"] == "failure"  # admitted, then refused by verification
    assert token_lookups == ["a" * 4096]


@pytest.fixture
def connection_limits(monkeypatch):
    def apply(total, unauthenticated, per_address=65536):
        monkeypatch.setattr("deploy.adapters.websocket.settings.websocket_max_connections", total)
        monkeypatch.setattr(
            "deploy.adapters.websocket.settings.websocket_max_unauthenticated_per_address", per_address
        )
        monkeypatch.setattr(
            "deploy.adapters.websocket.settings.websocket_max_unauthenticated_connections", unauthenticated
        )

    return apply


def assert_connection_refused(client, code=1013):
    with pytest.raises(WebSocketDisconnect) as excinfo:  # noqa: SIM117
        with client.websocket_connect(ws_path(uuid4())) as ws:
            ws.receive_json()
    assert excinfo.value.code == code


def test_websocket_unauthenticated_connections_are_capped(ws_client, cm, connection_limits):
    connection_limits(total=10, unauthenticated=2)
    with ws_client.websocket_connect(ws_path(uuid4())) as first, ws_client.websocket_connect(ws_path(uuid4())):
        assert_connection_refused(ws_client)
        assert len(cm.all_connections) == 2
        # authenticating releases the unauthenticated slot
        first.send_json({"access_token": user_token()})
        assert first.receive_json()["status"] == "success"
        with ws_client.websocket_connect(ws_path(uuid4())):
            assert len(cm.all_connections) == 3
            assert_connection_refused(ws_client)
    assert cm.all_connections == {}
    # capacity returns once the connections are gone
    with ws_client.websocket_connect(ws_path(uuid4())), ws_client.websocket_connect(ws_path(uuid4())):
        pass


def test_websocket_total_connections_are_capped(ws_client, cm, connection_limits):
    connection_limits(total=2, unauthenticated=2)
    with (
        ws_client.websocket_connect(ws_path(uuid4())) as first,
        ws_client.websocket_connect(ws_path(uuid4())) as second,
    ):
        for ws in (first, second):
            ws.send_json({"access_token": user_token()})
            assert ws.receive_json()["status"] == "success"
        assert_connection_refused(ws_client)
        assert len(cm.active_connections) == 2
    assert cm.all_connections == {}


def test_websocket_unauthenticated_connections_per_address_are_capped(ws_client, cm, connection_limits):
    connection_limits(total=10, unauthenticated=10, per_address=1)
    with ws_client.websocket_connect(ws_path(uuid4())) as first:
        assert_connection_refused(ws_client)
        first.send_json({"access_token": user_token()})
        assert first.receive_json()["status"] == "success"
        with ws_client.websocket_connect(ws_path(uuid4())):
            assert len(cm.all_connections) == 2
