import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from deploy.adapters.repository import SqlAlchemyDeployedServiceRepository
from deploy.domain import commands, events, model
from deploy.service_layer.messagebus import MessageBus


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        events.DeploymentStarted(
            id=41,
            service_id=7,
            origin="private-payload",
            user="private-payload",
            started=datetime.now(timezone.utc),
            finished=None,
            context={"password": "private-payload"},
        ),
        events.ServiceUpdated(id=7, name="private-payload", data={"token": "private-payload"}),
        events.StepProcessed(
            id=9,
            deployment_id=41,
            name="private-payload",
            message="private-payload",
            state="success",
            started=None,
            finished=None,
        ),
        commands.StartDeployment(
            service_id=7, user="private-payload", origin="private-payload", context={"password": "private-payload"}
        ),
        commands.CreateService(name="private-payload", data={"token": "private-payload"}),
        commands.FinishDeployment(deployment_id=41),
    ],
)
@pytest.mark.parametrize("fails", [False, True])
async def test_messagebus_logs_metadata_only(message, fails, caplog):
    failure = RuntimeError("handler failed")
    handler = AsyncMock(side_effect=failure if fails else None, return_value="result")
    # A callable's repr can also hold bound arguments containing secrets.
    handler.__str__ = Mock(return_value="private-handler-payload")
    next_handler = AsyncMock()
    uow = Mock()
    uow.collect_new_events.return_value = []
    bus = MessageBus(
        fs=Mock(),
        cm=Mock(),
        uow=uow,
        event_handlers={type(message): [handler, next_handler]},
        command_handlers={type(message): handler},
    )
    with caplog.at_level(logging.DEBUG, logger="deploy.service_layer.messagebus"):
        if fails and isinstance(message, commands.Command):
            with pytest.raises(RuntimeError) as raised:
                await bus.handle(message)
            assert raised.value is failure
        else:
            result = await bus.handle(message)
            if isinstance(message, commands.Command):
                assert result == "result"
    handler.assert_awaited_once_with(message)
    if isinstance(message, events.Event):
        next_handler.assert_awaited_once_with(message)
    records = [record for record in caplog.records if record.name == "deploy.service_layer.messagebus"]
    assert records
    for record in records:
        diagnostic = record.getMessage()
        action = "Exception handling" if record.levelno == logging.ERROR else "handling"
        kind = "event" if isinstance(message, events.Event) else "command"
        assert diagnostic == (
            f"{action} {kind}={type(message).__name__} "
            f"id={getattr(message, 'id', None)} "
            f"service_id={getattr(message, 'service_id', None)} "
            f"deployment_id={getattr(message, 'deployment_id', None)}"
        )
        assert "private-payload" not in diagnostic
        assert "private-handler-payload" not in diagnostic
    errors = [record for record in records if record.levelno == logging.ERROR]
    assert len(errors) == int(fails)
    if fails:
        assert errors[0].exc_info[1] is failure
        assert errors[0].exc_info[2] is not None
        assert "Traceback" in caplog.text


@pytest.mark.asyncio
async def test_deployed_service_add_emits_no_stdout(capsys):
    session = Mock()
    repository = SqlAlchemyDeployedServiceRepository(session)
    deployed_service = model.DeployedService(deployment_id=41, config={"password": "private-payload"})
    await repository.add(deployed_service)
    session.add.assert_called_once_with(deployed_service)
    assert deployed_service in repository.seen
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
