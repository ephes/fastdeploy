from datetime import datetime, timedelta, timezone

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
    assert updated_services == [model.Service(**{**services_from_fs[0].model_dump(), "id": 1})]
    assert deleted_services == []


def test_sync_services_delete():
    services_from_db = [
        model.Service(name="bar", data={"description": "bar baz foo", "steps": []}),
    ]
    services_from_fs = []
    updated_services, deleted_services = model.sync_services(services_from_fs, services_from_db)
    assert updated_services == []
    assert deleted_services == services_from_db


# test domain.model.check_sync_deletions


def services(*names):
    return [model.Service(name=name) for name in names]


def test_check_sync_deletions_refuses_empty_source():
    target = services("a", "b", "c")
    with pytest.raises(model.ServiceSyncRefused) as exc_info:
        model.check_sync_deletions([], target, target, force=False)
    assert exc_info.value.would_delete == ["a", "b", "c"]
    assert exc_info.value.total == 3


def test_check_sync_deletions_refuses_more_than_half():
    target = services("a", "b", "c")
    with pytest.raises(model.ServiceSyncRefused):
        model.check_sync_deletions(services("a"), target, services("b", "c"), force=False)


def test_check_sync_deletions_allows_half():
    target = services("a", "b")
    model.check_sync_deletions(services("a"), target, services("b"), force=False)


def test_check_sync_deletions_allows_empty_source_and_target():
    model.check_sync_deletions([], [], [], force=False)


def test_check_sync_deletions_force():
    target = services("a", "b", "c")
    model.check_sync_deletions([], target, target, force=True)


# test the sync_services handler


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
    cmd = commands.SyncServices(force=True)
    result = await bus.handle(cmd)
    async with uow:
        [service] = await uow.services.list()

    # make sure service_in_db is deleted
    assert service.name != service_in_db.name

    # make sure service_in_fs is added
    assert service.name == str(service_in_fs.name)
    assert result == model.ServiceSyncResult(updated=[service_in_fs.name], deleted=[service_in_db.name], skipped=[])


@pytest.mark.asyncio
async def test_sync_services_adds_and_updates_without_force(bus, uow, services_filesystem, publisher):
    async with uow:
        await uow.services.add(model.Service(name="keep", data={"old": True}))
        await uow.services.add(model.Service(name="gone", data={}))
        await uow.services.add(model.Service(name="other", data={}))
        await uow.commit()
    for name in ("keep", "other", "new"):
        (services_filesystem.root / name).mkdir()
        (services_filesystem.root / name / "config.json").write_text("{}")

    result = await bus.handle(commands.SyncServices())

    assert sorted(result.updated) == ["keep", "new"]
    assert result.deleted == ["gone"]
    assert result.skipped == []
    async with uow:
        names = sorted(service.name for service in await uow.services.list())
    assert names == ["keep", "new", "other"]
    deleted_events = [event for _, event in publisher.events if getattr(event, "deleted", False)]
    assert [event.name for event in deleted_events] == ["gone"]


@pytest.mark.asyncio
async def test_sync_services_empty_directory_is_refused(bus, uow, service_in_db, publisher):
    with pytest.raises(model.ServiceSyncRefused) as exc_info:
        await bus.handle(commands.SyncServices())

    assert exc_info.value.would_delete == [service_in_db.name]
    async with uow:
        [service] = await uow.services.list()
    assert service.name == service_in_db.name
    assert publisher.events == []


@pytest.mark.asyncio
async def test_sync_services_empty_directory_force_deletes(bus, uow, service_in_db):
    result = await bus.handle(commands.SyncServices(force=True))

    assert result.deleted == [service_in_db.name]
    async with uow:
        assert await uow.services.list() == []


async def add_running_deployment(uow, service):
    deployment = model.Deployment(
        service_id=service.id, origin="test", user="test", started=datetime.now(timezone.utc), finished=None
    )
    async with uow:
        await uow.deployments.add(deployment)
        await uow.commit()
        step = model.Step(name="running step", state="running", deployment_id=deployment.id)
        await uow.steps.add(step)
        await uow.commit()
    return deployment


@pytest.mark.asyncio
async def test_sync_services_keeps_service_with_running_deployment(bus, uow, service_in_db, publisher):
    deployment = await add_running_deployment(uow, service_in_db)

    result = await bus.handle(commands.SyncServices(force=True))

    assert result.deleted == []
    assert result.skipped == [
        model.SkippedService(name=service_in_db.name, reason=f"deployment {deployment.id} is still running")
    ]
    async with uow:
        [service] = await uow.services.list()
        [kept] = await uow.deployments.get_by_service(service.id)
    assert service.name == service_in_db.name
    assert kept.id == deployment.id
    assert publisher.events == []


@pytest.mark.asyncio
async def test_sync_services_deletes_service_with_stale_deployment(bus, uow, service_in_db):
    deployment = await add_running_deployment(uow, service_in_db)
    async with uow:
        deployment.started = datetime.now(timezone.utc) - timedelta(days=2)
        await uow.deployments.add(deployment)
        await uow.commit()

    result = await bus.handle(commands.SyncServices(force=True))

    assert result.deleted == [service_in_db.name]
    assert result.skipped == []


@pytest.mark.asyncio
async def test_sync_services_deletes_service_with_orphaned_deployment(bus, uow, service_in_db):
    """An orphaned deployment (no open steps, no recent activity) does not count as running."""
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    deployment = model.Deployment(service_id=service_in_db.id, origin="test", user="test", started=old, finished=None)
    async with uow:
        await uow.deployments.add(deployment)
        await uow.commit()
        await uow.steps.add(
            model.Step(name="done", state="success", deployment_id=deployment.id, started=old, finished=old)
        )
        await uow.commit()

    result = await bus.handle(commands.SyncServices(force=True))

    assert result.deleted == [service_in_db.name]
    assert result.skipped == []


@pytest.mark.asyncio
async def test_sync_services_keeps_service_whose_deployment_reported_recently(bus, uow, service_in_db):
    """No open steps, but the last step was just reported: the deploy task may still be finishing."""
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    deployment = model.Deployment(service_id=service_in_db.id, origin="test", user="test", started=old, finished=None)
    async with uow:
        await uow.deployments.add(deployment)
        await uow.commit()
        await uow.steps.add(
            model.Step(
                name="done",
                state="success",
                deployment_id=deployment.id,
                started=old,
                finished=datetime.now(timezone.utc),
            )
        )
        await uow.commit()

    result = await bus.handle(commands.SyncServices(force=True))

    assert result.deleted == []
    assert result.skipped == [
        model.SkippedService(name=service_in_db.name, reason=f"deployment {deployment.id} is still running")
    ]
