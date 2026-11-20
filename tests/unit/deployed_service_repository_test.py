from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from deploy.adapters import orm, repository
from deploy.domain import model


@pytest.fixture
def sql_repository():
    orm.start_mappers()
    engine = create_engine("sqlite://")
    try:
        orm.deployed_services.create(engine)
        with Session(engine) as session:
            async_session = Mock(add=session.add, execute=AsyncMock(side_effect=session.execute))
            yield repository.SqlAlchemyDeployedServiceRepository(async_session)
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_deployed_service_inventory_uses_primary_key_order(sql_repository):
    in_memory = repository.InMemoryDeployedServiceRepository()
    for repo in (sql_repository, in_memory):
        for deployment_id in (9, 4, 9):
            await repo.add(model.DeployedService(deployment_id=deployment_id))

    persistent_rows = await sql_repository.list()
    statement = sql_repository.session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "ORDER BY deployed_service.id DESC" in str(statement)
    expected = [(3, 9), (2, 4), (1, 9)]
    assert [(row.id, row.deployment_id) for row in persistent_rows] == expected
    assert [(row.id, row.deployment_id) for row in await in_memory.list()] == expected


@pytest.mark.asyncio
async def test_deployed_service_page_filters_and_limits_in_sql(sql_repository):
    for deployment_id in (9, 4, 9, 4, 9):
        await sql_repository.add(model.DeployedService(deployment_id=deployment_id))

    rows = await sql_repository.list(limit=2, before_id=5)

    sql_repository.session.execute.assert_awaited_once()
    statement = sql_repository.session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    sql = str(statement)
    assert "WHERE deployed_service.id <" in sql
    assert "ORDER BY deployed_service.id DESC" in sql
    assert "LIMIT" in sql
    assert sorted(statement.params.values()) == [2, 5]
    assert [(row.id, row.deployment_id) for row in rows] == [(4, 4), (3, 9)]
