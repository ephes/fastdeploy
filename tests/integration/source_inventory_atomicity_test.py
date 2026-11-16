"""Total-source refusal never becomes an authoritative deletion inventory."""

from datetime import datetime, timezone

import pytest

from deploy.adapters import filesystem
from deploy.domain import commands, model

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("limit", ["MAX_SOURCE_SERVICES", "MAX_SOURCE_BYTES", "MAX_SOURCE_WORK"])
async def test_total_source_refusal_preserves_all_committed_rows(
    independent_bus, services_filesystem, publisher, monkeypatch, force, limit
):
    setup, syncer = [await independent_bus() for _ in range(2)]
    now = datetime.now(timezone.utc)
    async with setup.uow as uow:
        for name in ("keep", "gone"):
            service = model.Service(name=name, data={"generation": "old"})
            await uow.services.add(service)
            await uow.flush()
            deployment = model.Deployment(service_id=service.id, origin="test", user="test", started=now, finished=now)
            await uow.deployments.add(deployment)
            await uow.flush()
            await uow.steps.add(
                model.Step(name="history", state="success", deployment_id=deployment.id, message="OLD")
            )
        await uow.commit()

    async def snapshot():
        async with setup.uow as uow:
            return (
                [s.model_dump() for s in await uow.services.list()],
                [d.model_dump() for d in await uow.deployments.list()],
                [s.model_dump() for s in await uow.steps.list()],
            )

    before = await snapshot()
    for name in ("keep", "new", "extra"):
        directory = services_filesystem.root / name
        directory.mkdir()
        (directory / "config.json").write_text('{"generation": "new"}')
    with monkeypatch.context() as scoped:
        scoped.setattr(filesystem, limit, 2)
        with pytest.raises(filesystem.ServiceConfigError):
            await syncer.handle(commands.SyncServices(force=force))
    assert await snapshot() == before
    assert publisher.events == []
    result = await syncer.handle(commands.SyncServices(force=True))
    assert result.deleted == ["gone"]
    assert sorted(result.updated) == ["extra", "keep", "new"]
