"""Sync ownership includes source reads, including an initially empty database."""

import asyncio

import pytest

from deploy import views
from deploy.domain import commands, model


@pytest.mark.asyncio
async def test_waiting_sync_reads_source_only_after_previous_commit(independent_bus, monkeypatch):
    first, second, reader = [await independent_bus() for _ in range(3)]
    captured = asyncio.Event()
    release = asyncio.Event()
    second_read = asyncio.Event()
    source = [model.Service(name="keep", data={"generation": "old"}), model.Service(name="gone")]
    calls = 0

    async def snapshot(fs):
        nonlocal calls
        calls += 1
        result = [model.Service(name=s.name, data=dict(s.data)) for s in source]
        if calls == 1:
            captured.set()
            await release.wait()
        else:
            second_read.set()
        return result

    monkeypatch.setattr(views, "get_services_from_filesystem", snapshot)
    older = asyncio.create_task(first.handle(commands.SyncServices(force=True)))
    await asyncio.wait_for(captured.wait(), 5)
    newer = asyncio.create_task(second.handle(commands.SyncServices(force=True)))
    try:
        # A blocked lock must not permit even the second source read.
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(second_read.wait(), 0.2)
        source[:] = [model.Service(name="keep", data={"generation": "new"})]
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(older, newer), 5)
    assert results[0].deleted == []
    assert results[1].deleted == ["gone"]
    async with reader.uow as uow:
        rows = await uow.services.list()
    assert [(s.name, s.data) for s in rows] == [("keep", {"generation": "new"})]
