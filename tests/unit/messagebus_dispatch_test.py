"""Dispatch contracts through the real message bus and a synthetic event source."""

import asyncio
import logging
from unittest.mock import Mock

import pytest

from deploy.domain import commands, events
from deploy.entrypoints.helper_models import Bus
from deploy.service_layer.messagebus import MessageBus


class StartChain(commands.Command):
    label: str = "initial"
    payload: str = "private-payload"


class Followup(events.Event):
    type: str = "synthetic"
    label: str
    payload: str = "private-payload"


class EventSource:
    def __init__(self):
        self.pending = []

    def publish(self, *messages):
        self.pending.extend(messages)

    def collect_new_events(self):
        pending, self.pending = self.pending, []
        yield from pending


def make_bus(source, command_handler, handlers):
    return MessageBus(
        fs=Mock(),
        cm=Mock(),
        uow=source,
        command_handlers={StartChain: command_handler},
        event_handlers={Followup: handlers},
    )


@pytest.mark.asyncio
async def test_followups_are_fifo_once_and_preserve_initial_result():
    source = EventSource()
    calls = []
    initial_result, independent_result = object(), object()

    async def command_handler(command):
        calls.append(("command", command.label))
        if command.label == "initial":
            source.publish(Followup(label="first"), Followup(label="second"))
            return initial_result
        return independent_result

    async def first_handler(event):
        calls.append(("first handler", event.label))
        if event.label == "first":
            source.publish(Followup(label="nested"))
        return "event result must not replace command result"

    async def second_handler(event):
        calls.append(("second handler", event.label))
        return "another event result"

    bus = make_bus(source, command_handler, [first_handler, second_handler])
    assert await bus.handle(StartChain()) is initial_result
    expected = [
        ("command", "initial"),
        ("first handler", "first"),
        ("second handler", "first"),
        ("first handler", "second"),
        ("second handler", "second"),
        ("first handler", "nested"),
        ("second handler", "nested"),
    ]
    assert calls == expected
    assert await bus.handle(StartChain(label="independent")) is independent_result
    assert calls == [*expected, ("command", "independent")]
    assert await bus.handle(Followup(label="standalone")) is None
    assert calls[-2:] == [("first handler", "standalone"), ("second handler", "standalone")]


@pytest.mark.asyncio
async def test_event_failure_continues_handlers_and_generated_chain(caplog):
    source = EventSource()
    calls = []
    command_result = object()
    failure = RuntimeError("synthetic handler failure")

    async def command_handler(command):
        source.publish(Followup(label="first"), Followup(label="second"))
        return command_result

    async def fragile_handler(event):
        calls.append(("fragile", event.label))
        if event.label == "first":
            raise failure

    async def next_handler(event):
        calls.append(("next", event.label))
        if event.label == "first":
            source.publish(Followup(label="nested"))

    bus = make_bus(source, command_handler, [fragile_handler, next_handler])
    with caplog.at_level(logging.DEBUG, logger="deploy.service_layer.messagebus"):
        assert await bus.handle(StartChain()) is command_result
    assert calls == [
        ("fragile", "first"),
        ("next", "first"),
        ("fragile", "second"),
        ("next", "second"),
        ("fragile", "nested"),
        ("next", "nested"),
    ]
    records = [record for record in caplog.records if record.name == "deploy.service_layer.messagebus"]
    errors = [record for record in records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].exc_info is None
    assert "category=RuntimeError" in errors[0].getMessage()
    assert str(failure) not in caplog.text
    assert "Exception handling event=Followup" in errors[0].getMessage()
    assert all("private-payload" not in record.getMessage() for record in records)


