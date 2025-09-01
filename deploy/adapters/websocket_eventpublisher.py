import logging

from ..domain import events
from .websocket import ConnectionManager

logger = logging.getLogger(__name__)


class WebsocketEventpublisher:
    def __init__(self, cm: ConnectionManager):
        self.cm = cm

    async def __call__(self, channel: str, event: events.Event):
        print("websocket event publisher: ", channel, event)
        logging.info("publishing: event=%s", event)
        await self.cm.publish(channel, event)
