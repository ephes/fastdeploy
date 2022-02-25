from typing import Callable, Type

from ..domain import commands, events, model
from ..service_layer.unit_of_work import AbstractUnitOfWork


def create_service(command: commands.CreateService, uow: AbstractUnitOfWork):
    print("in create service: ", command)
    with uow:
        service = model.Service(name=command.name, data=command.data)
        uow.services.add(service)
        uow.commit()


def publish_service_created_event(
    event: events.ServiceCreated,
    publish: Callable,
):
    publish("service created", event)


EVENT_HANDLERS = {
    events.ServiceCreated: [publish_service_created_event],
}  # type: dict[Type[events.Event], list[Callable]]

COMMAND_HANDLERS = {
    commands.CreateService: create_service,
}  # type: dict[Type[commands.Command], Callable]
