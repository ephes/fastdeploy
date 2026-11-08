"""Bound request work with thousands of synthetic unfinished deployments."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select

from deploy import views
from deploy.adapters import orm
from deploy.domain import model
from deploy.entrypoints.routers.deployments import get_deployments

pytestmark = pytest.mark.asyncio


async def seed_history(engine):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=2)
    # Ineligible ids surround candidates so limiting before filtering starves them.
    records = []
    steps = []
    eligible = set()
    for identifier in range(1, 2401):
        kind = identifier % 20
        orphan = kind == 0
        if orphan:
            eligible.add(identifier)
        records.append(
            {
                "id": identifier,
                "service_id": 1,
                "origin": "synthetic",
                "user": "test",
                "started": None if kind == 1 else (now if kind == 2 else old),
                "finished": old if kind == 3 else None,
            }
        )
        if kind != 0:
            steps.append(
                {
                    "deployment_id": identifier,
                    "name": "synthetic",
                    "state": "pending" if kind == 4 else ("running" if kind >= 7 else "success"),
                    "started": now if kind == 5 else old,
                    "finished": now if kind == 6 else None,
                }
            )
    # Some eligible candidates have terminal steps; others have no steps.
    steps.extend(
        {"deployment_id": i, "name": "done", "state": "success", "started": old, "finished": old}
        for i in sorted(eligible)
        if i % 40 == 0
    )
    async with engine.begin() as conn:
        await conn.execute(orm.services.insert(), [{"id": 1, "name": "synthetic", "data": {}}])
        await conn.execute(orm.deployments.insert(), records)
        await conn.execute(orm.steps.insert(), steps)
    return eligible


async def test_history_reconciliation_is_bounded_and_eventually_drains(database, independent_bus):
    eligible = await seed_history(database)
    bus = await independent_bus()
    queries, loaded = [], []

    def count_query(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    def count_load(instance, context):
        loaded.append(instance.id)

    event.listen(bus.uow.engine.sync_engine, "before_cursor_execute", count_query)
    event.listen(model.Deployment, "load", count_load)
    try:
        candidates = await views.get_orphaned_unfinished_deployment_ids(bus.uow)
        assert 0 < len(candidates) <= 50
        assert candidates == sorted(eligible)[:50]
        assert len(queries) <= 2
        assert len(loaded) <= 50
        finished = set()
        for _ in range(3):
            queries.clear()
            loaded.clear()
            page = await get_deployments(bus=bus, limit=7, before_id=None, service_id=None)
            assert [d.id for d in page] == list(range(2400, 2393, -1))
            # Each candidate still gets the existing ownership/row-lock recheck.
            assert len(queries) <= 2 + 12 * 50
            assert len(loaded) <= 3 * 50 + 7
            async with database.connect() as conn:
                finished_now = (
                    set(
                        (
                            await conn.scalars(
                                select(orm.deployments.c.id).where(orm.deployments.c.finished.is_not(None))
                            )
                        ).all()
                    )
                    & eligible
                )
            assert finished_now > finished
            assert len(finished_now - finished) <= 50
            finished = finished_now
        assert finished == eligible
        assert await views.get_orphaned_unfinished_deployment_ids(bus.uow) == []
        async with database.connect() as conn:
            marked = set(
                (
                    await conn.scalars(
                        select(orm.steps.c.deployment_id).where(orm.steps.c.name == "deployment orphaned")
                    )
                ).all()
            )
        assert marked == eligible
    finally:
        event.remove(bus.uow.engine.sync_engine, "before_cursor_execute", count_query)
        event.remove(model.Deployment, "load", count_load)
