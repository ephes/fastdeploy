from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from deploy.adapters import orm, repository
from deploy.domain.model import Step

pytestmark = pytest.mark.asyncio


@pytest.fixture(params=["memory", "sqlalchemy"])
def step_repository(request: pytest.FixtureRequest) -> Iterator[repository.AbstractStepRepository]:
    if request.param == "memory":
        yield repository.InMemoryStepRepository()
        return

    orm.start_mappers()
    engine = create_engine("sqlite://")
    try:
        orm.steps.create(engine)
        with Session(engine) as session:
            async_session = Mock(add=session.add, execute=AsyncMock(side_effect=session.execute))
            yield repository.SqlAlchemyStepRepository(async_session)
    finally:
        engine.dispose()


async def test_step_lookup_returns_retained_step_and_raises_for_missing_id(
    step_repository: repository.AbstractStepRepository,
) -> None:
    retained = Step(name="retained")
    await step_repository.add(retained)
    await step_repository.list()  # Flush the pending insert in the SQLAlchemy adapter.

    assert retained.id is not None
    assert await step_repository.get(retained.id) is retained
    with pytest.raises(NoResultFound):
        await step_repository.get(retained.id + 1)


async def test_memory_step_cursor_keeps_each_retained_id_after_delete() -> None:
    repo = repository.InMemoryStepRepository()
    removed = Step(name="removed", deployment_id=1)
    retained = Step(name="retained", deployment_id=1)
    added = Step(name="added", deployment_id=1)
    await repo.add(removed)
    await repo.add(retained)
    retained_id = retained.id
    await repo.delete(removed)
    await repo.add(added)

    first_page = await repo.page_by_deployment(1, limit=1)
    assert [step.name for step in first_page] == ["added"]
    second_page = await repo.page_by_deployment(1, limit=1, before_id=first_page[0].id)
    assert [step.name for step in second_page] == ["retained"]
    assert second_page[0].id == retained_id
    assert await repo.page_by_deployment(1, limit=1, before_id=retained_id) == []


async def test_memory_step_readd_keeps_id_and_single_row() -> None:
    repo = repository.InMemoryStepRepository()
    first = Step(name="first", deployment_id=1)
    second = Step(name="second", deployment_id=1)
    await repo.add(first)
    await repo.add(second)
    first_id, second_id = first.id, second.id

    # process_step re-adds steps that are already stored.
    first.state = "running"
    await repo.add(first)
    await repo.add(second)

    assert (first.id, second.id) == (first_id, second_id)
    assert await repo.list() == [first, second]
    first_page = await repo.page_by_deployment(1, limit=1)
    assert first_page == [second]
    assert await repo.page_by_deployment(1, limit=1, before_id=second_id) == [first]
    assert await repo.page_by_deployment(1, limit=1, before_id=first_id) == []

    added = Step(name="added", deployment_id=1)
    await repo.add(added)
    assert added.id > second_id
