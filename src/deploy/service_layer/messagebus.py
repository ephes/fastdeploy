import logging
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from ..adapters import filesystem, websocket
from ..domain import commands, events
from . import unit_of_work

logger = logging.getLogger(__name__)

Message = commands.Command | events.Event


def _log_dispatch(kind: str, message: Message) -> None:
    with suppress(Exception):
        logger.debug(
            "handling %s=%s id=%s service_id=%s deployment_id=%s",
            kind,
            type(message).__name__,
            getattr(message, "id", None),
            getattr(message, "service_id", None),
            getattr(message, "deployment_id", None),
        )


def _log_dispatch_error(kind: str, message: Message, error: Exception) -> None:
    # A failing diagnostic sink must not interrupt dispatch or mask its error.
    with suppress(Exception):
        logger.error(
            "Exception handling %s=%s id=%s service_id=%s deployment_id=%s category=%s",
            kind,
            type(message).__name__,
            getattr(message, "id", None),
            getattr(message, "service_id", None),
            getattr(message, "deployment_id", None),
            type(error).__name__[:100],
        )


class MessageBus:
    def __init__(
        self,
        fs: filesystem.AbstractFilesystem,
        cm: websocket.ConnectionManager,
        uow: unit_of_work.AbstractUnitOfWork,
        event_handlers: dict[type[events.Event], list[Callable]],
        command_handlers: dict[type[commands.Command], Callable],
    ):
        self.fs = fs
        self.cm = cm
        self.uow = uow
        self.event_handlers = event_handlers
        self.command_handlers = command_handlers
        self._handling = False

    async def handle(self, message: Message) -> Any:
        """
        Handle a message and all events raised while handling it. Returns
        the result of the command handler if the message was a command.
        One operation owns this bus/UOW; overlapping calls raise RuntimeError.
        """
        if self._handling:
            raise RuntimeError("Message bus is already handling a message")
        self.queue: deque[Message] = deque([message])
        self._handling = True
        try:
            result = None
            initial = message
            while self.queue:
                message = self.queue.popleft()
                if isinstance(message, events.Event):
                    await self.handle_event(message)
                elif isinstance(message, commands.Command):
                    handler_result = await self.handle_command(message)
                    if message is initial:
                        result = handler_result
                else:
                    raise Exception(f"{message} was not an Event or Command")
            return result
        finally:
            self.queue.clear()
            self._handling = False

    async def handle_event(self, event: events.Event):
        for handler in self.event_handlers.get(type(event), ()):
            _log_dispatch("event", event)
            try:
                await handler(event)
                self.queue.extend(self.uow.collect_new_events())
            except Exception as exc:
                _log_dispatch_error("event", event, exc)

    async def handle_command(self, command: commands.Command) -> Any:
        _log_dispatch("command", command)
        try:
            handler = self.command_handlers[type(command)]
            result = await handler(command)
            self.queue.extend(self.uow.collect_new_events())
            return result
        except Exception as exc:
            _log_dispatch_error("command", command, exc)
            raise
