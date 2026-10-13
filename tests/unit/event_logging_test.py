import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from deploy.adapters.websocket_eventpublisher import WebsocketEventpublisher
from deploy.domain import events
from deploy.service_layer.handlers import publish_event


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event",
    [
        events.DeploymentStarted(
            id=41,
            service_id=7,
            origin="test",
            user="user",
            started=datetime.now(timezone.utc),
            finished=None,
            context={"password": "sentinel-private-value"},
        ),
        events.ServiceUpdated(id=7, name="sentinel-private-value", data={"token": "sentinel-private-value"}),
        events.StepProcessed(
            id=9,
            deployment_id=41,
            name="sentinel-private-value",
            message="sentinel-private-value",
            state="success",
            started=None,
            finished=None,
        ),
    ],
)
async def test_event_publishers_log_metadata_only(event, caplog, capsys):
    cm = AsyncMock()
    publisher = WebsocketEventpublisher(cm)
    with caplog.at_level(logging.INFO):
        await publish_event(event, publisher)

    diagnostic = caplog.text + capsys.readouterr().out
    assert "sentinel-private-value" not in diagnostic
    assert type(event).__name__ in diagnostic
    assert f"id={event.id}" in diagnostic
    if isinstance(event, events.DeploymentStarted):
        assert "service_id=7" in diagnostic
    for record in caplog.records:
        assert f"id={event.id}" in record.getMessage()
        assert "sentinel-private-value" not in record.getMessage()
    cm.publish.assert_awaited_once_with("broadcast", event)
