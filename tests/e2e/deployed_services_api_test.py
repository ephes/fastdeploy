from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from deploy.auth import create_access_token
from deploy.domain import model

pytestmark = pytest.mark.asyncio


# test list_deployed_services endpoint


async def test_list_deployed_services_without_authentication(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(app.url_path_for("list_deployed_services"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.fixture
def valid_config_token(service):
    """Valid config token."""
    return create_access_token({"type": "config"}, timedelta(minutes=5))


async def test_list_deployed_services_happy(app, deployed_service_in_db, valid_config_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("list_deployed_services"),
            headers={"authorization": f"Bearer {valid_config_token}"},
        )

    assert response.status_code == 200
    result = response.json()
    deployed_service_from_api = model.DeployedService(**result[0])
    assert deployed_service_from_api == deployed_service_in_db


@pytest.mark.db("in_memory")
async def test_deployed_service_inventory_opt_in_cursor(app, uow, valid_config_token):
    expected = []
    async with uow:
        for index, deployment_id in enumerate((9, 4, 9, 4, 9), start=1):
            deployed_service = model.DeployedService(deployment_id=deployment_id, config={"example": index})
            await uow.deployed_services.add(deployed_service)
            expected.append(deployed_service.model_dump())
        await uow.commit()
    expected.reverse()

    path = app.url_path_for("list_deployed_services")
    headers = {"authorization": f"Bearer {valid_config_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unpaged = await client.get(path, headers=headers)
        assert unpaged.status_code == 200
        assert unpaged.json() == expected

        params = {"limit": 2}
        for offset in (0, 2, 4, 5):
            page = await client.get(path, headers=headers, params=params)
            assert page.status_code == 200
            assert page.headers["cache-control"] == "private, no-store"
            rows = page.json()
            assert rows == expected[offset : offset + 2]
            if rows:
                params["before_id"] = rows[-1]["id"]

        cursor_only = await client.get(path, headers=headers, params={"before_id": expected[0]["id"]})
        assert cursor_only.status_code == 200
        assert cursor_only.json() == expected[1:]

        for invalid in ({"limit": 0}, {"limit": 201}, {"before_id": 0}, {"before_id": 2**31}):
            response = await client.get(path, headers=headers, params=invalid)
            assert response.status_code == 422

        assert (await client.get(path, params={"limit": 2})).status_code == 401
