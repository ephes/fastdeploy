import asyncio
import importlib
import logging
from types import SimpleNamespace
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
    uow.owns_engine = False
    monkeypatch.setattr(bootstrap_module.unit_of_work, "SqlAlchemyUnitOfWork", Mock(return_value=uow))
    state = SimpleNamespace(database_engine=engine, database_session_factory=lambda bind: session)
    request = bootstrap_module.get_bus(SimpleNamespace(app=SimpleNamespace(state=state)))
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
    engine.dispose.assert_not_awaited()


@pytest.mark.parametrize("phase", ["body", "cancel", "none"])
@pytest.mark.parametrize("rollback_fails", [False, True])
async def test_expunge_failure_always_rolls_back_and_preserves_primary(caplog, phase, rollback_fails):
    expunge_error = OSError("private expunge details")
    session = Mock(
        expunge_all=Mock(side_effect=expunge_error),
        rollback=AsyncMock(side_effect=RuntimeError("private rollback") if rollback_fails else None),
        close=AsyncMock(),
    )
    connection = Mock(close=AsyncMock())
    engine = Mock(connect=AsyncMock(return_value=connection), dispose=AsyncMock())
    uow = SqlAlchemyUnitOfWork(engine, lambda bind: session, owns_engine=False)
    await uow.connect()
    primary = asyncio.CancelledError("private cancel") if phase == "cancel" else ValueError("private body")
    with (
        caplog.at_level(logging.ERROR),
        pytest.raises(type(expunge_error) if phase == "none" else type(primary)) as error,
    ):
        async with uow:
            if phase != "none":
                raise primary
    assert error.value is (expunge_error if phase == "none" else primary)
    session.rollback.assert_awaited_once()
    assert all("private" not in record.getMessage() and record.exc_info is None for record in caplog.records)
    assert any(record.getMessage() == "uow_expunge_failed category=OSError" for record in caplog.records) == (
        phase != "none"
    )
    session.expunge_all.side_effect = None
    session.rollback.side_effect = None
    session.commit = AsyncMock()
    async with uow:
        await uow.commit()
    assert session.rollback.await_count == 2
    await uow.close()
    session.close.assert_awaited_once()
    connection.close.assert_awaited_once()
    engine.dispose.assert_not_awaited()


async def test_clean_body_inside_exception_handler_still_surfaces_rollback_error():
    session = Mock(rollback=AsyncMock(side_effect=OSError("rollback")))
    uow = SqlAlchemyUnitOfWork(Mock(), Mock())
    uow.session = session
    try:
        raise ValueError("already handled")
    except ValueError:
        with pytest.raises(OSError, match="rollback"):
            async with uow:
                pass
