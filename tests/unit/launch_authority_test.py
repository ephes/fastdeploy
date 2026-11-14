from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from jwt import InvalidTokenError

from deploy import auth
from deploy.config import settings
from deploy.domain import commands, model

pytestmark = [pytest.mark.asyncio, pytest.mark.db("in_memory")]


@pytest.mark.parametrize("change", ["revoke", "delete_user", "expire_record", "legacy_cutoff", "unchanged"])
async def test_start_rechecks_authenticated_credential(bus, service_in_db, user_in_db, monkeypatch, change):
    token, record = await auth.issue_service_token(
        service=service_in_db.name,
        user=user_in_db.name,
        origin="test",
        expires_delta=timedelta(minutes=5),
        uow=bus.uow,
    )
    if change == "legacy_cutoff":
        monkeypatch.setattr(
            settings, "legacy_service_tokens_accepted_until", datetime.now(timezone.utc) + timedelta(days=1)
        )
        token = auth.create_access_token({"type": "service", "service": service_in_db.name, "user": user_in_db.name})
    await auth.service_from_token(token, bus.uow)
    if change == "revoke":
        record.revoke(datetime.now(timezone.utc))
    elif change == "delete_user":
        bus.uow.users._users.clear()
    elif change == "expire_record":
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    elif change == "legacy_cutoff":
        monkeypatch.setattr(settings, "legacy_service_tokens_accepted_until", None)
    launched = Mock()
    monkeypatch.setattr(model.Deployment, "start_deployment_task", launched)
    command = commands.StartDeployment(
        service_id=service_in_db.id, user=user_in_db.name, origin="test", context={}, service_token=token
    )
    if change == "unchanged":
        await bus.handle(command)
        launched.assert_called_once()
        assert len(await bus.uow.deployments.list()) == 1
    else:
        with pytest.raises((auth.InvalidCredentials, InvalidTokenError)):
            await bus.handle(command)
        launched.assert_not_called()
        assert await bus.uow.deployments.list() == []
