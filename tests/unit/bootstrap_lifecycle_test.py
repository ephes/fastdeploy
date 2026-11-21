import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from deploy import bootstrap
from deploy.service_layer.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("factory", ["cli", "direct"])
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
        if factory == "cli":
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


async def test_successful_cli_transfers_ownership(monkeypatch):
    uow = SimpleNamespace(close=AsyncMock())
    bus = SimpleNamespace(uow=uow)
    monkeypatch.setattr(bootstrap, "bootstrap", AsyncMock(return_value=bus))
    assert await bootstrap.get_bus_for_cli() is bus
    uow.close.assert_not_awaited()


async def test_close_attempts_remaining_resources_if_session_and_connection_fail():
    engine = SimpleNamespace(dispose=AsyncMock())
    uow = SqlAlchemyUnitOfWork(engine, Mock())
    uow.session = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("session")))
    connection = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("connection")))
    uow.connection = connection
    with pytest.raises(RuntimeError):
        await uow.close()
    engine.dispose.assert_awaited_once()
    connection.close.assert_awaited_once()


@pytest.mark.parametrize(
    ("owns_engine", "failed_resource"),
    [(False, "session"), (False, "connection"), (True, "session"), (True, "connection"), (True, "engine")],
)
async def test_close_retires_each_owned_resource_once(owns_engine: bool, failed_resource: str) -> None:
    failure = RuntimeError(failed_resource)
    sessions = [SimpleNamespace(close=AsyncMock()), SimpleNamespace(close=AsyncMock())]
    connections = [SimpleNamespace(close=AsyncMock()), SimpleNamespace(close=AsyncMock())]
    engine = SimpleNamespace(connect=AsyncMock(side_effect=connections), dispose=AsyncMock())
    retirement = {"session": sessions[0].close, "connection": connections[0].close, "engine": engine.dispose}
    retirement[failed_resource].side_effect = [failure, None]
    uow = SqlAlchemyUnitOfWork(engine, Mock(side_effect=sessions), owns_engine=owns_engine)

    await uow.connect()
    with pytest.raises(RuntimeError) as caught:
        await uow.close()
    assert caught.value is failure
    await uow.close()

    sessions[0].close.assert_awaited_once()
    connections[0].close.assert_awaited_once()
    assert engine.dispose.await_count == int(owns_engine)

    await uow.connect()
    await uow.close()
    await uow.close()

    sessions[1].close.assert_awaited_once()
    connections[1].close.assert_awaited_once()
    assert engine.dispose.await_count == 2 * int(owns_engine)


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


@pytest.mark.parametrize("primary_type", [ValueError, asyncio.CancelledError])
async def test_request_cleanup_logging_failure_preserves_primary_and_retires_resources(
    monkeypatch: pytest.MonkeyPatch, primary_type: type[BaseException]
) -> None:
    primary = primary_type("synthetic request failure")
    session = SimpleNamespace(close=AsyncMock(side_effect=ValueError("synthetic session failure")))
    connection = SimpleNamespace(close=AsyncMock(side_effect=OSError("synthetic connection failure")))
    engine = SimpleNamespace(connect=AsyncMock(return_value=connection), dispose=AsyncMock())
    state = SimpleNamespace(database_engine=engine, database_session_factory=Mock(return_value=session))
    build_bus = AsyncMock(return_value=object())
    monkeypatch.setattr(bootstrap, "bootstrap", build_bus)
    log_error = Mock(side_effect=RuntimeError("synthetic logging failure"))
    monkeypatch.setattr(bootstrap.logger, "error", log_error)

    request = bootstrap.get_bus(SimpleNamespace(app=SimpleNamespace(state=state)))
    assert await anext(request) is build_bus.return_value
    uow = build_bus.await_args.kwargs["uow"]
    with pytest.raises(primary_type) as raised:
        await request.athrow(primary)

    assert raised.value is primary
    assert uow.connection is None
    assert not hasattr(uow, "session")
    await uow.close()
    session.close.assert_awaited_once_with()
    connection.close.assert_awaited_once_with()
    engine.dispose.assert_not_awaited()
    log_error.assert_called_once_with("request_cleanup_failed category=%s", "OSError")
