import pytest

from sqlmodel import Session

from ..auth import get_password_hash
from ..config import settings
from ..main import app as fastapi_app
from ..models import User, create_database


@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    # runs before test starts
    create_database()
    yield
    # runs after test ends
    ...


@pytest.fixture
def password():
    return "password"


@pytest.fixture
def user(password):
    return User(name="user", password=get_password_hash(password))


@pytest.fixture
def session():
    with Session(settings.db_engine) as session:
        yield session


@pytest.fixture
def user_in_db(session, password):
    user = User(name="user", password=get_password_hash(password), is_active=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    yield user
    session.delete(user)
    session.commit()


@pytest.fixture
def app():
    return fastapi_app


@pytest.fixture
def base_url():
    return "http://test"
