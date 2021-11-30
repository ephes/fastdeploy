from datetime import timedelta

import pytest

from sqlmodel import SQLModel

from .. import database
from ..auth import create_access_token, get_password_hash
from ..main import app as fastapi_app
from ..models import Deployment, Service, Step, StepBase, User
from ..routers.users import ServiceIn


@pytest.fixture
def repository():
    yield database.repository
    # after test ran, drop all tables and recreate them
    # to bring the database back into a clean state
    database.repository.reset()


@pytest.fixture
def password():
    return "password"


@pytest.fixture
def user(password):
    return User(name="user", password=get_password_hash(password))


@pytest.fixture
def service():
    return Service(name="fastdeploy", data={"foo": "bar"})


@pytest.fixture
async def service_in_db(repository, service):
    return await repository.add_service(service)


@pytest.fixture
def deployment(service_in_db):
    return Deployment(service_id=service_in_db.id, origin="github", user="fastdeploy")


@pytest.fixture
async def deployment_in_db(repository, deployment):
    return await repository.add_deployment(deployment)


@pytest.fixture
async def different_deployment_in_db(repository, deployment):
    different_deployment = Deployment(service_id=deployment.service_id + 1, origin="foo", user="bar")
    return await repository.add_deployment(different_deployment)


@pytest.fixture
async def user_in_db(repository, user):
    return await repository.add_user(user)


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
async def step_in_db(repository, step, deployment_in_db):
    step = Step(name=step.name, deployment_id=deployment_in_db.id)
    return await repository.add_step(step)


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


@pytest.fixture
def handler(repository):
    class Handler:
        async def handle_event(self, event):
            self.last_event = event

    handler = Handler()
    repository.register_event_handler(handler)

    return handler
