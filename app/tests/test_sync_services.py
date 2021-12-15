from ..models import Service


def test_sync_services_add(repository):
    services_from_db = []
    services_from_fs = [
        Service(name="bar", data={"description": "bar baz foo", "steps": []}),
    ]
    updated_services, deleted_services = repository.sync_services(services_from_fs, services_from_db)
    assert updated_services == services_from_fs
    assert deleted_services == []
