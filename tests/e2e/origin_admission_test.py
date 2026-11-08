"""HTTP origin storage contract before issuance and retention cleanup."""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from deploy import auth
from deploy.config import settings

pytestmark = [pytest.mark.asyncio, pytest.mark.db("in_memory")]


@pytest.mark.parametrize("length", [255, 256])
async def test_unicode_origin_limit(
    app, bus, service_in_db, user_in_db, valid_access_token_in_db, monkeypatch, length
):
    monkeypatch.setattr(settings, "service_token_admin_users", [user_in_db.name])
    with patch.object(auth, "issue_service_token", wraps=auth.issue_service_token) as issue:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/service-token",
                json={"service": service_in_db.name, "origin": "界" * length},
                headers={"authorization": f"Bearer {valid_access_token_in_db}"},
            )
        assert response.status_code == (200 if length == 255 else 422)
        if length == 255:
            assert (
                await auth.service_from_token(response.json()["service_token"], bus.uow)
            ).name == service_in_db.name
        else:
            issue.assert_not_called()
            assert len(response.text) < 250
