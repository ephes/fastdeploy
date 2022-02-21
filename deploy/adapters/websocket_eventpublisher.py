import logging

from ..domain import events
from ..websocket import connection_manager


logger = logging.getLogger(__name__)


async def publish(event: events.Event):
    logging.info("publishing: event=%s", event)
    await connection_manager.handle_event(event)
