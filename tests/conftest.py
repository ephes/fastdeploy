import asyncio

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from deploy.adapters import filesystem, orm
from deploy.auth import create_access_token, get_password_hash
from deploy.bootstrap import bootstrap, get_bus
from deploy.config import settings
from deploy.domain import model
from deploy.entrypoints.fastapi_app import app as fastapi_app
from deploy.service_layer import unit_of_work


@pytest.fixture(scope="session")
def anyio_backend():
    """Choose asyncio backend for tests"""
    return "asyncio"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def database():
    meta = orm.metadata_obj
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(meta.drop_all)
        await conn.run_sync(meta.create_all)
    orm.start_mappers()
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(meta.drop_all)
    await engine.dispose()


@pytest.fixture
def database_type(request):
    """Make it possible for tests to choose database type"""
    database = "database_url"  # default
    marker = request.node.get_closest_marker("db")
    if marker is not None:
        database = marker.args[0]
    return database


@pytest_asyncio.fixture()
async def rolling_back_database_session(database):
    """Wraps the session in a transaction and rolls back after each test."""
    connection = await database.connect()
    transaction = await connection.begin()
    session = sessionmaker(class_=AsyncSession, expire_on_commit=False)(bind=connection)
    yield session
    await session.close()
    await transaction.rollback()
    await connection.close()


@pytest.fixture
def rolling_back_database_uow(rolling_back_database_session):
    """
    Returns a unit of work that rolls back all changes after each test.
    """

    def session_factory(bind=None):
        """
        Just a helper to be able to pass the rollback_postgres_session
        to the unit of work.
        """
        return rolling_back_database_session

    class FakeEngine:
        async def connect(self):
            return None

    return unit_of_work.TestableSqlAlchemyUnitOfWork(FakeEngine(), session_factory)


@pytest.fixture
def in_memory_uow():
    return unit_of_work.InMemoryUnitOfWork()


@pytest.fixture
def uow(request, database_type):
    """Builds a unit of work for the given database type."""
    if database_type == "database_url":
        return request.getfixturevalue("rolling_back_database_uow")
    elif database_type == "in_memory":
        return request.getfixturevalue("in_memory_uow")
    else:
        raise ValueError(f"unknown database type: {database_type}")


class TestablePublisher:
    def __init__(self):
        self.events = []

    async def __call__(self, message, event):
        self.events.append((message, event))


@pytest.fixture
def publisher():
    return TestablePublisher()


@pytest.fixture
def services_filesystem(tmp_path) -> filesystem.AbstractFilesystem:
    return filesystem.Filesystem(tmp_path)


@pytest_asyncio.fixture()
async def bus(uow, publisher, services_filesystem):
    """The central message bus."""
    bus = await bootstrap(
        start_orm=False, create_db_and_tables=False, uow=uow, publish=publisher, fs=services_filesystem
    )
    return bus


@pytest.fixture
def app(bus):
    """
    Returns a fastapi app with custom message bus dependency.
    """
    fastapi_app.dependency_overrides[get_bus] = lambda: bus
    return fastapi_app


@pytest.fixture
def password():
    return "password"


@pytest.fixture
def user(password):
    return model.User(name="user", password=get_password_hash(password))


@pytest_asyncio.fixture()
async def user_in_db(bus, user):
    async with bus.uow as uow:
        await uow.users.add(user)
        await uow.commit()
    return user


@pytest.fixture
def valid_access_token(user):
    return create_access_token({"type": "user", "user": user.name}, timedelta(minutes=5))


@pytest.fixture
def valid_access_token_in_db(user_in_db):
    return create_access_token({"type": "user", "user": user_in_db.name}, timedelta(minutes=5))


@pytest.fixture
def service():
    return model.Service(name="fastdeploytest", data={"foo": "bar"})


@pytest_asyncio.fixture()
async def service_in_db(bus, service):
    async with bus.uow as uow:
        await uow.services.add(service)
        await uow.commit()
    return service


@pytest.fixture
def valid_service_token_in_db(service_in_db):
    return create_access_token({"type": "service", "service": service_in_db.name}, timedelta(minutes=5))


@pytest.fixture
def deployment(service_in_db):
    return model.Deployment(
        started=datetime.now(timezone.utc), service_id=service_in_db.id, origin="github", user="fastdeploy"
    )


@pytest_asyncio.fixture()
async def deployment_in_db(bus, deployment):
    async with bus.uow as uow:
        await uow.deployments.add(deployment)
        await uow.commit()
    return deployment


@pytest.fixture
def valid_deploy_token_in_db(deployment_in_db):
    return create_access_token({"type": "deployment", "deployment": deployment_in_db.id}, timedelta(minutes=5))


@pytest.fixture
def deployed_service(deployment_in_db):
    return model.DeployedService(
        deployment_id=deployment_in_db.id,
        config={"foo": "bar"},
    )


@pytest_asyncio.fixture()
async def deployed_service_in_db(bus, deployed_service):
    async with bus.uow as uow:
        await uow.deployed_services.add(deployed_service)
        await uow.commit()
    return deployed_service
