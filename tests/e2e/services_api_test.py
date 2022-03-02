import pytest

from httpx import AsyncClient
from sqlalchemy.orm.exc import NoResultFound


pytestmark = pytest.mark.anyio


async def test_get_services_without_authentication(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(app.url_path_for("get_services"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.db("database_url")
async def test_get_empty_list_of_services(app, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_services"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    result = response.json()
    assert result == []


async def test_get_services_happy(app, service_in_db, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_services"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    result = response.json()
    service_from_api = result[0]
    assert service_from_api["name"] == service_in_db.name


async def test_delete_service_without_authentication(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(app.url_path_for("delete_service", service_id=1))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.db("database_url")
async def test_delete_not_existingservice(app, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(
            app.url_path_for("delete_service", service_id=42),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Service does not exist"}


@pytest.mark.db("in_memory")
async def test_delete_service_happy(app, service_in_db, valid_access_token_in_db, publisher, uow):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(
            app.url_path_for("delete_service", service_id=service_in_db.id),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    # make sure delete was called properly
    assert response.status_code == 200
    result = response.json()
    assert result == {"detail": f"Service {service_in_db.id} deleted"}

    # make sure deleted service event was dispatched to event handlers
    [(message, delete_event)] = publisher.events
    assert "deleted" in message
    assert delete_event.id == service_in_db.id

    # make sure service_in_db is not in db anymore
    with uow as uow:
        with pytest.raises((NoResultFound, StopIteration)):
            [service] = uow.services.get(service_in_db.id)

    # FIXME: make sure deployments for this service are also removed
    # maybe just listen to the service delete event and run cleanup
    # function etc...
