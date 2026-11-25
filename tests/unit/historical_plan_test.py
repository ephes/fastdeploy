from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import create_engine, null
from sqlalchemy.orm import Session

from deploy.adapters import orm
from deploy.domain import model
from deploy.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def sqlite_plan_uow():
    orm.start_mappers()
    engine = create_engine("sqlite://")
    try:
        orm.metadata_obj.create_all(engine)
        with Session(engine, expire_on_commit=False) as session:
            async_session = Mock(
                wraps=session,
                execute=AsyncMock(side_effect=session.execute),
                flush=AsyncMock(side_effect=session.flush),
                commit=AsyncMock(side_effect=session.commit),
                rollback=AsyncMock(side_effect=session.rollback),
            )
            uow = SqlAlchemyUnitOfWork(engine, None, owns_engine=False)
            uow.session = async_session
            yield uow
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["sqlite", "in_memory"])
async def test_legacy_null_step_disqualifies_successful_plan(request, backend):
    uow = request.getfixturevalue("sqlite_plan_uow" if backend == "sqlite" else "in_memory_uow")
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)

    async with uow:
        service = model.Service(name="sample")
        await uow.services.add(service)
        await uow.flush()
        older = model.Deployment(
            service_id=service.id, origin="test", user="test", started=now - timedelta(days=1), finished=now
        )
        newer = model.Deployment(service_id=service.id, origin="test", user="test", started=now, finished=now)
        await uow.deployments.add(older)
        await uow.deployments.add(newer)
        await uow.flush()
        await uow.steps.add(model.Step(name="older success", state="success", deployment_id=older.id))
        await uow.steps.add(model.Step(name="newer success", state="success", deployment_id=newer.id))
        # Bypass the SQL column default, as a legacy row can contain a real NULL.
        await uow.steps.add(
            model.Step(name="legacy step", state=null() if backend == "sqlite" else None, deployment_id=newer.id)
        )
        await uow.commit()

    async with uow:
        assert await uow.deployments.get_last_successful_deployment_id(service.id) == older.id
