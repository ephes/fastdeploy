"""Synthetic connection interleavings; no transport or platform dependencies."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import BaseModel

from deploy.adapters import websocket as module
from deploy.adapters.websocket import ConnectionManager
from deploy.entrypoints import fastapi_app

pytestmark = pytest.mark.asyncio


class Frame(BaseModel):
    number: int


class Socket:
    def __init__(self, blocked=False):
        self.sent = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.blocked = blocked
        self.sending = False
        self.overlap = False
        self.closed = False

    async def accept(self):
        pass

    async def send_text(self, text):
        self.overlap |= self.sending
        self.sending = True
        self.entered.set()
        try:
            if self.blocked:
                await self.release.wait()
            self.sent.append(text)
        finally:
            self.sending = False

    async def send_json(self, message):
        await self.send_text(message)

    async def close(self, code=1000, reason=""):
        self.closed = True


@pytest.mark.parametrize("second", ["broadcast", "send", "authentication", "reject", "close"])
async def test_concurrent_sends_share_one_fifo(second, monkeypatch):
    cm = ConnectionManager()
    client_id = uuid4()
    socket = Socket(blocked=True)
    await cm.connect(client_id, socket)
    cm.active_connections[client_id] = socket
    first = asyncio.create_task(cm.broadcast(Frame(number=1)))
    await asyncio.wait_for(socket.entered.wait(), 1)
    if second == "broadcast":
        next_send = cm.broadcast(Frame(number=2))
    elif second == "send":
        next_send = cm.send(client_id, {"number": 2})
    elif second == "authentication":

        async def user(*args):
            return type("User", (), {"name": "synthetic"})()

        monkeypatch.setattr(module, "user_from_token", user)
        monkeypatch.setattr(module, "token_to_payload", lambda _: {"exp": datetime.now(timezone.utc).timestamp() + 60})
        next_send = cm.authenticate(client_id, "synthetic", None)
    elif second == "reject":
        next_send = cm.reject(client_id, "synthetic")
    else:
        next_send = cm.close(client_id, "synthetic")
    following = asyncio.create_task(next_send)
    try:
        # Let the independent publisher/control response reach the held send.
        for _ in range(8):
            await asyncio.sleep(0)
        assert not socket.overlap
        assert not socket.sent
        socket.release.set()
        await asyncio.wait_for(asyncio.gather(first, following), 1)
        assert len(socket.sent) == 2
        assert socket.sent[0] == Frame(number=1).model_dump_json()
    finally:
        socket.release.set()
        cm.disconnect(client_id, socket)
        await asyncio.gather(first, following, return_exceptions=True)


async def test_replacement_does_not_inherit_queued_frames_or_lock():
    cm = ConnectionManager()
    client_id = uuid4()
    old, new = Socket(blocked=True), Socket()
    await cm.connect(client_id, old)
    cm.active_connections[client_id] = old
    first = asyncio.create_task(cm.broadcast(Frame(number=1)))
    await asyncio.wait_for(old.entered.wait(), 1)
    queued = asyncio.create_task(cm.send(client_id, {"old": True}))
    for _ in range(8):
        await asyncio.sleep(0)
    cm.disconnect(client_id, old)
    await cm.connect(client_id, new)
    cm.active_connections[client_id] = new
    try:
        await asyncio.wait_for(cm.send(client_id, {"new": True}), 0.5)
        old.release.set()
        await asyncio.wait_for(asyncio.gather(first, queued), 1)
        assert old.sent == [Frame(number=1).model_dump_json()]
        assert new.sent == [{"new": True}]
    finally:
        old.release.set()
        cm.disconnect(client_id, new)
        await asyncio.gather(first, queued, return_exceptions=True)


async def test_lock_wait_is_inside_total_send_budget(monkeypatch):
    monkeypatch.setattr(module, "BROADCAST_SEND_TIMEOUT_SECONDS", 0.02)
    cm = ConnectionManager()
    client_id = uuid4()
    socket = Socket(blocked=True)
    await cm.connect(client_id, socket)
    cm.active_connections[client_id] = socket
    await asyncio.wait_for(asyncio.gather(cm.broadcast(Frame(number=1)), cm.broadcast(Frame(number=2))), 0.5)
    assert not socket.overlap
    assert socket.closed
    assert client_id not in cm.all_connections


async def test_lifespan_drains_only_owned_tasks_and_restarts_empty(monkeypatch):
    cm, other = ConnectionManager(), ConnectionManager()
    monkeypatch.setattr(fastapi_app, "connection_manager", cm, raising=False)
    monkeypatch.setattr(module, "SLOW_CLIENT_CLOSE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(module, "SHUTDOWN_TIMEOUT_SECONDS", 0.02, raising=False)

    class StuckClose(Socket):
        async def close(self, code=1000, reason=""):
            self.entered.set()
            await self.release.wait()
            self.closed = True

    socket, retired, unrelated = StuckClose(), StuckClose(), StuckClose()
    client_id, other_id = uuid4(), uuid4()
    await other.connect(other_id, unrelated)
    await other.close(other_id, "other application")
    try:
        async with fastapi_app.app.router.lifespan_context(fastapi_app.app):
            await cm.connect(client_id, socket)
            await cm.close_on_expire(client_id, datetime.now(timezone.utc) + timedelta(minutes=1))
            timer = cm.expiry_tasks[client_id]
            retired_id = uuid4()
            await cm.connect(retired_id, retired)
            await cm.close(retired_id, "old socket")
        assert timer.done()
        assert not cm.all_connections and not cm.active_connections
        assert not cm.expiry_tasks and not cm.close_tasks and not cm.owned_timers
        assert other.close_tasks  # application-local ownership
        async with fastapi_app.app.router.lifespan_context(fastapi_app.app):
            assert not cm.all_connections
            fresh = Socket()
            assert await cm.connect(uuid4(), fresh)
        assert fresh.closed
    finally:
        unrelated.release.set()
        socket.release.set()
        retired.release.set()
        # Clean the global pre-fix tasks too, so the red run leaks nothing.
        pending = set(getattr(module, "_pending_closes", set())) | set(getattr(other, "close_tasks", set()))
        await asyncio.gather(*pending, return_exceptions=True)


async def test_shutdown_tracks_expiry_already_inside_close(monkeypatch):
    cm = ConnectionManager()
    monkeypatch.setattr(module, "EXPIRY_GRACE_SECONDS", 0)
    monkeypatch.setattr(module, "SHUTDOWN_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(module, "SLOW_CLIENT_CLOSE_TIMEOUT_SECONDS", 0.01)

    class StuckClose(Socket):
        async def close(self, code=1000, reason=""):
            self.entered.set()
            await self.release.wait()

    socket = StuckClose()
    client_id = uuid4()
    await cm.connect(client_id, socket)
    await cm.close_on_expire(client_id, datetime.now(timezone.utc) + timedelta(milliseconds=1))
    timer = cm.expiry_tasks[client_id]
    await asyncio.wait_for(socket.entered.wait(), 1)
    assert client_id not in cm.expiry_tasks
    await asyncio.wait_for(cm.shutdown(), 0.5)
    assert timer.done()
    assert not cm.owned_timers and not cm.close_tasks
    # A late request-finally after shutdown cannot leave a detached close.
    await asyncio.wait_for(cm.close_socket(socket, 1000), 0.5)
    assert not cm.close_tasks


@pytest.mark.parametrize("final", ["close", "reject"])
@pytest.mark.parametrize("failure", ["timeout", "error", "cancel"])
async def test_failed_send_poisons_queue_before_unlock(monkeypatch, final, failure):
    cm = ConnectionManager()
    client_id = uuid4()
    monkeypatch.setattr(module, "BROADCAST_SEND_TIMEOUT_SECONDS", 0.03)

    class PartialFrame(Socket):
        def __init__(self):
            super().__init__()
            self.attempts = []

        async def send_text(self, text):
            self.attempts.append(text)
            self.entered.set()
            if len(self.attempts) == 1:
                await self.release.wait()
                raise OSError("partial frame")
            self.sent.append(text)

    socket = PartialFrame()
    await cm.connect(client_id, socket)
    cm.active_connections[client_id] = socket
    first = asyncio.create_task(cm.send(client_id, {"first": True}))
    await asyncio.wait_for(socket.entered.wait(), 1)
    # Give the final frame a later deadline than the send already in progress.
    monkeypatch.setattr(module, "BROADCAST_SEND_TIMEOUT_SECONDS", 0.3)
    closing = asyncio.create_task(getattr(cm, final)(client_id, "synthetic"))
    for _ in range(8):
        await asyncio.sleep(0)
    if failure == "error":
        socket.release.set()
    elif failure == "cancel":
        first.cancel()
    await asyncio.wait_for(asyncio.gather(first, closing, return_exceptions=True), 1)
    assert socket.attempts == [{"first": True}]
    assert not socket.sent
    assert socket.closed
    assert client_id not in cm.send_locks
