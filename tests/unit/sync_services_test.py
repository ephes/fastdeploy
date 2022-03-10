import pytest

from deploy.domain import commands, model


# test domain.model.sync_services


def test_sync_services_add():
    services_from_db = []
    services_from_fs = [
        model.Service(name="bar", data={"description": "bar baz foo", "steps": []}),
    ]
    updated_services, deleted_services = model.sync_services(services_from_fs, services_from_db)
    assert updated_services == services_from_fs
    assert deleted_services == []


def test_sync_services_update():
    services_from_db = [
        model.Service(id=1, name="bar", data={"description": "bar baz foo", "steps": []}),
    ]
    services_from_fs = [
        model.Service(name="bar", data={"description": "foobar", "steps": [1]}),
    ]
    updated_services, deleted_services = model.sync_services(services_from_fs, services_from_db)
    assert updated_services == [model.Service(**{**services_from_fs[0].dict(), "id": 1})]
    assert deleted_services == []


def test_sync_services_delete():
    services_from_db = [
        model.Service(name="bar", data={"description": "bar baz foo", "steps": []}),
    ]
    services_from_fs = []
    updated_services, deleted_services = model.sync_services(services_from_fs, services_from_db)
    assert updated_services == []
    assert deleted_services == services_from_db


@pytest.fixture
def service_in_fs(services_filesystem):
    service_directory = services_filesystem.root / "fastdeploy"
    service_directory.mkdir()
    service_config = service_directory / "config.json"
    with service_config.open("w") as f:
        f.write("{}")
    return service_directory


@pytest.mark.asyncio
async def test_sync_services_integration(bus, uow, service_in_fs, service_in_db):
    cmd = commands.SyncServices()
    await bus.handle(cmd)
    async with uow:
        [[service]] = await uow.services.list()

    # make sure service_in_db is deleted
    assert service.name != service_in_db.name

    # make sure service_in_fs is added
    assert service.name == str(service_in_fs.name)
