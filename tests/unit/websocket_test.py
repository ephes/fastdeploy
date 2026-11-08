import asyncio
from datetime import datetime, timedelta, timezone
from typing import ClassVar
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import WebSocket
from pydantic import BaseModel

from deploy.adapters import websocket as websocket_module
from deploy.adapters.websocket import ConnectionManager
from deploy.auth import create_access_token
from deploy.domain import model

pytestmark = pytest.mark.asyncio


@pytest.fixture
def stub_websocket():
    class StubWebsocket:
        sent: ClassVar[list] = []
        has_accepted = False

        async def send_json(self, message):
            self.sent.append(message)

        async def send_text(self, message):
            self.sent.append(message)

        async def accept(self):
            self.has_accepted = True

    return StubWebsocket()


async def test_websocket_connect(stub_websocket):
    cm = ConnectionManager()
    client_id = uuid4()
    await cm.connect(client_id, stub_websocket)
    assert client_id in cm.all_connections
    assert stub_websocket.has_accepted


async def test_websocket_disconnect(stub_websocket):
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


@pytest.fixture
def invalid_access_token(user):
    return create_access_token({"type": "user", "user": user.name}, timedelta(minutes=-5))


async def test_websocket_authenticate_invalid_token(uow, invalid_access_token, stub_websocket):
    cm = ConnectionManager()
    client_id = uuid4()
    cm.all_connections[client_id] = stub_websocket

    # make sure connection was not authenticated already
    assert client_id not in cm.active_connections

    await cm.authenticate(client_id, invalid_access_token, uow)

    assert client_id not in cm.active_connections
    assert "failed" in stub_websocket.sent[0]["detail"]


async def test_websocket_authenticate_valid_token(uow, valid_access_token_in_db, stub_websocket):
    cm = ConnectionManager()
    client_id = uuid4()
    cm.all_connections[client_id] = stub_websocket

    # mock close on expire to avoid cm.close was never awaited warning
    async def do_nothing(*args, **kwargs): ...

    cm.close_on_expire = do_nothing

    # make sure connection was not authenticated already
    assert client_id not in cm.active_connections

    await cm.authenticate(client_id, valid_access_token_in_db, uow)

    assert client_id in cm.active_connections
    assert "successful" in stub_websocket.sent[0]["detail"]


@pytest.fixture
def test_message():
    class Message(BaseModel):
        test: str = "message"

    return Message()


async def test_broadcast_only_to_active_connections(stub_websocket, test_message):
    client_id = uuid4()
    cm = ConnectionManager()
    cm.all_connections[client_id] = stub_websocket

    await cm.broadcast(test_message)

    assert test_message.model_dump_json() not in stub_websocket.sent

    cm.active_connections[client_id] = stub_websocket
    await cm.broadcast(test_message)
    assert test_message.model_dump_json() in stub_websocket.sent


async def test_close_websocket_on_expire():
    class StubWebsocket(WebSocket):
        def __init__(self):
            self.closed = False
            self.sent = []

        async def send_json(self, message):
            self.sent.append(message)

        async def close(self, code=1000, reason=None):
            self.closed = True

    websocket = StubWebsocket()
    client_id = uuid4()
    cm = ConnectionManager()
    cm.all_connections[client_id] = websocket

    await cm.close_on_expire(client_id, datetime.now(timezone.utc))
    assert websocket.closed
    assert "expired" in websocket.sent[0]["detail"]


class RecordingWebsocket:
    """Websocket stub recording what the server does with it."""

    def __init__(self, fail_on_send=False):
        self.sent = []
        self.accepted = False
        self.closed = False
        self.close_code = None
        self.fail_on_send = fail_on_send

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        if self.fail_on_send:
            raise RuntimeError("connection is gone")
        self.sent.append(message)

    async def send_text(self, message):
        if self.fail_on_send:
            raise RuntimeError("connection is gone")
        self.sent.append(message)

    async def close(self, code=1000, reason=None):
        self.closed = True
        self.close_code = code


