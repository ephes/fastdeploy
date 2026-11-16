"""Real PostgreSQL row-lock wait must not extend a deployment credential."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from deploy import auth
from deploy.adapters import repository
from deploy.bootstrap import get_bus
from deploy.domain import model
from deploy.entrypoints.fastapi_app import app

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("operation", ["step", "finish"])
async def test_deployment_token_expiry_behind_postgres_lock(independent_bus, publisher, monkeypatch, operation):
    setup = await independent_bus()
    now = datetime.now(timezone.utc)
    async with setup.uow as uow:
        service = model.Service(name="synthetic-service", data={})
        await uow.services.add(service)
        await uow.flush()
        deployment = model.Deployment(service_id=service.id, user="synthetic", origin="fixture", started=now)
        await uow.deployments.add(deployment)
        await uow.commit()
    token = auth.create_access_token({"type": "deployment", "deployment": deployment.id}, timedelta(minutes=5))
    blocker = await independent_bus()
    request_bus = await independent_bus()
    entered = asyncio.Event()
    original = repository.SqlAlchemyDeploymentRepository.get_for_update

    async def locked_get(self, deployment_id):
        entered.set()
        return await original(self, deployment_id)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return now + timedelta(minutes=10)

    initial_events = len(publisher.events)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_bus] = lambda: request_bus
    task = None
    try:
        async with blocker.uow:
            await original(blocker.uow.deployments, deployment.id)
            monkeypatch.setattr(repository.SqlAlchemyDeploymentRepository, "get_for_update", locked_get)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                kwargs = {"headers": {"authorization": f"Bearer {token}"}}
                if operation == "step":
                    kwargs["json"] = {
                        "name": "synthetic",
                        "state": "success",
                        "started": now.isoformat(),
                        "finished": now.isoformat(),
                        "message": "ok",
                    }
                    method, path = "POST", "/steps/"
                else:
                    method, path = "PUT", "/deployments/finish/"
                task = asyncio.create_task(client.request(method, path, **kwargs))
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    # Observe actual DB contention, rather than relying on scheduler timing.
                    for _ in range(500):
                        waiting = await blocker.uow.connection.scalar(
                            text(
                                "select exists(select 1 from pg_locks where not granted and locktype='transactionid')"
                            )
                        )
                        if waiting:
                            break
                        await asyncio.sleep(0.01)
                    else:
                        raise AssertionError("mutation did not wait on the deployment row lock")
                    monkeypatch.setattr(auth, "datetime", Later)
                finally:
                    await blocker.uow.commit()
                response = await asyncio.wait_for(task, 5)
        assert response.status_code == 401
        assert len(publisher.events) == initial_events
        async with setup.uow:
            saved = await setup.uow.deployments.get(deployment.id)
            assert saved.finished is None
            assert await setup.uow.steps.get_steps_by_deployment(deployment.id) == []
    finally:
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
