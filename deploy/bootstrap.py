import inspect

from typing import Callable

# from .adapters import orm, websocket_eventpublisher
from .adapters import orm
from .adapters.notifications import AbstractNotifications, EmailNotifications
from .service_layer import handlers, messagebus, unit_of_work


def bootstrap(
    start_orm: bool = True,
    uow: unit_of_work.AbstractUnitOfWork = unit_of_work.SqlAlchemyUnitOfWork(),
    notifications: AbstractNotifications = None,
    publish: Callable = lambda *args: None,
    create_db_and_tables: bool = True,
    # publish: Callable = websocket_eventpublisher.publish,
) -> messagebus.MessageBus:

    if notifications is None:
        notifications = EmailNotifications()

    if start_orm:
        orm.start_mappers()

    if create_db_and_tables:
        orm.create_db_and_tables()

    dependencies = {"uow": uow, "notifications": notifications, "publish": publish}

    injected_event_handlers = {
        event_type: [inject_dependencies(handler, dependencies) for handler in event_handlers]
        for event_type, event_handlers in handlers.EVENT_HANDLERS.items()
    }
    injected_command_handlers = {
        command_type: inject_dependencies(handler, dependencies)
        for command_type, handler in handlers.COMMAND_HANDLERS.items()
    }

    return messagebus.MessageBus(
        uow=uow,
        event_handlers=injected_event_handlers,
        command_handlers=injected_command_handlers,
    )


def inject_dependencies(handler, dependencies):
    params = inspect.signature(handler).parameters
    deps = {name: dependency for name, dependency in dependencies.items() if name in params}
    return lambda message: handler(message, **deps)


# bus = bootstrap()


def get_bus() -> messagebus.MessageBus:
    return bootstrap()
