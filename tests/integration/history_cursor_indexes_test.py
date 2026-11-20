import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import DropIndex

from deploy.adapters import orm

CURSOR_INDEXES = [
    pytest.param(orm.steps, orm.steps.c.deployment_id, "ix_step_deployment_id_id", id="steps"),
    pytest.param(orm.deployments, orm.deployments.c.service_id, "ix_deployment_service_id_id", id="history"),
]


def seed_history(conn, table, owner):
    conn.execute(orm.services.insert(), [{"id": 1, "name": "sparse"}, {"id": 2, "name": "busy"}])
    if table is orm.steps:
        conn.execute(orm.deployments.insert(), [{"id": 1, "service_id": 1}, {"id": 2, "service_id": 2}])
    conn.execute(
        table.insert(),
        [{"id": row_id, owner.key: 1 if row_id in (1, 1501, 3001) else 2} for row_id in range(1, 5001)],
    )


def assert_cursor_pages(conn, table, owner, index_name, *, indexed):
    if conn.dialect.name == "postgresql":
        conn.exec_driver_sql(f"ANALYZE {table.name}")
        explain = "EXPLAIN "
    else:
        explain = "EXPLAIN QUERY PLAN "

    for before_id, expected in [(None, [3001, 1501]), (1501, [1])]:
        stmt = select(table).where(owner == 1).order_by(table.c.id.desc()).limit(2)
        if before_id is not None:
            stmt = stmt.where(table.c.id < before_id)
        sql = stmt.compile(dialect=conn.dialect, compile_kwargs={"literal_binds": True})
        plan = str(conn.exec_driver_sql(explain + str(sql)).all())
        assert (index_name in plan) == indexed, plan
        assert [row.id for row in conn.execute(stmt)] == expected

    if table is orm.deployments:
        global_page = select(table).where(table.c.id < 3001).order_by(table.c.id.desc()).limit(2)
        assert [row.id for row in conn.execute(global_page)] == [3000, 2999]


def drop_cursor_index(conn, table, index_name):
    for index in table.indexes:
        if index.name == index_name:
            conn.execute(DropIndex(index))


@pytest.mark.parametrize("table,owner,index_name", CURSOR_INDEXES)
def test_cursor_index_sqlite(tmp_path, table, owner, index_name):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.sqlite'}", poolclass=NullPool)
    try:
        with engine.begin() as conn:
            orm.metadata_obj.create_all(conn)
            seed_history(conn, table, owner)
            assert_cursor_pages(conn, table, owner, index_name, indexed=True)
            drop_cursor_index(conn, table, index_name)
        with engine.begin() as conn:
            assert_cursor_pages(conn, table, owner, index_name, indexed=False)
            orm.upgrade_history_indexes(conn)
        with engine.begin() as conn:
            assert {index["name"] for index in inspect(conn).get_indexes(table.name)} >= {index_name}
            orm.upgrade_history_indexes(conn)
            assert_cursor_pages(conn, table, owner, index_name, indexed=True)
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("table,owner,index_name", CURSOR_INDEXES)
async def test_cursor_index_postgresql(database, table, owner, index_name):
    async with database.begin() as conn:
        await conn.run_sync(seed_history, table, owner)
        await conn.run_sync(assert_cursor_pages, table, owner, index_name, indexed=True)
        await conn.run_sync(drop_cursor_index, table, index_name)
        await conn.run_sync(assert_cursor_pages, table, owner, index_name, indexed=False)

    async with database.begin() as conn:
        await conn.run_sync(orm.upgrade_history_indexes)
        await conn.run_sync(orm.upgrade_history_indexes)
        await conn.run_sync(assert_cursor_pages, table, owner, index_name, indexed=True)
