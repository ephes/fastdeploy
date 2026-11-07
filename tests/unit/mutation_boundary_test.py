"""Production HTTP mutation errors with synthetic in-memory records."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from deploy.domain import commands

pytestmark = [pytest.mark.asyncio, pytest.mark.db("in_memory")]


@pytest.mark.parametrize("operation", ["delete", "finish", "start"])
async def test_commit_failure_is_server_error(
    operation,
    app,
    bus,
    service_in_db,
    deployment_in_db,
    valid_access_token_in_db,
    valid_service_token_in_db,
    valid_deploy_token_in_db,
    monkeypatch,
):
    commit = AsyncMock(side_effect=OperationalError("synthetic-private-query", {}, Exception("synthetic-secret")))
    monkeypatch.setattr(bus.uow, "commit", commit)
    if operation == "delete":
        # An existing finished deployment does not block deletion.
        deployment_in_db.finished = deployment_in_db.started
        method, url, token = "DELETE", f"/services/{service_in_db.id}", valid_access_token_in_db
    elif operation == "finish":
        method, url, token = "PUT", "/deployments/finish/", valid_deploy_token_in_db
    else:
        deployment_in_db.finished = deployment_in_db.started
        method, url, token = "POST", "/deployments/", valid_service_token_in_db
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.request(method, url, headers={"Authorization": f"Bearer {token}"})
    assert commit.await_count == 1  # the injected fault actually ran
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


async def test_delete_missing_service_is_still_404(app, valid_access_token_in_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete(
            "/services/987", headers={"Authorization": f"Bearer {valid_access_token_in_db}"}
        )
    assert response.status_code == 404
    assert response.json() == {"detail": "Service does not exist"}


async def test_missing_finish_after_authentication_is_still_404(app, bus, valid_deploy_token_in_db, monkeypatch):
    # A row may disappear between token resolution and the mutation.
    from deploy import views

    handle = AsyncMock(side_effect=views.DeploymentNotFound(1))
    monkeypatch.setitem(bus.command_handlers, commands.FinishDeployment, handle)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(
            "/deployments/finish/", headers={"Authorization": f"Bearer {valid_deploy_token_in_db}"}
        )
    assert response.status_code == 404


async def test_missing_service_after_authentication_is_404(app, bus, valid_service_token_in_db, monkeypatch):
    from sqlalchemy.exc import NoResultFound

    handle = AsyncMock(side_effect=NoResultFound())
    monkeypatch.setitem(bus.command_handlers, commands.StartDeployment, handle)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/deployments/", headers={"Authorization": f"Bearer {valid_service_token_in_db}"})
    handle.assert_awaited_once()
    assert response.status_code == 404
    assert response.json() == {"detail": "Service not found"}
