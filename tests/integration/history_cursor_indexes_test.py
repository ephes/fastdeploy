import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import DropIndex

from deploy.adapters import orm

STEP_INDEX = "ix_step_deployment_id_id"


def seed_steps(conn):
    conn.execute(orm.services.insert(), [{"id": 1, "name": "sparse"}])
    conn.execute(orm.deployments.insert(), [{"id": 1, "service_id": 1}, {"id": 2, "service_id": 1}])
    conn.execute(
        orm.steps.insert(),
        [{"id": row_id, "deployment_id": 1 if row_id in (1, 1501, 3001) else 2} for row_id in range(1, 5001)],
    )


def assert_step_pages(conn, *, indexed):
    if conn.dialect.name == "postgresql":
        conn.exec_driver_sql("ANALYZE step")
        explain = "EXPLAIN "
    else:
        explain = "EXPLAIN QUERY PLAN "

    for before_id, expected in [(None, [3001, 1501]), (1501, [1])]:
        stmt = select(orm.steps).where(orm.steps.c.deployment_id == 1).order_by(orm.steps.c.id.desc()).limit(2)
        if before_id is not None:
            stmt = stmt.where(orm.steps.c.id < before_id)
        sql = stmt.compile(dialect=conn.dialect, compile_kwargs={"literal_binds": True})
        plan = str(conn.exec_driver_sql(explain + str(sql)).all())
        assert (STEP_INDEX in plan) == indexed, plan
        assert [step.id for step in conn.execute(stmt)] == expected


def drop_step_index(conn):
    for index in orm.steps.indexes:
        if index.name == STEP_INDEX:
            conn.execute(DropIndex(index))


def test_step_cursor_index_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'history.sqlite'}"
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            orm.metadata_obj.create_all(conn)
            seed_steps(conn)
            assert_step_pages(conn, indexed=True)
            drop_step_index(conn)
        with engine.begin() as conn:
            assert_step_pages(conn, indexed=False)
            orm.upgrade_history_indexes(conn)
        with engine.begin() as conn:
            orm.upgrade_history_indexes(conn)
            assert {index["name"] for index in inspect(conn).get_indexes("step")} >= {STEP_INDEX}
            assert_step_pages(conn, indexed=True)
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_step_cursor_index_postgresql(database):
    async with database.begin() as conn:
        await conn.run_sync(seed_steps)
        await conn.run_sync(assert_step_pages, indexed=True)
        await conn.run_sync(drop_step_index)
        await conn.run_sync(assert_step_pages, indexed=False)

    async with database.begin() as conn:
        await conn.run_sync(orm.upgrade_history_indexes)
        await conn.run_sync(orm.upgrade_history_indexes)
        await conn.run_sync(assert_step_pages, indexed=True)
