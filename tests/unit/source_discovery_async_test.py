"""Source threads may not block the loop or outlive their sync ownership."""

import asyncio
import threading
from unittest.mock import AsyncMock

import anyio.to_thread
import pytest

from deploy import views
from deploy.domain import commands
from deploy.service_layer.handlers import sync_services


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["names", "configs"])
async def test_source_discovery_does_not_block_independent_async_marker(kind):
    entered, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()
    observed = []

    class Source:
        def read(self):
            loop.call_soon_threadsafe(entered.set)
            observed.append(threading.get_ident())
            # A bounded fallback makes the regression fail rather than deadlock
            # when the old implementation runs this directly on the event loop.
            assert release.wait(1), "async marker could not run while source was reading"
            return []

        list = get_configs = read

    async def marker():
        await entered.wait()
        release.set()

    check = asyncio.create_task(marker())
    try:
        result = await (
            views.get_service_names(Source()) if kind == "names" else views.get_services_from_filesystem(Source())
        )
        assert result == []
        assert observed and observed[0] != loop_thread
    finally:
        release.set()
        await check


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_fails", [False, True])
async def test_repeated_cancellation_waits_for_source_and_keeps_capacity(in_memory_uow, monkeypatch, worker_fails):
    limiter = anyio.to_thread.current_default_thread_limiter()
    previous_tokens = limiter.total_tokens
    limiter.total_tokens = 1
    entered, release, second_entered = threading.Event(), threading.Event(), threading.Event()
    rollback = AsyncMock(wraps=in_memory_uow.rollback)
    commit = AsyncMock(wraps=in_memory_uow.commit)
    monkeypatch.setattr(in_memory_uow, "rollback", rollback)
    monkeypatch.setattr(in_memory_uow, "commit", commit)
    loop_thread = threading.get_ident()

    class SlowSource:
        def get_configs(self):
            assert threading.get_ident() != loop_thread, "source still runs on loop"
            entered.set()
            assert release.wait(5)
            if worker_fails:
                raise ValueError("synthetic source error after cancellation")
            return [("partial", {})]

    class NextSource:
        def list(self):
            second_entered.set()
            return ["next"]

    task = asyncio.create_task(sync_services(commands.SyncServices(force=True), in_memory_uow, SlowSource()))
    second = None
    try:
        async with asyncio.timeout(2):
            while not entered.is_set():
                if task.done():
                    await task
                await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        second = asyncio.create_task(views.get_service_names(NextSource()))
        # Use the thread helper's borrowed-token inventory as the capacity oracle.
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done()
        assert limiter.borrowed_tokens == 1
        assert not second_entered.is_set()
        rollback.assert_not_awaited()
        commit.assert_not_awaited()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert await asyncio.wait_for(second, 2) == ["next"]
        rollback.assert_awaited_once()
        commit.assert_not_awaited()
        assert await in_memory_uow.services.list() == []
        assert limiter.borrowed_tokens == 0
    finally:
        release.set()
        await asyncio.gather(task, *([second] if second else []), return_exceptions=True)
        limiter.total_tokens = previous_tokens
