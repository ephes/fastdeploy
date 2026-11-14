import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from deploy import bootstrap
from deploy.entrypoints.fastapi_app import lifespan

pytestmark = pytest.mark.asyncio


async def test_many_requests_share_engine_but_keep_sessions_isolated(monkeypatch):
    engines, sessions, connections = [], [], []

    def create_engine(*args, **kwargs):
        async def connect():
            connection = SimpleNamespace(close=AsyncMock())
            connections.append(connection)
            return connection

        engine = SimpleNamespace(connect=connect, dispose=AsyncMock())
        engines.append(engine)
        return engine

    def session_factory(**kwargs):
        session = SimpleNamespace(close=AsyncMock())
        sessions.append(session)
        return session

    monkeypatch.setattr(bootstrap, "create_async_engine", create_engine)
    monkeypatch.setattr(bootstrap, "sessionmaker", Mock(return_value=session_factory))
    schema = AsyncMock()
    monkeypatch.setattr(bootstrap.orm, "create_db_and_tables", schema)
    application = FastAPI(lifespan=lifespan)
    seen = []

    @application.get("/probe")
    async def probe(bus=Depends(bootstrap.get_bus)):
        seen.append(bus.uow)
        return {"ok": True}

    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            results = await asyncio.gather(*(client.get("/probe") for _ in range(10)))
            assert all(response.status_code == 200 for response in results)
        assert len(engines) == 1
        engines[0].dispose.assert_not_awaited()
        assert len({id(uow) for uow in seen}) == 10
        assert len({id(session) for session in sessions}) == 10
        for session, connection in zip(sessions, connections, strict=True):
            session.close.assert_awaited_once()
            connection.close.assert_awaited_once()
        schema.assert_not_awaited()
    engines[0].dispose.assert_awaited_once()


async def test_lifespan_start_failure_disposes_engine_without_masking_primary(monkeypatch):
    engine = SimpleNamespace(dispose=AsyncMock(side_effect=ValueError("cleanup-canary")))
    monkeypatch.setattr(bootstrap, "create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr(bootstrap.orm, "start_mappers", Mock(side_effect=RuntimeError("startup-canary")))
    application = FastAPI(lifespan=lifespan)
    with pytest.raises(RuntimeError, match="startup-canary"):
        async with application.router.lifespan_context(application):
            pytest.fail("must not serve")
    engine.dispose.assert_awaited_once()


@pytest.mark.parametrize("stage", ["session", "bus"])
async def test_request_start_failure_closes_partial_resources_without_disposing_pool(monkeypatch, stage):
    connection = SimpleNamespace(close=AsyncMock())
    engine = SimpleNamespace(connect=AsyncMock(return_value=connection), dispose=AsyncMock())
    session = SimpleNamespace(close=AsyncMock())
    failure = RuntimeError("primary-canary")
    factory = Mock(return_value=session, side_effect=failure if stage == "session" else None)
    if stage == "bus":
        monkeypatch.setattr(bootstrap, "bootstrap", AsyncMock(side_effect=failure))
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(database_engine=engine, database_session_factory=factory))
    )
    with pytest.raises(RuntimeError) as error:
        await anext(bootstrap.get_bus(request))
    assert error.value is failure
    connection.close.assert_awaited_once()
    if stage == "bus":
        session.close.assert_awaited_once()
    engine.dispose.assert_not_awaited()
