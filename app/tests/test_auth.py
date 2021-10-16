import pytest

from httpx import AsyncClient

from ..auth import verify_password


def test_verify_password(user, password):
    assert verify_password(password, user.password)
    assert not verify_password("", user.password)


@pytest.mark.asyncio
async def test_login_required_without_token(app, base_url, user, password):
    async with AsyncClient(app=app, base_url=base_url) as client:
        response = await client.get("/users/me/")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
