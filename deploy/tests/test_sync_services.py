import pytest

from ..models import Service


def test_sync_services_add(repository):
    services_from_db = []
    services_from_fs = [
        Service(name="bar", data={"description": "bar baz foo", "steps": []}),
    ]
    updated_services, deleted_services = repository.sync_services(services_from_fs, services_from_db)
    assert updated_services == services_from_fs
    assert deleted_services == []


def test_sync_services_update(repository):
    services_from_db = [
        Service(id=1, name="bar", data={"description": "bar baz foo", "steps": []}),
    ]
    services_from_fs = [
        Service(name="bar", data={"description": "foobar", "steps": [1]}),
    ]
    updated_services, deleted_services = repository.sync_services(services_from_fs, services_from_db)
    assert updated_services == [Service(**{**services_from_fs[0].dict(), "id": 1})]
    assert deleted_services == []


def test_sync_services_delete(repository):
    services_from_db = [
        Service(name="bar", data={"description": "bar baz foo", "steps": []}),
    ]
    services_from_fs = []
    updated_services, deleted_services = repository.sync_services(services_from_fs, services_from_db)
    assert updated_services == []
    assert deleted_services == services_from_db


@pytest.mark.asyncio
async def test_sync_services_integration(repository, service_in_db):
    services_from_db = [service_in_db]
    services_from_fs = [
        Service(name="bar", data={"description": "bar baz foo", "steps": []}),
    ]
    updated_services, deleted_services = repository.sync_services(services_from_fs, services_from_db)
    await repository.persist_synced_services(updated_services, deleted_services)
    assert (
        await repository.get_service_by_name(service_in_db.name) is None
    )  # name, because updated service has id 1, too
    assert await repository.get_service_by_name("bar") == services_from_fs[0]
