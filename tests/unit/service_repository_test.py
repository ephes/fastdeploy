import pytest
from sqlalchemy.exc import NoResultFound

from deploy.adapters.repository import InMemoryServiceRepository
from deploy.domain.model import Service

pytestmark = pytest.mark.asyncio


async def test_memory_service_insert_allocates_id_after_delete() -> None:
    repo = InMemoryServiceRepository()
    removed = Service(name="removed")
    retained = Service(name="retained")
    added = Service(name="added")
    await repo.add(removed)
    await repo.add(retained)
    retained_id = retained.id

    await repo.delete(removed)
    await repo.add(added)

    assert retained_id is not None
    assert added.id > retained_id
    assert retained.id == retained_id
    assert await repo.get(retained_id) is retained
    assert await repo.get(added.id) is added
    assert await repo.list() == [retained, added]


async def test_memory_service_update_replaces_matching_id_after_delete() -> None:
    repo = InMemoryServiceRepository()
    removed = Service(name="removed")
    retained = Service(name="retained")
    other = Service(name="other")
    for service in (removed, retained, other):
        await repo.add(service)
    await repo.delete(removed)

    replacement = Service(id=retained.id, name="updated")
    await repo.add(replacement)

    assert await repo.list() == [replacement, other]
    assert await repo.get(retained.id) is replacement
    assert await repo.get(other.id) is other


async def test_memory_service_update_raises_for_deleted_id() -> None:
    repo = InMemoryServiceRepository()
    removed = Service(name="removed")
    retained = Service(name="retained")
    await repo.add(removed)
    await repo.add(retained)
    await repo.delete(removed)

    with pytest.raises(NoResultFound):
        await repo.add(Service(id=removed.id, name="updated"))
    assert await repo.list() == [retained]
