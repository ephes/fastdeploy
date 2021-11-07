from unittest.mock import AsyncMock, patch

import pytest

from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_services_without_authentication(app, base_url):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(app.url_path_for("get_services"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_get_services(app, base_url, service_in_db, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(
            app.url_path_for("get_services"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    result = response.json()
    service_from_api = result[0]
    assert service_from_api["name"] == service_in_db.name


@pytest.mark.asyncio
async def test_create_service_without_authentication(app, base_url, service):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(app.url_path_for("create_service"), json=service.dict())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_create_service(app, base_url, repository, service, valid_access_token_in_db):
    service.id = given_id = -1
    connection_manager = AsyncMock()
    with patch("app.database.connection_manager", new=connection_manager):
        async with AsyncClient(app=app, base_url=base_url) as client:
            response = await client.post(
                app.url_path_for("create_service"),
                headers={"authorization": f"Bearer {valid_access_token_in_db}"},
                json=service.dict(),
            )

    assert response.status_code == 200

    # make sure added step was broadcast to websockets
    connection_manager.broadcast.assert_called()

    result = response.json()
    service_from_db = repository.get_service_by_name(result["name"])
    assert service_from_db.collect == service.collect
    assert service_from_db.deploy == service.deploy
    assert service_from_db.id != given_id


@pytest.mark.asyncio
async def test_delete_service_without_authentication(app, base_url, service):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.delete(app.url_path_for("delete_service", service_id=service.id))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_delete_service(app, base_url, repository, service_in_db, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.delete(
            app.url_path_for("delete_service", service_id=service_in_db.id),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    # make sure delete was called properly
    assert response.status_code == 200
    result = response.json()
    assert result == {"detail": f"Service {service_in_db.id} deleted"}

    # make sure service_in_db is not in db anymore
    assert repository.get_service_by_id(service_in_db.id) is None
