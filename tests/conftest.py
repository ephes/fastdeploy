import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import clear_mappers, sessionmaker

from deploy.adapters import orm
from deploy.bootstrap import bootstrap, get_bus
from deploy.config import settings
from deploy.entrypoints.fastapi_app import app as fastapi_app
from deploy.service_layer import unit_of_work


@pytest.fixture
def base_url():
    return "http://test"


@pytest.fixture
def anyio_backend():
    """Choose asyncio backend for tests"""
    return "trio"


@pytest.fixture(scope="session")
def postgres_db():
    engine = create_engine(settings.database_url)
    orm.metadata_obj.create_all(engine)
    yield engine
    orm.metadata_obj.drop_all(engine)
    clear_mappers()


@pytest.fixture
def rollback_postgres_session(postgres_db):
    """Wraps the session in a transaction and rolls back after each test."""
    connection = postgres_db.connect()
    transaction = connection.begin()
    session = sessionmaker()(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def rollback_postgres_uow(rollback_postgres_session):
    """
    Returns a unit of work that rolls back all changes after each test.
    """

    def session_factory():
        """
        Just a helper to be able to pass the rollback_postgres_session
        to the unit of work.
        """
        return rollback_postgres_session

    return unit_of_work.SqlAlchemyUnitOfWork(session_factory)


@pytest.fixture
def app(rollback_postgres_uow):
    """
    Returns a fastapi app with custom message bus dependency.
    """
    bus = bootstrap(start_orm=False, uow=rollback_postgres_uow)
    fastapi_app.dependency_overrides[get_bus] = lambda: bus
    return fastapi_app
