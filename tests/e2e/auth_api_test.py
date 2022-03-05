import pytest

from httpx import AsyncClient

from deploy.entrypoints.routers.users import UserOut


pytestmark = pytest.mark.asyncio


async def test_login_required_without_token(app, base_url, user, password):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get(app.url_path_for("read_users_me"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_api_token(app, base_url, user_in_db, password):
    user = user_in_db
    # post username + password to login to get access token
    async with AsyncClient(app=app, base_url=base_url) as ac:
        response = await ac.post(
            app.url_path_for("login_for_access_token"), data={"username": user.name, "password": password}
        )
    assert response.status_code == 200
    access_token = response.json().get("access_token")
    assert access_token is not None

    # use fetched token to assert we are authenticated now
    headers = {"authorization": f"Bearer {access_token}"}
    async with AsyncClient(app=app, base_url=base_url) as ac:
        response = await ac.get("/users/me", headers=headers)

    assert response.status_code == 200
    assert response.json() == UserOut.from_orm(user).dict()
