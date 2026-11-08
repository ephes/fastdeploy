import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from deploy.bootstrap import bootstrap
from deploy.config import settings
from deploy.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest_asyncio.fixture
async def independent_bus(database, publisher, services_filesystem):
    """Request-like buses with independent connections and real commits."""
    buses = []

    async def make():
        engine = create_async_engine(settings.database_url)
        uow = SqlAlchemyUnitOfWork(engine, sessionmaker(class_=AsyncSession, expire_on_commit=False))
        await uow.connect()
        bus = await bootstrap(
            start_orm=False, create_db_and_tables=False, uow=uow, publish=publisher, fs=services_filesystem
        )
        buses.append(bus)
        return bus

    yield make
    for bus in reversed(buses):
        await bus.uow.close()
