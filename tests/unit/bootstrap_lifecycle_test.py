from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from deploy import bootstrap
from deploy.service_layer.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("factory", ["request", "cli", "direct"])
@pytest.mark.parametrize("stage", ["connect", "bootstrap"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_startup_failure_closes_owned_resources(monkeypatch, factory, stage, cleanup_fails):
    failure = RuntimeError("synthetic-startup-error")
    engine = SimpleNamespace(connect=AsyncMock(), dispose=AsyncMock())
    connection = SimpleNamespace(
        close=AsyncMock(side_effect=ValueError("cleanup") if cleanup_fails and stage == "connect" else None)
    )
    session = SimpleNamespace(close=AsyncMock(side_effect=ValueError("cleanup") if cleanup_fails else None))
    engine.connect.return_value = connection
    session_factory = Mock(return_value=session)
    if stage == "connect":
        # Fail after the connection is acquired but before session initialization.
        session_factory.side_effect = failure
    else:
        monkeypatch.setattr(bootstrap.orm, "start_mappers", Mock(side_effect=failure))
    monkeypatch.setattr(bootstrap, "create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr(bootstrap, "sessionmaker", Mock(return_value=session_factory))
    with pytest.raises(RuntimeError) as caught:
        if factory == "request":
            await anext(bootstrap.get_bus())
        elif factory == "cli":
            await bootstrap.get_bus_for_cli()
        else:
            await bootstrap.bootstrap()
    assert caught.value is failure
    if stage == "bootstrap":
        session.close.assert_awaited_once()
    connection.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()


async def test_failed_engine_connect_still_disposes_engine(monkeypatch):
    engine = SimpleNamespace(connect=AsyncMock(side_effect=RuntimeError("connect")), dispose=AsyncMock())
    monkeypatch.setattr(bootstrap, "create_async_engine", Mock(return_value=engine))
    with pytest.raises(RuntimeError, match="connect"):
        await bootstrap.get_bus_for_cli()
    engine.dispose.assert_awaited_once()


async def test_successful_request_closes_on_exit_but_cli_transfers_ownership(monkeypatch):
    uow = SimpleNamespace(close=AsyncMock())
    bus = SimpleNamespace(uow=uow)
    monkeypatch.setattr(bootstrap, "bootstrap", AsyncMock(return_value=bus))
    request = bootstrap.get_bus()
    assert await anext(request) is bus
    uow.close.assert_not_awaited()
    await request.aclose()
    uow.close.assert_awaited_once()
    uow.close.reset_mock()
    assert await bootstrap.get_bus_for_cli() is bus
    uow.close.assert_not_awaited()


async def test_close_attempts_remaining_resources_if_session_and_connection_fail():
    engine = SimpleNamespace(dispose=AsyncMock())
    uow = SqlAlchemyUnitOfWork(engine, Mock())
    uow.session = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("session")))
    uow.connection = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("connection")))
    with pytest.raises(RuntimeError):
        await uow.close()
    engine.dispose.assert_awaited_once()
    uow.connection.close.assert_awaited_once()


async def test_session_factory_construction_failure_disposes_engine(monkeypatch):
    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(bootstrap, "create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr(bootstrap, "sessionmaker", Mock(side_effect=RuntimeError("factory")))
    with pytest.raises(RuntimeError, match="factory"):
        await bootstrap.get_bus_for_cli()
    engine.dispose.assert_awaited_once()


async def test_supplied_uow_stays_owned_by_caller_on_bootstrap_failure(monkeypatch):
    uow = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(bootstrap.orm, "start_mappers", Mock(side_effect=RuntimeError("mapper")))
    with pytest.raises(RuntimeError, match="mapper"):
        await bootstrap.bootstrap(uow=uow)
    uow.close.assert_not_awaited()
