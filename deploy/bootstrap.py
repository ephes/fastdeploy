import inspect

from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .adapters import filesystem, orm
from .adapters.notifications import AbstractNotifications, EmailNotifications
from .adapters.websocket import connection_manager
from .adapters.websocket_eventpublisher import WebsocketEventpublisher

# from .adapters import orm, websocket_eventpublisher
from .config import settings
from .service_layer import handlers, messagebus, unit_of_work


async def bootstrap(
    start_orm: bool = True,
    uow: unit_of_work.AbstractUnitOfWork | None = None,
    connection_manager: Any = connection_manager,
    fs: filesystem.AbstractFilesystem = filesystem.Filesystem(settings.services_root),
    notifications: AbstractNotifications | None = None,
    publish: Callable | None = None,
    create_db_and_tables: bool = True,
) -> messagebus.MessageBus:

    if uow is None:
        uow = unit_of_work.SqlAlchemyUnitOfWork()
        await uow.connect()

    if notifications is None:
        notifications = EmailNotifications()

    if publish is None:
        publish = WebsocketEventpublisher(connection_manager)

    if start_orm:
        orm.start_mappers()

    if create_db_and_tables:
        await orm.create_db_and_tables(uow.engine)

    dependencies = {"uow": uow, "notifications": notifications, "publish": publish, "fs": fs}

    injected_event_handlers = {
        event_type: [inject_dependencies(handler, dependencies) for handler in event_handlers]
        for event_type, event_handlers in handlers.EVENT_HANDLERS.items()
    }
    injected_command_handlers = {
        command_type: inject_dependencies(handler, dependencies)
        for command_type, handler in handlers.COMMAND_HANDLERS.items()
    }

    return messagebus.MessageBus(
        fs=fs,
        cm=connection_manager,
        uow=uow,
        event_handlers=injected_event_handlers,
        command_handlers=injected_command_handlers,
    )


def inject_dependencies(handler, dependencies):
    params = inspect.signature(handler).parameters
    deps = {name: dependency for name, dependency in dependencies.items() if name in params}
    return lambda message: handler(message, **deps)


async def get_bus():
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = sessionmaker(class_=AsyncSession, expire_on_commit=False)
    uow = unit_of_work.SqlAlchemyUnitOfWork(engine, session_factory)
    await uow.connect()
    bus = await bootstrap(uow=uow)
    try:
        yield bus
    finally:
        await bus.uow.close()
