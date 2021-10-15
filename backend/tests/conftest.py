import pytest

from ..models import User


@pytest.fixture
def password():
    return "password"


@pytest.fixture
def user(password):
    return User(name="user", password=password)
