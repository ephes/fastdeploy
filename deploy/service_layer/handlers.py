from typing import Callable, Type

from ..domain import commands, events, model
from ..service_layer.unit_of_work import AbstractUnitOfWork


def create_service(command: commands.CreateService, uow: AbstractUnitOfWork):
    with uow:
        service = model.Service(name=command.name, data=command.data)
        uow.services.add(service)
        uow.commit()


def delete_service(command: commands.DeleteService, uow: AbstractUnitOfWork):
    with uow:
        [service] = uow.services.get(command.service_id)
        uow.services.delete(service)
        uow.commit()
        service.delete()


def publish_service_deleted_event(
    event: events.ServiceDeleted,
    publish: Callable,
):
    publish("service deleted: ", event)


EVENT_HANDLERS = {
    events.ServiceDeleted: [publish_service_deleted_event],
}  # type: dict[Type[events.Event], list[Callable]]

COMMAND_HANDLERS = {
    commands.CreateService: create_service,
    commands.DeleteService: delete_service,
}  # type: dict[Type[commands.Command], Callable]
