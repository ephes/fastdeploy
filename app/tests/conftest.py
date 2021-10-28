from datetime import timedelta

import pytest

from sqlmodel import Session, SQLModel

from .. import database
from ..auth import create_access_token, get_password_hash
from ..main import app as fastapi_app
from ..models import Service, Step, User


@pytest.fixture
def password():
    return "password"


@pytest.fixture
def user(password):
    return User(name="user", password=get_password_hash(password))


@pytest.fixture
def service():
    return Service(name="fastdeploy")


@pytest.fixture
def service_in_db(cleanup_database_after_test, service):
    with Session(database.engine) as session:
        session.add(service)
        session.commit()
        session.refresh(service)
    return service


@pytest.fixture
def cleanup_database_after_test():
    database.create_db_and_tables()
    yield
    # after test ran, drop all tables and recreate them
    # to bring the database back into a clean state
    SQLModel.metadata.drop_all(database.engine)


@pytest.fixture
def user_in_db(cleanup_database_after_test, user):
    with Session(database.engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


@pytest.fixture
def app():
    return fastapi_app


@pytest.fixture
def base_url():
    return "http://test"


@pytest.fixture
def valid_access_token(user):
    return create_access_token({"user": user.name}, timedelta(minutes=5))


@pytest.fixture
def valid_access_token_in_db(user_in_db):
    return create_access_token({"user": user_in_db.name}, timedelta(minutes=5))


@pytest.fixture
def invalid_access_token(user):
    return create_access_token({"user": user.name}, timedelta(minutes=-5))


@pytest.fixture
def invalid_service_token(service):
    return create_access_token({"service": service.name}, timedelta(minutes=-5))


@pytest.fixture
def valid_service_token(service):
    return create_access_token({"service": service.name}, timedelta(minutes=5))


@pytest.fixture
def valid_service_token_in_db(service_in_db):
    data = {
        "service": service_in_db.name,
        "origin": "GitHub",
    }
    return create_access_token(data, timedelta(minutes=5))


@pytest.fixture
def stub_websocket():
    class StubWebsocket:
        sent = []
        has_accepted = False

        async def send_json(self, message):
            self.sent.append(message)

        async def accept(self):
            self.has_accepted = True

    return StubWebsocket()


@pytest.fixture
def step():
    return Step(id=1, deployment_id=23)