def assert_forgotten(cm, client_id):
    assert client_id not in cm.all_connections
    assert client_id not in cm.active_connections
    assert client_id not in cm.principals
    assert client_id not in cm.expiry_tasks


async def test_websocket_authenticate_with_service_token_closes_and_cleans_up(uow, valid_service_token_in_db):
    cm = ConnectionManager()
    client_id = uuid4()
    websocket = RecordingWebsocket()
    await cm.connect(client_id, websocket)

    authenticated = await cm.authenticate(client_id, valid_service_token_in_db, uow)

    assert not authenticated
    assert websocket.sent[0]["status"] == "failure"
    assert websocket.closed
    assert websocket.close_code == 1008
    assert_forgotten(cm, client_id)


async def test_websocket_authenticate_with_token_of_deleted_user_closes_and_cleans_up(uow, valid_access_token):
    # valid_access_token belongs to a user that is not in the database
    cm = ConnectionManager()
    client_id = uuid4()
    websocket = RecordingWebsocket()
    await cm.connect(client_id, websocket)

    authenticated = await cm.authenticate(client_id, valid_access_token, uow)

    assert not authenticated
    assert websocket.sent[0]["status"] == "failure"
    assert websocket.closed
    assert_forgotten(cm, client_id)


async def test_websocket_authenticate_with_garbage_token_closes_and_cleans_up(uow):
    cm = ConnectionManager()
    client_id = uuid4()
    websocket = RecordingWebsocket()
    await cm.connect(client_id, websocket)

    assert not await cm.authenticate(client_id, {"not": "a token"}, uow)  # type: ignore[arg-type]

    assert websocket.closed
    assert_forgotten(cm, client_id)


async def test_websocket_connect_refuses_duplicate_client_id():
    cm = ConnectionManager()
    client_id = uuid4()
    victim, attacker = RecordingWebsocket(), RecordingWebsocket()
    assert await cm.connect(client_id, victim)
    cm.active_connections[client_id] = victim

    assert not await cm.connect(client_id, attacker)

    assert not attacker.accepted
    assert attacker.closed
    assert attacker.close_code == 1008
    assert cm.all_connections[client_id] is victim
    assert cm.active_connections[client_id] is victim


async def test_websocket_disconnect_of_stale_connection_keeps_newer_connection():
    cm = ConnectionManager()
    client_id = uuid4()
    old, new = RecordingWebsocket(), RecordingWebsocket()
    await cm.connect(client_id, old)
    cm.disconnect(client_id, old)
    await cm.connect(client_id, new)

    # a late cleanup of the old connection must not remove the new one
    assert not cm.disconnect(client_id, old)
    assert cm.all_connections[client_id] is new
    # disconnect is idempotent
    cm.disconnect(client_id, new)
    cm.disconnect(client_id, new)
    assert_forgotten(cm, client_id)


@pytest_asyncio.fixture(loop_scope="function")
async def other_user_token_in_db(bus):
    other = model.User(name="other", password="unused")
    async with bus.uow as uow:
        await uow.users.add(other)
        await uow.commit()
    return create_access_token({"type": "user", "user": other.name}, timedelta(minutes=5))


async def test_websocket_reauthenticate_as_different_user_is_rejected(
    uow, valid_access_token_in_db, other_user_token_in_db
):
    cm = ConnectionManager()
    client_id = uuid4()
    websocket = RecordingWebsocket()
    await cm.connect(client_id, websocket)
    assert await cm.authenticate(client_id, valid_access_token_in_db, uow)
    assert cm.principals[client_id] == "user"

    assert not await cm.authenticate(client_id, other_user_token_in_db, uow)

    assert websocket.sent[-1]["status"] == "failure"
    assert websocket.closed
    assert_forgotten(cm, client_id)


