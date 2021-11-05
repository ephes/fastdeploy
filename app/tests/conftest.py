from datetime import timedelta

import pytest

from sqlmodel import Session, SQLModel

from .. import database
from ..auth import create_access_token, get_password_hash
from ..main import app as fastapi_app
from ..models import Deployment, Service, Step, StepBase, User
from ..routers.users import ServiceIn


@pytest.fixture
def repository():
    return database.repository


@pytest.fixture
def password():
    return "password"


@pytest.fixture
def user(password):
    return User(name="user", password=get_password_hash(password))


@pytest.fixture
def service():
    return Service(name="fastdeploy", collect="fastdeploy_collect.py", deploy="fastdeploy_deploy.sh")


@pytest.fixture
def service_in_db(cleanup_database_after_test, repository, service):
    return repository.add_service(service)


@pytest.fixture
def deployment(service_in_db):
    return Deployment(service_id=service_in_db.id)


@pytest.fixture
def deployment_in_db(cleanup_database_after_test, deployment):
    with Session(database.engine) as session:
        session.add(deployment)
        session.commit()
        session.refresh(deployment)
    return deployment


@pytest.fixture
def different_deployment_in_db(cleanup_database_after_test, deployment):
    deployment.id += 1
    with Session(database.engine) as session:
        session.add(deployment)
        session.commit()
        session.refresh(deployment)
    return deployment


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
    return create_access_token({"type": "user", "user": user.name}, timedelta(minutes=5))


@pytest.fixture
def valid_access_token_in_db(user_in_db):
    return create_access_token({"type": "user", "user": user_in_db.name}, timedelta(minutes=5))


@pytest.fixture
def invalid_access_token(user):
    return create_access_token({"type": "user", "user": user.name}, timedelta(minutes=-5))


@pytest.fixture
def invalid_service_token(service):
    return create_access_token(
        {"type": "service", "user": "foobar", "origin": "GitHub", "service": service.name}, timedelta(minutes=-5)
    )


@pytest.fixture
def valid_service_token(service):
    return create_access_token(
        {"type": "service", "user": "foobar", "origin": "GitHub", "service": service.name}, timedelta(minutes=5)
    )


@pytest.fixture
def valid_service_token_in_db(service_in_db):
    data = {"type": "service", "service": service_in_db.name, "origin": "GitHub", "user": "foobar"}
    return create_access_token(data, timedelta(minutes=5))


@pytest.fixture
def stub_websocket():
    class StubWebsocket:
        sent = []
        has_accepted = False

        async def send_json(self, message):
            self.sent.append(message)

        async def send_text(self, message):
            self.sent.append(message)

        async def accept(self):
            self.has_accepted = True

    return StubWebsocket()


@pytest.fixture
def step():
    return StepBase(name="foo bar baz")


@pytest.fixture
def step_in_db(step, deployment_in_db):
    step = Step(name=step.name, deployment_id=deployment_in_db.id)
    with Session(database.engine) as session:
        session.add(step)
        session.commit()
        session.refresh(step)
    return step


@pytest.fixture
def invalid_deploy_token():
    return create_access_token({"type": "deployment", "deployment": 1}, timedelta(minutes=-5))


@pytest.fixture
def valid_deploy_token(deployment):
    data = {"type": "deployment", "deployment": deployment.id}
    return create_access_token(data, timedelta(minutes=5))


@pytest.fixture
def valid_deploy_token_in_db(deployment_in_db):
    data = {"type": "deployment", "deployment": deployment_in_db.id}
    return create_access_token(data, timedelta(minutes=5))


@pytest.fixture
def valid_different_deploy_token_in_db(different_deployment_in_db):
    data = {"type": "deployment", "deployment": different_deployment_in_db.id}
    return create_access_token(data, timedelta(minutes=5))


@pytest.fixture
def origin():
    return "GitHub"


@pytest.fixture
def service_in(service, origin):
    return ServiceIn(service=service.name, origin=origin)


@pytest.fixture
def test_message():
    class Message(SQLModel):
        test: str = "message"

    return Message()
