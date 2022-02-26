from datetime import timedelta

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import clear_mappers, sessionmaker

from deploy.adapters import orm
from deploy.auth import create_access_token, get_password_hash
from deploy.bootstrap import bootstrap, get_bus
from deploy.config import settings
from deploy.domain import model
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
    orm.start_mappers()
    yield engine
    orm.metadata_obj.drop_all(engine)
    clear_mappers()


@pytest.fixture
def database_type(request):
    "Make it possible for tests to choose database type"
    database = "postgres"  # default
    marker = request.node.get_closest_marker("db")
    if marker is not None:
        database = marker.args[0]
    return database


@pytest.fixture
def rolling_back_postgres_session(postgres_db):
    """Wraps the session in a transaction and rolls back after each test."""
    connection = postgres_db.connect()
    transaction = connection.begin()
    session = sessionmaker()(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def rolling_back_postgres_uow(rolling_back_postgres_session):
    """
    Returns a unit of work that rolls back all changes after each test.
    """

    def session_factory():
        """
        Just a helper to be able to pass the rollback_postgres_session
        to the unit of work.
        """
        return rolling_back_postgres_session

    return unit_of_work.TestableSqlAlchemyUnitOfWork(session_factory)


@pytest.fixture
def in_memory_uow():
    return unit_of_work.InMemoryUnitOfWork()


@pytest.fixture
def uow(request, database_type):
    """Builds a unit of work for the given database type."""
    # default_uow_fixture_name = "rolling_back_postgres_uow"  # default
    default_uow_fixture_name = "in_memory_uow"
    # if database_type == "postgres":
    #     return request.getfixturevalue("rolling_back_postgres_uow")
    return request.getfixturevalue(default_uow_fixture_name)


@pytest.fixture
def bus(uow):
    """The central message bus."""
    return bootstrap(start_orm=False, uow=uow)


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


@pytest.fixture
def user_in_db(bus, user):
    with bus.uow as uow:
        uow.users.add(user)
        [from_db] = uow.users.get(user.name)
    return from_db


@pytest.fixture
def valid_access_token(user):
    return create_access_token({"type": "user", "user": user.name}, timedelta(minutes=5))


@pytest.fixture
def valid_access_token_in_db(user_in_db):
    return create_access_token({"type": "user", "user": user_in_db.name}, timedelta(minutes=5))


@pytest.fixture
def service():
    return model.Service(name="fastdeploytest", data={"foo": "bar"})


@pytest.fixture
def service_in_db(bus, service):
    with bus.uow as uow:
        uow.services.add(service)
        uow.commit()
        [from_db] = uow.services.get(service.name)
    return from_db