async def test_websocket_reauthenticate_replaces_expiry_timer(uow, valid_access_token_in_db):
    cm = ConnectionManager()
    client_id = uuid4()
    websocket = RecordingWebsocket()
    await cm.connect(client_id, websocket)

    assert await cm.authenticate(client_id, valid_access_token_in_db, uow)
    first_timer = cm.expiry_tasks[client_id]
    assert await cm.authenticate(client_id, valid_access_token_in_db, uow)
    second_timer = cm.expiry_tasks[client_id]
    await asyncio.sleep(0)  # let the cancellation happen

    assert first_timer is not second_timer
    assert first_timer.cancelled()
    assert not second_timer.done()

    cm.disconnect(client_id, websocket)
    await asyncio.sleep(0)
    assert second_timer.cancelled()
    assert_forgotten(cm, client_id)


async def test_websocket_stale_expiry_timer_does_not_close_new_connection():
    cm = ConnectionManager()
    client_id = uuid4()
    old, new = RecordingWebsocket(), RecordingWebsocket()
    await cm.connect(client_id, old)
    # a timer for the old connection which survived somehow
    stale = asyncio.create_task(cm._close_after(client_id, old, 0, "expired"))
    cm.disconnect(client_id, old)
    await cm.connect(client_id, new)

    await stale

    assert not new.closed
    assert cm.all_connections[client_id] is new


async def test_websocket_expiry_closes_connection_and_cleans_up():
    cm = ConnectionManager()
    client_id = uuid4()
    websocket = RecordingWebsocket()
    await cm.connect(client_id, websocket)
    cm.active_connections[client_id] = websocket
    cm.principals[client_id] = "user"

    await cm.close_on_expire(client_id, datetime.now(timezone.utc))

    assert websocket.closed
    assert "expired" in websocket.sent[0]["detail"]
    assert_forgotten(cm, client_id)


async def test_broadcast_continues_after_failing_connection(test_message):
    cm = ConnectionManager()
    broken, healthy = RecordingWebsocket(fail_on_send=True), RecordingWebsocket()
    for socket in (broken, healthy):
        client_id = uuid4()
        await cm.connect(client_id, socket)
        cm.active_connections[client_id] = socket

    await cm.broadcast(test_message)

    assert healthy.sent == [test_message.model_dump_json()]


async def test_websocket_failing_authentication_does_not_touch_replacement_connection(
    uow, valid_access_token, monkeypatch
):
    """
    While the token of the old connection is being verified, the old connection
    goes away (e.g. its session expires) and a new connection reuses the id.
    The failing verification must reject only the old connection.
    """
    cm = ConnectionManager()
    client_id = uuid4()
    old, new = RecordingWebsocket(), RecordingWebsocket()
    await cm.connect(client_id, old)
    cm.active_connections[client_id] = old
    cm.principals[client_id] = "user"

    async def user_from_token_with_replacement(token, uow):
        await cm.close(client_id, "Your session has expired.")
        await cm.connect(client_id, new)
        raise LookupError("user was deleted")

    monkeypatch.setattr(websocket_module, "user_from_token", user_from_token_with_replacement)

    assert not await cm.authenticate(client_id, valid_access_token, uow)

    assert old.closed
    assert old.sent[-1]["type"] == "warning"  # stale rejection sends no further frame
    assert not new.closed
    assert new.sent == []
    assert cm.all_connections[client_id] is new


async def test_websocket_successful_authentication_does_not_touch_replacement_connection(
    uow, valid_access_token_in_db, monkeypatch
):
    cm = ConnectionManager()
    client_id = uuid4()
    old, new = RecordingWebsocket(), RecordingWebsocket()
    await cm.connect(client_id, old)
    original_user_from_token = websocket_module.user_from_token

    async def user_from_token_with_replacement(token, uow):
        cm.disconnect(client_id, old)
        await cm.connect(client_id, new)
        return await original_user_from_token(token, uow)

    monkeypatch.setattr(websocket_module, "user_from_token", user_from_token_with_replacement)

    assert not await cm.authenticate(client_id, valid_access_token_in_db, uow)

    assert not cm.is_authenticated(client_id)
    assert cm.all_connections[client_id] is new
    assert new.sent == []
    assert client_id not in cm.expiry_tasks


