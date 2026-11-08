"""Deleting a service retires its recorded authorization in the same transaction."""

import pytest
from httpx import ASGITransport, AsyncClient

from deploy import auth
from deploy.bootstrap import get_bus
from deploy.domain import commands, model
from deploy.entrypoints.fastapi_app import app

pytestmark = pytest.mark.asyncio


async def setup(independent_bus):
    bus = await independent_bus()
    async with bus.uow as uow:
        await uow.users.add(model.User(name="sample", password="fixture-hash"))
        service = model.Service(name="sample")
        await uow.services.add(service)
        await uow.commit()
    token, record = await auth.issue_service_token_for_existing(
        service="sample", user="sample", origin="fixture", days=1, uow=bus.uow
    )
    return bus, service, token, record


@pytest.mark.parametrize("method", ["delete", "sync"])
async def test_name_reuse_does_not_restore_old_deployment_authority(independent_bus, monkeypatch, method):
    bus, service, token, record = await setup(independent_bus)
    if method == "delete":
        await bus.handle(commands.DeleteService(service_id=service.id))
    else:
        await bus.handle(commands.SyncServices(force=True))
    async with bus.uow as uow:
        await uow.services.add(model.Service(name="sample"))
        await uow.commit()
    from unittest.mock import Mock

    from deploy import tasks

    launch = Mock()
    monkeypatch.setattr(tasks, "run_deploy", launch)
    monkeypatch.setitem(app.dependency_overrides, get_bus, lambda: bus)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/deployments/", json={}, headers={"authorization": f"Bearer {token}"})
    assert response.status_code == 401
    launch.assert_not_called()
    new_token, _ = await auth.issue_service_token_for_existing(
        service="sample", user="sample", origin="fixture", days=1, uow=bus.uow
    )
    assert (await auth.service_from_token(new_token, bus.uow)).name == "sample"
    async with bus.uow as uow:
        assert (await uow.service_tokens.get_by_jti(record.jti)).revoked


@pytest.mark.parametrize("method", ["delete", "sync"])
async def test_failed_service_deletion_rolls_back_token_retirement(independent_bus, monkeypatch, method):
    bus, service, token, record = await setup(independent_bus)
    reached = []

    async def fail_commit():
        await bus.uow.flush()
        assert (await bus.uow.service_tokens.get_by_jti(record.jti)).revoked
        reached.append(True)
        raise RuntimeError("synthetic commit failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(bus.uow, "_commit", fail_commit)
        with pytest.raises(RuntimeError, match="synthetic commit failure"):
            await bus.handle(
                commands.DeleteService(service_id=service.id)
                if method == "delete"
                else commands.SyncServices(force=True)
            )
    assert reached
    assert (await auth.service_from_token(token, bus.uow)).id == service.id
    async with bus.uow as uow:
        assert not (await uow.service_tokens.get_by_jti(record.jti)).revoked


@pytest.mark.parametrize("first", ["issuance", "deletion"])
async def test_issuance_and_deletion_share_service_lock(independent_bus, monkeypatch, first):
    import asyncio

    from deploy.adapters.repository import SqlAlchemyServiceRepository

    setup_bus, service, _, _ = await setup(independent_bus)
    issuer, deleter = await independent_bus(), await independent_bus()
    holder = issuer if first == "issuance" else deleter
    contender = deleter if first == "issuance" else issuer
    committed, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_commit = holder.uow._commit
    original_lock = SqlAlchemyServiceRepository.lock_for_deployment

    async def paused_commit():
        committed.set()
        await release.wait()
        await original_commit()

    async def observed_lock(self, service_id):
        if self.session is contender.uow.session:
            waiting.set()
        await original_lock(self, service_id)

    monkeypatch.setattr(holder.uow, "_commit", paused_commit)
    monkeypatch.setattr(SqlAlchemyServiceRepository, "lock_for_deployment", observed_lock)

    async def issue():
        return await auth.issue_service_token_for_existing(
            service="sample", user="sample", origin="race", days=1, uow=issuer.uow
        )

    async def remove():
        await deleter.handle(commands.DeleteService(service_id=service.id))

    first_task = asyncio.create_task(issue() if first == "issuance" else remove())
    second_task = None
    try:
        await asyncio.wait_for(committed.wait(), 5)
        second_task = asyncio.create_task(remove() if first == "issuance" else issue())
        await asyncio.wait_for(waiting.wait(), 5)
        assert not second_task.done()
    finally:
        release.set()
    results = await asyncio.wait_for(asyncio.gather(first_task, second_task, return_exceptions=True), 5)
    if first == "issuance":
        token, _record = results[0]
        assert results[1] is None
        with pytest.raises(auth.InvalidCredentials, match="revoked"):
            await auth.service_from_token(token, setup_bus.uow)
    else:
        assert results[0] is None
        assert isinstance(results[1], auth.ServiceTokenIssueRefused)
