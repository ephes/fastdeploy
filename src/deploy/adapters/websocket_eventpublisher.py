import logging

from ..domain import events
from .websocket import ConnectionManager

logger = logging.getLogger(__name__)


class WebsocketEventpublisher:
    def __init__(self, cm: ConnectionManager):
        self.cm = cm

    async def __call__(self, channel: str, event: events.Event):
        logger.info(
            "Publishing event=%s id=%s service_id=%s deployment_id=%s",
            type(event).__name__,
            getattr(event, "id", None),
            getattr(event, "service_id", None),
            getattr(event, "deployment_id", None),
        )
        await self.cm.publish(channel, event)
