"""Cancelling source preparation must retain the real PostgreSQL sync fence."""

import asyncio
import threading

import pytest

from deploy import views
from deploy.domain import commands

pytestmark = pytest.mark.asyncio


async def test_cancelled_worker_retires_before_next_sync_can_read(
    independent_bus, services_filesystem, monkeypatch, publisher
):
    first, second, reader = [await independent_bus() for _ in range(3)]
    entered, second_read = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    calls = []
    loop_thread = threading.get_ident()

    def snapshot():
        assert threading.get_ident() != loop_thread
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(5)
            return [("cancelled", {})]
        loop.call_soon_threadsafe(second_read.set)
        return [("stable", {})]

    monkeypatch.setattr(services_filesystem, "get_configs", snapshot)
    cancelled = asyncio.create_task(first.handle(commands.SyncServices(force=True)))
    waiting = None
    try:
        await asyncio.wait_for(entered.wait(), 3)
        cancelled.cancel()
        await asyncio.sleep(0)
        cancelled.cancel()
        waiting = asyncio.create_task(second.handle(commands.SyncServices(force=True)))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(second_read.wait(), 0.1)
        assert not cancelled.done()
        assert publisher.events == []
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(cancelled, 3)
        result = await asyncio.wait_for(waiting, 3)
        assert result.updated == ["stable"]
        assert calls == [1, 2]
        assert [s.name for s in await views.all_synced_services(reader.uow)] == ["stable"]
    finally:
        release.set()
        await asyncio.gather(cancelled, *([waiting] if waiting else []), return_exceptions=True)
