import asyncio
import importlib
import logging
from unittest.mock import AsyncMock, Mock

import pytest

from deploy.domain import commands
from deploy.service_layer.unit_of_work import SqlAlchemyUnitOfWork

bootstrap_module = importlib.import_module("deploy.bootstrap")
pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("phase", ["handler", "commit", "cancel", "none"])
@pytest.mark.parametrize("cleanup_type", [OSError, asyncio.CancelledError])
async def test_rollback_failure_preserves_primary_and_request_cleanup(monkeypatch, caplog, phase, cleanup_type):
    cleanup = cleanup_type("private rollback details")
    session = Mock(close=AsyncMock(), rollback=AsyncMock(side_effect=cleanup))
    connection = Mock(close=AsyncMock())
    engine = Mock(connect=AsyncMock(return_value=connection), dispose=AsyncMock())
    uow = SqlAlchemyUnitOfWork(engine, lambda bind: session)
    await uow.connect()
    bus = await bootstrap_module.bootstrap(start_orm=False, create_db_and_tables=False, uow=uow, publish=AsyncMock())
    primary = asyncio.CancelledError("private cancellation") if phase == "cancel" else RuntimeError("private primary")
    session.commit = AsyncMock(side_effect=primary if phase == "commit" else None)

    async def failing_handler(command):
        async with uow:
            if phase in ("handler", "cancel"):
                raise primary
            if phase == "commit":
                await uow.commit()

    bus.command_handlers[commands.SyncServices] = failing_handler
    monkeypatch.setattr(bootstrap_module, "bootstrap", AsyncMock(return_value=bus))
    request = bootstrap_module.get_bus()
    assert await anext(request) is bus
    try:
        with (
            caplog.at_level(logging.ERROR, logger="deploy.service_layer.unit_of_work"),
            pytest.raises(
                cleanup_type if phase == "none" or cleanup_type is asyncio.CancelledError else type(primary)
            ) as error,
        ):
            await bus.handle(commands.SyncServices())
        if cleanup_type is asyncio.CancelledError:
            assert error.value is cleanup
            assert not any(r.name == "deploy.service_layer.unit_of_work" for r in caplog.records)
        elif phase != "none":
            assert error.value is primary
            records = [r for r in caplog.records if r.name == "deploy.service_layer.unit_of_work"]
            assert len(records) == 1
            assert records[0].getMessage() == "uow_rollback_failed category=OSError"
            assert records[0].exc_info is None
        else:
            assert not any(r.name == "deploy.service_layer.unit_of_work" for r in caplog.records)
    finally:
        await request.aclose()
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()
    connection.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()
