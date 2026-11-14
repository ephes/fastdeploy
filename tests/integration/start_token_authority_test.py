import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from deploy import auth
from deploy.adapters import repository
from deploy.bootstrap import get_bus
from deploy.domain import commands, events, model
from deploy.entrypoints.fastapi_app import app

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("change", ["revoke", "delete_user", "expire_record", "unchanged"])
async def test_http_start_rechecks_after_waiting_for_service_lock(independent_bus, monkeypatch, change):
    setup = await independent_bus()
    service = model.Service(name="synthetic", data={})
    user = model.User(name="synthetic", password="unused")
    async with setup.uow as uow:
        await uow.services.add(service)
        await uow.users.add(user)
        await uow.commit()
    token, record = await auth.issue_service_token(
        service=service.name, user=user.name, origin="test", expires_delta=timedelta(minutes=5), uow=setup.uow
    )
    starter = await independent_bus()
    blocker = await independent_bus()
    entered = asyncio.Event()
    original = repository.SqlAlchemyServiceRepository.lock_for_deployment

    async def signal_lock(self, service_id):
        entered.set()
        await original(self, service_id)

    monkeypatch.setattr(repository.SqlAlchemyServiceRepository, "lock_for_deployment", signal_lock)
    launched = Mock(side_effect=lambda deployment, service: deployment.record(events.DeploymentStarted))
    monkeypatch.setattr(model.Deployment, "start_deployment_task", launched)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_bus] = lambda: starter
    try:
        async with blocker.uow:
            await original(blocker.uow.services, service.id)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                task = asyncio.create_task(
                    client.post("/deployments/", json={"env": {}}, headers={"Authorization": f"Bearer {token}"})
                )
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    if change == "revoke":
                        await setup.handle(commands.RevokeServiceToken(jti=record.jti))
                    elif change == "delete_user":
                        async with setup.uow as uow:
                            await uow.session.execute(delete(model.User).where(model.User.id == user.id))
                            await uow.commit()
                    elif change == "expire_record":
                        async with setup.uow as uow:
                            current = await uow.service_tokens.get_by_jti(record.jti, for_update=True)
                            current.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                            await uow.commit()
                finally:
                    await blocker.uow.rollback()
                response = await asyncio.wait_for(task, 5)
        assert response.status_code == (200 if change == "unchanged" else 401)
        assert launched.call_count == int(change == "unchanged")
        async with setup.uow as uow:
            assert len(await uow.deployments.list()) == int(change == "unchanged")
    finally:
        app.dependency_overrides = previous
