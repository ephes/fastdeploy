"""Credentials must survive the owning deployment lock wait."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from deploy import auth

pytestmark = [pytest.mark.asyncio, pytest.mark.db("in_memory")]


@pytest.mark.parametrize("operation", ["step", "finish"])
async def test_expiry_during_lock_wait_refuses_without_mutation(
    app, bus, publisher, deployment_in_db, valid_deploy_token_in_db, monkeypatch, operation
):
    entered, resume = asyncio.Event(), asyncio.Event()
    original = bus.uow.deployments.get_for_update

    async def wait_for_lock(deployment_id):
        entered.set()
        await resume.wait()
        return await original(deployment_id)

    monkeypatch.setattr(bus.uow.deployments, "get_for_update", wait_for_lock)
    initial_events = len(publisher.events)
    now = datetime.now(timezone.utc)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return now + timedelta(minutes=10)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        kwargs = {"headers": {"authorization": f"Bearer {valid_deploy_token_in_db}"}}
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
        with patch.object(bus.uow, "commit", wraps=bus.uow.commit) as commit:
            task = asyncio.create_task(client.request(method, path, **kwargs))
            try:
                await asyncio.wait_for(entered.wait(), 2)
                monkeypatch.setattr(auth, "datetime", Later)
            finally:
                resume.set()
            response = await asyncio.wait_for(task, 2)
            assert response.status_code == 401
            commit.assert_not_called()
        assert deployment_in_db.finished is None
        assert await bus.uow.steps.get_steps_by_deployment(deployment_in_db.id) == []
        assert len(publisher.events) == initial_events
        monkeypatch.setattr(auth, "datetime", datetime)
        first = await client.request(method, path, **kwargs)
        second = await client.request(method, path, **kwargs)
        assert first.status_code == second.status_code == 200


@pytest.mark.parametrize("operation", ["step", "finish"])
async def test_locked_mutation_refuses_credential_for_another_deployment(bus, deployment_in_db, operation):
    from deploy.auth import InvalidCredentials, create_access_token
    from deploy.domain import commands

    token = create_access_token({"type": "deployment", "deployment": deployment_in_db.id + 1}, timedelta(minutes=5))
    fields = {"deployment_id": deployment_in_db.id, "deployment_token": token}
    if operation == "step":
        now = datetime.now(timezone.utc)
        command = commands.ProcessStep(
            **fields, name="synthetic", state="success", started=now, finished=now, message="ok"
        )
    else:
        command = commands.FinishDeployment(**fields)
    with patch.object(bus.uow, "commit", wraps=bus.uow.commit) as commit:
        with pytest.raises(InvalidCredentials):
            await bus.handle(command)
        commit.assert_not_called()
    assert deployment_in_db.finished is None
    assert await bus.uow.steps.get_steps_by_deployment(deployment_in_db.id) == []