class StuckWebsocket(RecordingWebsocket):
    """A client that never takes what the server sends (full send buffer)."""

    def __init__(self, stuck_close=False):
        super().__init__()
        self.stuck_close = stuck_close
        self.send_cancelled = False
        self.close_cancelled = False
        self.release_close = asyncio.Event()

    async def send_text(self, message):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.send_cancelled = True
            raise

    async def close(self, code=1000, reason=None):
        if self.stuck_close:
            try:
                await self.release_close.wait()
            except asyncio.CancelledError:
                self.close_cancelled = True
                raise
        await super().close(code=code, reason=reason)


@pytest.fixture
def short_broadcast_budget(monkeypatch):
    monkeypatch.setattr(websocket_module, "BROADCAST_SEND_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(websocket_module, "SLOW_CLIENT_CLOSE_TIMEOUT_SECONDS", 0.2)


async def test_broadcast_slow_client_does_not_block_healthy_clients(test_message, short_broadcast_budget):
    cm = ConnectionManager()
    slow_id, healthy_id = uuid4(), uuid4()
    slow, healthy = StuckWebsocket(), RecordingWebsocket()
    for client_id, websocket in ((slow_id, slow), (healthy_id, healthy)):  # the slow client comes first
        await cm.connect(client_id, websocket)
        cm.active_connections[client_id] = websocket
        cm.principals[client_id] = "user"

    broadcast = asyncio.create_task(cm.broadcast(test_message))
    # the healthy client gets the event while the slow send is still pending
    await asyncio.sleep(0.05)
    assert healthy.sent == [test_message.model_dump_json()]
    assert not broadcast.done()

    # the broadcast itself is bounded, the publisher is not held indefinitely
    await asyncio.wait_for(broadcast, timeout=2)

    assert slow.send_cancelled
    assert slow.closed
    assert slow.close_code == 1013
    assert_forgotten(cm, slow_id)
    assert slow_id not in cm.principals
    assert cm.active_connections == {healthy_id: healthy}

    # later broadcasts work and no longer wait for the removed client
    await asyncio.wait_for(cm.broadcast(test_message), timeout=0.1)
    assert healthy.sent == [test_message.model_dump_json()] * 2


async def test_broadcast_is_bounded_when_slow_client_does_not_close_either(test_message, short_broadcast_budget):
    cm = ConnectionManager()
    slow_id = uuid4()
    slow = StuckWebsocket(stuck_close=True)
    await cm.connect(slow_id, slow)
    cm.active_connections[slow_id] = slow

    await asyncio.wait_for(cm.broadcast(test_message), timeout=2)

    assert not slow.closed
    assert not slow.close_cancelled
    assert_forgotten(cm, slow_id)
    pending = set(cm.close_tasks)
    assert pending
    slow.release_close.set()
    await asyncio.wait_for(asyncio.gather(*pending), 0.5)
    assert slow.closed
    assert not cm.close_tasks


async def test_broadcast_timeout_does_not_remove_replacement_connection(test_message, short_broadcast_budget):
    """The slow connection goes away and its client id is reused while the send is pending."""
    cm = ConnectionManager()
    client_id = uuid4()
    slow, replacement = StuckWebsocket(), RecordingWebsocket()
    await cm.connect(client_id, slow)
    cm.active_connections[client_id] = slow

    broadcast = asyncio.create_task(cm.broadcast(test_message))
    await asyncio.sleep(0.05)
    cm.disconnect(client_id, slow)
    await cm.connect(client_id, replacement)
    cm.active_connections[client_id] = replacement
    await asyncio.wait_for(broadcast, timeout=2)

    assert cm.all_connections == {client_id: replacement}
    assert cm.active_connections == {client_id: replacement}


async def test_broadcast_keeps_event_order_per_client(short_broadcast_budget):
    class Numbered(BaseModel):
        number: int

    cm = ConnectionManager()
    healthy = RecordingWebsocket()
    client_id = uuid4()
    await cm.connect(client_id, healthy)
    cm.active_connections[client_id] = healthy

    for number in range(5):
        await cm.broadcast(Numbered(number=number))

    assert healthy.sent == [Numbered(number=number).model_dump_json() for number in range(5)]


class StuckControlWebsocket(RecordingWebsocket):
    def __init__(self, stuck_send=False, stuck_close=False):
        super().__init__()
        self.stuck_send = stuck_send
        self.stuck_close = stuck_close
        self.send_started = asyncio.Event()
        self.send_cancelled = False
        self.close_started = False
        self.close_cancelled = False
        self.release_close = asyncio.Event()

    async def send_json(self, message):
        self.send_started.set()
        if self.stuck_send:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.send_cancelled = True
                raise
        await super().send_json(message)

    async def close(self, code=1000, reason=None):
        self.close_started = True
        if self.stuck_close:
            try:
                await self.release_close.wait()
            except asyncio.CancelledError:
                self.close_cancelled = True
                raise
        await super().close(code, reason)


@pytest.mark.parametrize("operation", ["expiry", "reject", "duplicate"])
@pytest.mark.parametrize("stuck_send,stuck_close", [(True, False), (False, True), (True, True)])
async def test_control_cleanup_has_send_and_close_deadlines(monkeypatch, operation, stuck_send, stuck_close):
    monkeypatch.setattr(websocket_module, "BROADCAST_SEND_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(websocket_module, "SLOW_CLIENT_CLOSE_TIMEOUT_SECONDS", 0.01)
    cm = ConnectionManager()
    client_id = uuid4()
    socket = StuckControlWebsocket(stuck_send, stuck_close)
    await cm.connect(client_id, socket)
    cm.active_connections[client_id] = socket
    cm.principals[client_id] = "user"
    await cm.close_on_expire(client_id, datetime.now(timezone.utc) + timedelta(minutes=1))
    expiry_task = cm.expiry_tasks[client_id]
    if operation == "expiry":
        await asyncio.wait_for(cm.close_on_expire(client_id, datetime.now(timezone.utc)), 0.5)
    elif operation == "reject":
        await asyncio.wait_for(cm.reject(client_id, "bad token", socket), 0.5)
    else:
        duplicate = StuckControlWebsocket(stuck_close=stuck_close)
        assert not await asyncio.wait_for(cm.connect(client_id, duplicate), 0.5)
        assert cm.all_connections[client_id] is socket
        assert duplicate.close_started
        assert not duplicate.close_cancelled
        duplicate.release_close.set()
        await asyncio.sleep(0)
        cm.disconnect(client_id, socket)
        await asyncio.sleep(0)
        assert expiry_task.cancelled()
        return
    await asyncio.sleep(0)
    assert expiry_task.cancelled()
    assert_forgotten(cm, client_id)
    assert socket.send_cancelled == stuck_send
    assert socket.close_started
    assert not socket.close_cancelled
    socket.release_close.set()
    await asyncio.sleep(0)


async def test_control_timeout_preserves_replacement(monkeypatch):
    monkeypatch.setattr(websocket_module, "BROADCAST_SEND_TIMEOUT_SECONDS", 0.01)
    cm = ConnectionManager()
    client_id = uuid4()
    old, replacement = StuckControlWebsocket(stuck_send=True), RecordingWebsocket()
    await cm.connect(client_id, old)
    closing = asyncio.create_task(cm.close(client_id, "expired"))
    await old.send_started.wait()
    await cm.connect(client_id, replacement)
    await asyncio.wait_for(closing, 0.5)
    assert old.close_started
    assert cm.all_connections[client_id] is replacement
    assert not replacement.closed


@pytest.mark.db("in_memory")
async def test_reauthentication_success_send_is_bounded(uow, valid_access_token_in_db, monkeypatch):
    monkeypatch.setattr(websocket_module, "BROADCAST_SEND_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(websocket_module, "SLOW_CLIENT_CLOSE_TIMEOUT_SECONDS", 0.01)
    cm = ConnectionManager()
    socket = StuckControlWebsocket()
    client_id = uuid4()
    await cm.connect(client_id, socket)
    assert await cm.authenticate(client_id, valid_access_token_in_db, uow)
    first_expiry = cm.expiry_tasks[client_id]
    socket.stuck_send = socket.stuck_close = True
    assert not await asyncio.wait_for(cm.authenticate(client_id, valid_access_token_in_db, uow), 0.5)
    assert first_expiry.cancelled()
    assert socket.send_cancelled and not socket.close_cancelled
    socket.release_close.set()
    await asyncio.sleep(0)
    assert_forgotten(cm, client_id)


@pytest.mark.parametrize("error_type", [OSError, RuntimeError])
async def test_broadcast_error_forgets_state_once_without_receive_disconnect(test_message, error_type):
    cm = ConnectionManager()
    failed_id, healthy_id = uuid4(), uuid4()

    class Broken(RecordingWebsocket):
        sends = 0
        closes = 0

        async def send_text(self, message):
            self.sends += 1
            raise error_type("synthetic send failure")

        async def close(self, code=1000, reason=None):
            self.closes += 1
            await super().close(code, reason)

    broken, healthy = Broken(), RecordingWebsocket()
    for client_id, ws in ((failed_id, broken), (healthy_id, healthy)):
        await cm.connect(client_id, ws)
        cm.active_connections[client_id] = ws
        cm.principals[client_id] = "synthetic"
    await cm.close_on_expire(failed_id, datetime.now(timezone.utc) + timedelta(minutes=1))
    expiry = cm.expiry_tasks[failed_id]

    await cm.broadcast(test_message)
    await asyncio.wait_for(asyncio.gather(expiry, return_exceptions=True), 1)
    assert expiry.cancelled()
    assert_forgotten(cm, failed_id)
    assert broken.close_code == 1013
    await cm.broadcast(test_message)
    assert (broken.sends, broken.closes) == (1, 1)
    assert healthy.sent == [test_message.model_dump_json()] * 2
    assert cm.principals == {healthy_id: "synthetic"}
    cm.disconnect(healthy_id, healthy)


@pytest.mark.parametrize("error_type", [OSError, RuntimeError])
async def test_broadcast_error_preserves_replacement_and_its_expiry(test_message, error_type):
    cm = ConnectionManager()
    client_id = uuid4()
    entered, release = asyncio.Event(), asyncio.Event()

    class FailingLater(RecordingWebsocket):
        async def send_text(self, message):
            entered.set()
            await release.wait()
            raise error_type("synthetic stale send failure")

    old, replacement = FailingLater(), RecordingWebsocket()
    await cm.connect(client_id, old)
    cm.active_connections[client_id] = old
    broadcasting = asyncio.create_task(cm.broadcast(test_message))
    await asyncio.wait_for(entered.wait(), 1)
    cm.disconnect(client_id, old)
    await cm.connect(client_id, replacement)
    cm.active_connections[client_id] = replacement
    cm.principals[client_id] = "replacement"
    await cm.close_on_expire(client_id, datetime.now(timezone.utc) + timedelta(minutes=1))
    expiry = cm.expiry_tasks[client_id]
    try:
        release.set()
        await asyncio.wait_for(broadcasting, 1)
        assert cm.all_connections == {client_id: replacement}
        assert cm.active_connections == {client_id: replacement}
        assert cm.principals == {client_id: "replacement"}
        assert cm.expiry_tasks == {client_id: expiry}
        assert not expiry.done()
        assert old.closed and not replacement.closed
    finally:
        cm.disconnect(client_id, replacement)
        await asyncio.gather(expiry, return_exceptions=True)


async def test_broadcast_error_close_wait_is_bounded(test_message, short_broadcast_budget):
    cm = ConnectionManager()
    client_id = uuid4()

    class BrokenWithStuckClose(StuckWebsocket):
        async def send_text(self, message):
            raise OSError("synthetic send failure")

    broken = BrokenWithStuckClose(stuck_close=True)
    await cm.connect(client_id, broken)
    cm.active_connections[client_id] = broken
    try:
        await asyncio.wait_for(cm.broadcast(test_message), 1)
        assert_forgotten(cm, client_id)
        assert not broken.closed
        assert not broken.close_cancelled
    finally:
        broken.release_close.set()
        pending = set(cm.close_tasks)
        await asyncio.wait_for(asyncio.gather(*pending), 1)
    assert broken.closed
    assert not cm.close_tasks
