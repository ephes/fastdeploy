import asyncio
from threading import BoundedSemaphore
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from deploy import auth
from deploy.bootstrap import get_bus
from deploy.entrypoints.routers import users
from deploy.login_throttle import Attempt, LoginThrottle

pytestmark = pytest.mark.asyncio


@pytest.fixture
def graph(monkeypatch):
    # Keep the production route and Bus dependency graph, replacing only storage.
    app = FastAPI()
    app.include_router(users.router)
    acquisitions = []
    capacity = BoundedSemaphore(1)
    throttle = LoginThrottle(limit=1, address_limit=2)
    monkeypatch.setattr(users, "login_capacity", capacity)
    monkeypatch.setattr(users, "login_throttle", throttle)

    async def counting_bus():
        acquisitions.append("connect")
        try:
            yield SimpleNamespace(uow=object(), fs=None, cm=None, event_handlers={}, command_handlers={})
        finally:
            assert not capacity.acquire(blocking=False)  # slot survives DB cleanup
            acquisitions.append("close")

    app.dependency_overrides[get_bus] = counting_bus
    return app, acquisitions, capacity, throttle


async def post(app, *, username: str = "synthetic"):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/token", data={"username": username, "password": "invented"})


@pytest.mark.parametrize("reason", ["capacity", "throttle"])
async def test_refusal_precedes_database_acquisition(graph, monkeypatch, reason):
    app, acquisitions, capacity, throttle = graph
    authenticate = AsyncMock(return_value=SimpleNamespace(name="synthetic"))
    monkeypatch.setattr(auth, "authenticate_user", authenticate)
    if reason == "capacity":
        assert capacity.acquire(blocking=False)
    else:
        throttle.record_failure(throttle.begin_attempt("synthetic", "127.0.0.1"))
    try:
        response = await post(app)
        assert response.status_code == 429
        assert acquisitions == []
        authenticate.assert_not_called()
    finally:
        if reason == "capacity":
            capacity.release()


async def test_admitted_cancellation_releases_slot_after_database_cleanup(graph, monkeypatch):
    app, acquisitions, capacity, throttle = graph
    entered = asyncio.Event()

    async def authenticate(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(auth, "authenticate_user", authenticate)
    task = asyncio.create_task(post(app))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert acquisitions == ["connect", "close"]
    assert capacity.acquire(blocking=False)
    capacity.release()
    assert not throttle._attempts[("pair", "synthetic", "127.0.0.1")][0].pending


async def test_acquisition_failure_releases_admission_without_counting_a_password_failure(graph):
    app, _, capacity, throttle = graph

    async def broken_bus():
        raise RuntimeError("synthetic acquisition failure")

    app.dependency_overrides[get_bus] = broken_bus
    with pytest.raises(RuntimeError, match="synthetic acquisition failure"):
        await post(app)
    assert capacity.acquire(blocking=False)
    capacity.release()
    assert throttle.retry_after("synthetic", "127.0.0.1") is None


async def test_discard_failure_releases_login_capacity(graph, monkeypatch: pytest.MonkeyPatch) -> None:
    app, acquisitions, _, throttle = graph
    primary = RuntimeError("synthetic acquisition failure")
    cleanup = RuntimeError("synthetic discard failure")

    async def broken_bus() -> None:
        raise primary

    def broken_discard(attempt: Attempt) -> None:
        assert attempt.pending
        raise cleanup

    with monkeypatch.context() as overrides:
        overrides.setitem(app.dependency_overrides, get_bus, broken_bus)
        overrides.setattr(throttle, "discard_attempt", broken_discard)
        with pytest.raises(RuntimeError, match="synthetic discard failure") as raised:
            await post(app)
        assert raised.value is cleanup
        assert raised.value.__context__ is primary

    authenticate = AsyncMock(return_value=SimpleNamespace(name="next-user"))
    monkeypatch.setattr(auth, "authenticate_user", authenticate)
    response = await post(app, username="next-user")
    assert response.status_code == 200
    assert acquisitions == ["connect", "close"]


@pytest.mark.parametrize("outcome", ["success", "failure", "backend"])
async def test_completed_login_keeps_capacity_through_cleanup(graph, monkeypatch, outcome):
    app, acquisitions, capacity, _ = graph
    effects = {
        "success": None,
        "failure": auth.InvalidCredentials("synthetic failure"),
        "backend": RuntimeError("synthetic backend failure"),
    }
    monkeypatch.setattr(
        auth,
        "authenticate_user",
        AsyncMock(return_value=SimpleNamespace(name="synthetic"), side_effect=effects[outcome]),
    )
    if outcome == "backend":
        with pytest.raises(RuntimeError, match="synthetic backend failure"):
            await post(app)
    else:
        response = await post(app)
        assert response.status_code == (200 if outcome == "success" else 401)
    assert acquisitions == ["connect", "close"]
    assert capacity.acquire(blocking=False)
    capacity.release()


async def test_cancelled_acquisition_returns_pending_reservation(graph):
    app, _, capacity, throttle = graph
    entered = asyncio.Event()

    async def waiting_bus():
        entered.set()
        await asyncio.Event().wait()

    app.dependency_overrides[get_bus] = waiting_bus
    task = asyncio.create_task(post(app))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert capacity.acquire(blocking=False)
    capacity.release()
    assert throttle.retry_after("synthetic", "127.0.0.1") is None
