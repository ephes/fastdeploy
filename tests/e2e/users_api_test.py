import pytest

from httpx import AsyncClient

from deploy.auth import service_from_token
from deploy.entrypoints.routers.users import ServiceIn, UserOut


pytestmark = pytest.mark.asyncio


async def test_login_required_without_token(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(app.url_path_for("read_users_me"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


async def test_api_token(app, user_in_db, password):
    user = user_in_db
    # post username + password to login to get access token
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post(
            app.url_path_for("login_for_access_token"), data={"username": user.name, "password": password}
        )
    assert response.status_code == 200
    access_token = response.json().get("access_token")
    assert access_token is not None

    # use fetched token to assert we are authenticated now
    headers = {"authorization": f"Bearer {access_token}"}
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/users/me", headers=headers)

    assert response.status_code == 200
    assert response.json() == UserOut.model_validate(user).model_dump()


@pytest.fixture
def service_in(service):
    return ServiceIn(service=service.name, origin="GitHub")


async def test_fetch_service_token_no_access_token(app, service_in):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(app.url_path_for("service_token"), json=service_in.model_dump())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


async def test_fetch_service_token(app, service_in, service_in_db, valid_access_token_in_db, uow):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            app.url_path_for("service_token"),
            json=service_in.model_dump(),
            headers={"authorization": f"Bearer {valid_access_token_in_db}"},
        )

    assert response.status_code == 200
    token = response.json()["service_token"]
    service_token = await service_from_token(token, uow)
    assert service_in.service == service_token.name
