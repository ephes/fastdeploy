from unittest.mock import patch

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
async def test_create_non_existing_service(app, base_url, service, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.post(
            app.url_path_for("create_service"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
            json=service.dict(),
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Service does not exists"}


@pytest.mark.asyncio
async def test_create_service(app, base_url, repository, handler, service, valid_access_token_in_db):
    service.id = given_id = -1
    print("service: ", service.dict())
    with (
        patch("app.database.get_directories", return_value=["fastdeploytest"]),
        patch("app.database.get_service_config", return_value={"steps": []}),
    ):
        async with AsyncClient(app=app, base_url=base_url) as client:
            response = await client.post(
                app.url_path_for("create_service"),
                headers={"authorization": f"Bearer {valid_access_token_in_db}"},
                json=service.dict(),
            )

    result = response.json()
    print("result: ", result)

    assert response.status_code == 200

    # make sure added step was dispatched to event handlers
    assert handler.last_event.name == service.name

    result = response.json()
    service_from_db = await repository.get_service_by_name(result["name"])
    assert service_from_db.id != given_id


@pytest.mark.asyncio
async def test_delete_service_without_authentication(app, base_url, service):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.delete(app.url_path_for("delete_service", service_id=service.id))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_delete_service(
    app, base_url, repository, handler, service_in_db, deployment_in_db, valid_access_token_in_db
):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.delete(
            app.url_path_for("delete_service", service_id=service_in_db.id),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    # make sure delete was called properly
    assert response.status_code == 200
    result = response.json()
    assert result == {"detail": f"Service {service_in_db.id} deleted"}

    # make sure added step was dispatched to event handlers
    assert handler.last_event.name == service_in_db.name

    # make sure service_in_db is not in db anymore
    assert await repository.get_service_by_id(service_in_db.id) is None

    # make sure deployment_in_db is not in db anymore
    assert await repository.get_deployment_by_id(deployment_in_db.id) is None