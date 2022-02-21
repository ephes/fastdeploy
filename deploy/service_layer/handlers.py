from typing import Callable, Type

from ..domain import events, model


def create_service(name: str, data: dict) -> model.Service:
    return model.Service(name=name, data=data)


def publish_service_created_event(
    event: events.ServiceCreated,
    publish: Callable,
):
    publish("service created", event)


EVENT_HANDLERS = {
    events.ServiceCreated: [publish_service_created_event],
}  # type: dict[Type[events.Event], list[Callable]]

COMMAND_HANDLERS = {}