@pytest.mark.asyncio
async def test_command_failure_propagates_without_dispatching_generated_events_in_that_call(caplog):
    source = EventSource()
    calls = []
    failure = RuntimeError("synthetic command failure")

    async def command_handler(command):
        calls.append("command")
        source.publish(Followup(label="not dispatched"))
        raise failure

    async def event_handler(event):
        calls.append("event")

    bus = make_bus(source, command_handler, [event_handler])
    with (
        caplog.at_level(logging.DEBUG, logger="deploy.service_layer.messagebus"),
        pytest.raises(RuntimeError) as raised,
    ):
        await bus.handle(StartChain())
    assert raised.value is failure
    assert calls == ["command"]
    records = [record for record in caplog.records if record.name == "deploy.service_layer.messagebus"]
    errors = [record for record in records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].exc_info is None
    assert "category=RuntimeError" in errors[0].getMessage()
    assert str(failure) not in caplog.text
    assert "Exception handling command=StartChain" in errors[0].getMessage()
    assert all("private-payload" not in record.getMessage() for record in records)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_during", ["command", "event"])
async def test_cancellation_propagates_without_running_later_handlers(cancel_during, caplog):
    source = EventSource()
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def pause():
        entered.set()
        await release.wait()
        calls.append("released")

    async def command_handler(command):
        calls.append("command")
        source.publish(Followup(label="first"), Followup(label="second"))
        if cancel_during == "command":
            await pause()
        return "command result"

    async def first_handler(event):
        calls.append(("first handler", event.label))
        await pause()

    async def later_handler(event):
        calls.append(("later handler", event.label))

    bus = make_bus(source, command_handler, [first_handler, later_handler])
    with caplog.at_level(logging.DEBUG, logger="deploy.service_layer.messagebus"):
        task = asyncio.create_task(bus.handle(StartChain()))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=5)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    expected = ["command"] if cancel_during == "command" else ["command", ("first handler", "first")]
    assert calls == expected
    records = [record for record in caplog.records if record.name == "deploy.service_layer.messagebus"]
    assert records
    assert all(record.levelno < logging.ERROR for record in records)
    assert all("private-payload" not in record.getMessage() for record in records)


@pytest.mark.asyncio
@pytest.mark.parametrize("wrapped", [False, True])
async def test_reentrant_handle_refused_without_losing_outer_events(wrapped):
    source = EventSource()
    calls = []

    async def command_handler(command):
        calls.append(command.label)
        if command.label == "initial":
            source.publish(Followup(label="first"), Followup(label="second"))
        return command.label

    async def handler(event):
        calls.append(event.label)
        if event.label == "first":
            with pytest.raises(RuntimeError, match="already handling"):
                await bus.handle(StartChain(label="reentrant"))

    bus = make_bus(source, command_handler, [handler])
    if wrapped:
        bus = Bus(bus)
    assert await bus.handle(StartChain()) == "initial"
    assert calls == ["initial", "first", "second"]
    assert await bus.handle(StartChain(label="later")) == "later"
    assert calls == ["initial", "first", "second", "later"]


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["success", "failure", "cancel"])
@pytest.mark.parametrize("wrapped", [False, True])
async def test_overlapping_handle_refused_and_ownership_released(ending, wrapped):
    source = EventSource()
    entered, resume = asyncio.Event(), asyncio.Event()
    calls = []

    async def command_handler(command):
        calls.append(command.label)
        if command.label == "initial":
            source.publish(Followup(label="first"), Followup(label="second"))
        return command.label

    async def handler(event):
        calls.append(event.label)
        if event.label == "first":
            entered.set()
            await resume.wait()
            if ending == "failure":
                raise ValueError("synthetic event failure")

    bus = make_bus(source, command_handler, [handler])
    if wrapped:
        bus = Bus(bus)
    active = asyncio.create_task(bus.handle(StartChain()))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        with pytest.raises(RuntimeError, match="already handling"):
            await bus.handle(StartChain(label="overlap"))
        assert calls == ["initial", "first"]
    finally:
        if ending == "cancel":
            active.cancel()
        resume.set()
        results = await asyncio.gather(active, return_exceptions=True)
    if ending == "cancel":
        assert isinstance(results[0], asyncio.CancelledError)
        assert calls == ["initial", "first"]
    else:
        assert results == ["initial"]
        assert calls == ["initial", "first", "second"]
    assert await bus.handle(StartChain(label="later")) == "later"
    assert calls[-1] == "later"
