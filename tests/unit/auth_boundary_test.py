import asyncio
import logging
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import NoResultFound, OperationalError
from starlette.requests import Request

from deploy import auth
from deploy.config import settings
from deploy.entrypoints import dependencies
from deploy.entrypoints.routers import users
from deploy.login_throttle import login_throttle

pytestmark = [pytest.mark.asyncio, pytest.mark.db("in_memory")]


def outage():
    return OperationalError("private-query", {}, Exception("synthetic-secret"))


async def test_login_backend_failure_is_safe_and_does_not_consume_attempt(app, monkeypatch, caplog):
    monkeypatch.setattr(settings, "login_failure_limit", 1)
    monkeypatch.setattr(auth, "authenticate_user", AsyncMock(side_effect=outage()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with caplog.at_level(logging.ERROR):
            for _ in range(2):
                response = await client.post("/token", data={"username": "user", "password": "synthetic-secret"})
                assert response.status_code == 500
                assert "synthetic-secret" not in response.text
    assert "OperationalError" in caplog.text
    assert "synthetic-secret" not in caplog.text
    assert "private-query" not in caplog.text
    assert login_throttle.retry_after("user", "127.0.0.1") is None


@pytest.mark.parametrize(
    "getter,name",
    [
        (dependencies.get_current_active_user, "user_from_token"),
        (dependencies.get_current_active_service, "service_from_token"),
        (dependencies.get_current_active_deployment, "deployment_from_token"),
    ],
)
async def test_token_backend_errors_are_not_credentials(getter, name, monkeypatch):
    monkeypatch.setattr(dependencies, name, AsyncMock(side_effect=outage()))
    with pytest.raises(OperationalError):
        await getter("synthetic-token", SimpleNamespace(uow=object()))


async def test_missing_user_costs_dummy_check_but_backend_failure_does_not(monkeypatch):
    dummy = []
    monkeypatch.setattr(auth.PWD_CONTEXT, "dummy_verify", lambda: dummy.append(1))
    lookup = AsyncMock(side_effect=NoResultFound())
    monkeypatch.setattr(auth.views, "get_user_by_name", lookup)
    with pytest.raises(NoResultFound):
        await auth.authenticate_user("unknown", "password", object())
    assert dummy == [1]
    lookup.side_effect = outage()
    with pytest.raises(OperationalError):
        await auth.authenticate_user("unknown", "password", object())
    assert dummy == [1]


def request(address):
    return Request({"type": "http", "client": (address, 1234)})


def credentials():
    return SimpleNamespace(username="user", password="password")


@pytest.mark.parametrize("result", ["success", "failure", "backend", "cancel"])
async def test_global_admission_is_fail_fast_and_releases_capacity(monkeypatch, result):
    entered = asyncio.Event()
    finish = asyncio.Event()
    calls = []

    async def authenticate(*args):
        calls.append(args)
        if len(calls) == 2:
            entered.set()
        await finish.wait()
        if result == "failure":
            raise auth.InvalidCredentials("invalid password")
        if result == "backend":
            raise outage()
        return SimpleNamespace(name="user")

    monkeypatch.setattr(users, "login_capacity", threading.BoundedSemaphore(2))
    monkeypatch.setattr(auth, "authenticate_user", authenticate)
    bus = SimpleNamespace(uow=object())
    tasks = [asyncio.create_task(users.login_for_access_token(request(str(i)), credentials(), bus)) for i in range(2)]
    await asyncio.wait_for(entered.wait(), 2)
    with pytest.raises(HTTPException) as saturated:
        await users.login_for_access_token(request("third"), credentials(), bus)
    assert saturated.value.status_code == 429
    assert saturated.value.headers == {"Retry-After": "1"}
    assert len(calls) == 2
    if result == "cancel":
        for task in tasks:
            task.cancel()
    finish.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert users.login_capacity.acquire(blocking=False)
    assert users.login_capacity.acquire(blocking=False)
    assert not users.login_capacity.acquire(blocking=False)
    users.login_capacity.release()
    users.login_capacity.release()


async def test_cancellation_holds_capacity_until_real_hash_work_finishes(monkeypatch):
    entered = threading.Event()
    finish = threading.Event()

    def verify(*args):
        entered.set()
        assert finish.wait(5)
        return True

    monkeypatch.setattr(users, "login_capacity", threading.BoundedSemaphore(1))
    monkeypatch.setattr(
        auth.views, "get_user_by_name", AsyncMock(return_value=SimpleNamespace(id=1, name="user", password="hash"))
    )
    monkeypatch.setattr(auth, "verify_password", verify)
    task = asyncio.create_task(
        users.login_for_access_token(request("first"), credentials(), SimpleNamespace(uow=object()))
    )
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()  # repeated cancellation must not retire running hash work
        await asyncio.sleep(0)
        assert not users.login_capacity.acquire(blocking=False)
    finally:
        finish.set()
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert login_throttle.retry_after("user", "first") is None
    assert len(login_throttle._attempts[("pair", "user", "first")]) == 1
    assert not login_throttle._attempts[("pair", "user", "first")][0].pending
    assert users.login_capacity.acquire(blocking=False)
    users.login_capacity.release()


@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
async def test_login_holds_pair_reservation_across_window(monkeypatch, outcome):
    from deploy.login_throttle import LoginThrottle

    now = [1000.0]
    throttle = LoginThrottle(limit=1, address_limit=2, window_seconds=60, clock=lambda: now[0])
    monkeypatch.setattr(users, "login_throttle", throttle)
    monkeypatch.setattr(users, "login_capacity", threading.BoundedSemaphore(2))
    entered, finish = asyncio.Event(), asyncio.Event()

    async def authenticate(*args):
        entered.set()
        await finish.wait()
        if outcome == "failure":
            raise auth.InvalidCredentials("invalid password")
        return SimpleNamespace(name="user")

    monkeypatch.setattr(auth, "authenticate_user", authenticate)
    bus = SimpleNamespace(uow=object())
    task = asyncio.create_task(users.login_for_access_token(request("same"), credentials(), bus))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        now[0] += 120
        with pytest.raises(HTTPException) as refused:
            await users.login_for_access_token(request("same"), credentials(), bus)
        assert refused.value.status_code == 429
    finally:
        if outcome == "cancel":
            task.cancel()
        finish.set()
        await asyncio.gather(task, return_exceptions=True)
    assert throttle.retry_after("user", "same") is None
