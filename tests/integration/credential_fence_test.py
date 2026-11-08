"""Login checks current committed credentials after slow password work."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update

from deploy import auth
from deploy.adapters import orm
from deploy.bootstrap import get_bus
from deploy.domain.model import User
from deploy.entrypoints.fastapi_app import app

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("change", ["rotate", "delete", "replace", "unchanged"])
async def test_password_check_revalidates_current_identity(independent_bus, monkeypatch, change):
    login_bus, writer = await independent_bus(), await independent_bus()
    async with writer.uow as uow:
        await uow.users.add(User(name="sample", password=auth.get_password_hash("old")))
        await uow.commit()
    entered, resume = asyncio.Event(), asyncio.Event()
    original = auth._password_work

    async def paused(function, *args):
        result = await original(function, *args)
        entered.set()
        await resume.wait()
        return result

    monkeypatch.setattr(auth, "_password_work", paused)
    monkeypatch.setitem(app.dependency_overrides, get_bus, lambda: login_bus)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        request = asyncio.create_task(client.post("/token", data={"username": "sample", "password": "old"}))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            async with writer.uow as uow:
                if change == "rotate":
                    await uow.session.execute(update(orm.users).values(password=auth.get_password_hash("new")))
                elif change in ("delete", "replace"):
                    await uow.session.execute(delete(orm.users))
                    if change == "replace":
                        await uow.users.add(User(name="sample", password=auth.get_password_hash("old")))
                await uow.commit()
        finally:
            resume.set()
        response = await asyncio.wait_for(request, 5)
    assert response.status_code == (200 if change == "unchanged" else 401)
    assert ("access_token" in response.json()) == (change == "unchanged")
