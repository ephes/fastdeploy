from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from deploy.adapters import orm, repository


@pytest.mark.asyncio
async def test_step_page_sql_is_bounded_and_uses_exclusive_cursor():
    orm.start_mappers()
    rows = [Mock(id=7)]
    result = Mock()
    result.scalars.return_value.all.return_value = rows
    session = Mock(execute=AsyncMock(return_value=result))
    repo = repository.SqlAlchemyStepRepository(session)
    assert await repo.page_by_deployment(42, limit=25, before_id=9) is rows
    statement = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    sql = str(statement)
    assert "step.deployment_id =" in sql
    assert "step.id <" in sql
    assert "ORDER BY step.id DESC" in sql
    assert "LIMIT" in sql
    assert sorted(statement.params.values()) == [9, 25, 42]
