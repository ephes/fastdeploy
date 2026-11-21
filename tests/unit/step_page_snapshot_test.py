from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from deploy.adapters import orm
from deploy.bootstrap import get_bus
from deploy.entrypoints.dependencies import get_current_active_user
from deploy.entrypoints.routers.steps import router
from deploy.service_layer import unit_of_work


@pytest.mark.asyncio
async def test_step_page_remains_consistent_when_parent_is_deleted(tmp_path):
    # WAL allows a second connection to commit while the reader is active.
    engine = create_engine(f"sqlite:///{tmp_path / 'steps.sqlite3'}")
    try:
        orm.start_mappers()
        orm.metadata_obj.create_all(engine)
        with engine.begin() as writer:
            writer.exec_driver_sql("PRAGMA journal_mode=WAL")
            writer.execute(orm.deployments.insert(), [{"id": 1}, {"id": 2}])
            writer.execute(
                orm.steps.insert(),
                [{"deployment_id": 1, "name": name, "message": ""} for name in ("older", "newest")],
            )

        with Session(engine) as reader:
            delete_after_read = False

            async def execute(statement):
                nonlocal delete_after_read
                # Match async SQLAlchemy's buffered results. Commit the deletion
                # after the first SELECT returns and before the application reads again.
                result = reader.execute(statement).freeze()()
                if delete_after_read:
                    delete_after_read = False
                    with engine.begin() as writer:
                        writer.exec_driver_sql("PRAGMA foreign_keys=ON")
                        writer.execute(orm.deployments.delete().where(orm.deployments.c.id == 1))
                        assert writer.execute(orm.steps.select()).all() == []
                return result

            session = Mock(execute=AsyncMock(side_effect=execute))
            uow = unit_of_work.TestableSqlAlchemyUnitOfWork(Mock(connect=AsyncMock()), lambda **_: session)
            app = FastAPI()
            app.include_router(router)
            app.dependency_overrides[get_bus] = lambda: Mock(uow=uow)
            app.dependency_overrides[get_current_active_user] = lambda: None

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                empty = await client.get("/steps/", params={"deployment_id": 2})
                assert empty.status_code == 200
                assert empty.json() == []

                delete_after_read = True
                session.execute.reset_mock()
                page = await client.get("/steps/", params={"deployment_id": 1, "limit": 1})
                assert page.status_code == 200
                assert [step["name"] for step in page.json()] == ["newest"]
                session.execute.assert_awaited_once()

                missing = await client.get("/steps/", params={"deployment_id": 1})
                assert missing.status_code == 404
                assert missing.json() == {"detail": "Deployment not found"}
    finally:
        engine.dispose()
