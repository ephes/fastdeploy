import pytest

from sqlmodel import Session, SQLModel

from .. import database
from ..auth import get_password_hash
from ..main import app as fastapi_app
from ..models import User


@pytest.fixture
def password():
    return "password"


@pytest.fixture
def user(password):
    return User(name="user", password=get_password_hash(password))


@pytest.fixture
def cleanup_database_after_test():
    database.create_db_and_tables()
    yield
    # after test ran, drop all tables and recreate them
    # to bring the database back into a clean state
    SQLModel.metadata.drop_all(database.engine)


@pytest.fixture
def user_in_db(cleanup_database_after_test, password):
    user = User(name="user", password=get_password_hash(password), is_active=True)
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
