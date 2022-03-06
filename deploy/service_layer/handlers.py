from typing import Callable, Type

from ..domain import commands, events
from ..service_layer.unit_of_work import AbstractUnitOfWork


async def delete_service(command: commands.DeleteService, uow: AbstractUnitOfWork):
    async with uow:
        [service] = await uow.services.get(command.service_id)
        await uow.services.delete(service)
        await uow.commit()
        service.delete()


async def publish_service_deleted_event(
    event: events.ServiceDeleted,
    publish: Callable,
):
    publish("service deleted: ", event)


EVENT_HANDLERS = {
    events.ServiceDeleted: [publish_service_deleted_event],
}  # type: dict[Type[events.Event], list[Callable]]

COMMAND_HANDLERS = {
    commands.DeleteService: delete_service,
}  # type: dict[Type[commands.Command], Callable]
