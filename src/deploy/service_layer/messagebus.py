import logging
from collections.abc import Callable
from typing import Any, Union

from ..adapters import filesystem, websocket
from ..domain import commands, events
from . import unit_of_work

logger = logging.getLogger(__name__)

Message = Union[commands.Command, events.Event]


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

    async def handle(self, message: Message) -> Any:
        """
        Handle a message and all events raised while handling it. Returns
        the result of the command handler if the message was a command.
        """
        result = None
        initial = message
        self.queue = [message]
        while self.queue:
            message = self.queue.pop(0)
            if isinstance(message, events.Event):
                await self.handle_event(message)
            elif isinstance(message, commands.Command):
                handler_result = await self.handle_command(message)
                if message is initial:
                    result = handler_result
            else:
                raise Exception(f"{message} was not an Event or Command")
        return result

    async def handle_event(self, event: events.Event):
        for handler in self.event_handlers[type(event)]:
            try:
                logger.debug("handling event %s with handler %s", event, handler)
                await handler(event)
                self.queue.extend(self.uow.collect_new_events())
            except Exception:
                logger.exception("Exception handling event %s", event)
                continue

    async def handle_command(self, command: commands.Command) -> Any:
        logger.debug("handling command %s", command)
        try:
            handler = self.command_handlers[type(command)]
            result = await handler(command)
            self.queue.extend(self.uow.collect_new_events())
            return result
        except Exception:
            logger.exception("Exception handling command %s", command)
            raise
