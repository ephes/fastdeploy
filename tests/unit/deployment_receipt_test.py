import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from deploy.domain import events, model
from deploy.entrypoints.routers.deployments import start_deployment
from deploy.tasks import DeploymentContext


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True], ids=["rejected", "cancelled"])
async def test_start_receipt_observer_is_scoped_to_the_request(cancelled):
    started = events.DeploymentStarted(
        id=42, service_id=1, origin="test", user="test", started=datetime.now(timezone.utc), finished=None
    )
    publisher = AsyncMock()
    observers = [publisher]
    delivery = []

    class ReusedBus:
        def __init__(self):
            self.event_handlers = {events.DeploymentStarted: observers}

        async def handle(self, command):
            if command.service_token == "first":
                if cancelled:
                    raise asyncio.CancelledError
                raise model.DeploymentAlreadyRunning(service_id=1, deployment_id=41)
            for observer in self.event_handlers[events.DeploymentStarted]:
                delivery.append(observer)
                await observer(started)

    bus = ReusedBus()
    request = Mock()
    request.url_for.return_value = "/deployments/42/"
    service = model.Service(id=1, name="synthetic")
    context = DeploymentContext(env={})

    with pytest.raises(asyncio.CancelledError if cancelled else HTTPException) as error:
        await start_deployment(request, "first", context, service, bus)
    if not cancelled:
        assert error.value.status_code == 409

    receipt = await start_deployment(request, "second", context, service, bus)
    assert receipt.id == started.id
    assert receipt.details == "/deployments/42/"
    assert len(delivery) == 2
    assert delivery[0] is publisher
    publisher.assert_awaited_once_with(started)
    assert observers == [publisher]
