import pytest

from httpx import AsyncClient
from sqlalchemy.orm.exc import NoResultFound


pytestmark = pytest.mark.asyncio


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


async def test_get_service_names_without_authentication(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(app.url_path_for("get_service_names"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


async def test_get_service_names_happy(app, valid_access_token_in_db, services_filesystem):
    (services_filesystem.root / "fastdeploy").mkdir()  # create service directory
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            app.url_path_for("get_service_names"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    result = response.json()
    assert "fastdeploy" in result


async def test_delete_service_without_authentication(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(app.url_path_for("delete_service", service_id=1))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.db("database_url")
async def test_delete_non_existing_service(app, valid_access_token_in_db):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(
            app.url_path_for("delete_service", service_id=42),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Service does not exist"}


@pytest.mark.db("in_memory")
async def test_delete_service_happy(app, service_in_db, valid_access_token_in_db, publisher, uow):
    async with uow as uow:
        print("begin of test services: ", await uow.services.list())
        print("begin of test users: ", await uow.users.list())
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
    assert delete_event.service_id == service_in_db.id

    # make sure service_in_db is not in db anymore
    async with uow as uow:
        with pytest.raises((NoResultFound, StopIteration, RuntimeError)):
            [service] = await uow.services.get(service_in_db.id)

    # FIXME: make sure deployments for this service are also removed
    # maybe just listen to the service delete event and run cleanup
    # function etc...


async def test_sync_services_without_authentication(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(app.url_path_for("sync_services"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.fixture
def service_in_fs(services_filesystem):
    service_directory = services_filesystem.root / "fastdeploy"
    service_directory.mkdir()
    service_config = service_directory / "config.json"
    with service_config.open("w") as f:
        f.write("{}")
    return service_directory


async def test_sync_services_happy(app, uow, valid_access_token_in_db, service_in_fs):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            app.url_path_for("sync_services"),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    result = response.json()
    assert result == {"detail": "Services synced"}
    async with uow:
        [service] = await uow.services.get_by_name(service_in_fs.name)
    assert service.name == service_in_fs.name
