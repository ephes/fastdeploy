from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from deploy.bootstrap import get_bus
from deploy.entrypoints.dependencies import get_current_active_user
from deploy.entrypoints.routers import deployments, steps

MAX_ID = 2**31 - 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "parameter", "base_params", "page_view"),
    [
        ("/deployments/", "before_id", {}, "get_all_deployments"),
        ("/deployments/", "service_id", {}, "get_all_deployments"),
        ("/steps/", "before_id", {"deployment_id": 1}, "get_step_page"),
        ("/steps/", "deployment_id", {"before_id": 1}, "get_step_page"),
    ],
)
async def test_page_validates_database_identifiers_before_page_reads(
    monkeypatch, path, parameter, base_params, page_view
):
    app = FastAPI()
    app.include_router(deployments.router)
    app.include_router(steps.router)
    bus = Mock()
    app.dependency_overrides[get_bus] = lambda: bus
    app.dependency_overrides[get_current_active_user] = lambda: None
    read_page = AsyncMock(return_value=[])
    reconcile = AsyncMock()
    monkeypatch.setattr(deployments.views, page_view, read_page)
    monkeypatch.setattr(deployments, "reconcile_orphaned_deployments", reconcile)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for invalid_id in (0, MAX_ID + 1):
            response = await client.get(path, params={**base_params, parameter: invalid_id})
            assert response.status_code == 422
            assert response.json()["detail"][0]["loc"] == ["query", parameter]
            read_page.assert_not_awaited()
            reconcile.assert_not_awaited()

        for valid_id in (1, MAX_ID):
            response = await client.get(path, params={**base_params, parameter: valid_id})
            assert response.status_code == 200
            assert response.json() == []
            args, kwargs = read_page.await_args
            assert (args[0] if parameter == "deployment_id" else kwargs[parameter]) == valid_id
