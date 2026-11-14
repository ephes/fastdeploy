import inspect
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from starlette.requests import HTTPConnection

from .adapters import filesystem, orm
from .adapters.notifications import AbstractNotifications, EmailNotifications
from .adapters.websocket import connection_manager
from .adapters.websocket_eventpublisher import WebsocketEventpublisher

# from .adapters import orm, websocket_eventpublisher
from .config import settings
from .service_layer import handlers, messagebus, unit_of_work

logger = logging.getLogger(__name__)


async def bootstrap(
    start_orm: bool = True,
    uow: unit_of_work.AbstractUnitOfWork | None = None,
    connection_manager: Any = connection_manager,
    fs: filesystem.AbstractFilesystem = filesystem.Filesystem(settings.services_root),  # noqa: B008 -- import-time default is intended, callers/tests override it
    notifications: AbstractNotifications | None = None,
    publish: Callable | None = None,
    create_db_and_tables: bool = True,
) -> messagebus.MessageBus:
    owned_uow = None
    engine = None
    try:
        if uow is None:
            engine = create_async_engine(settings.database_url, echo=False)
            session_factory = sessionmaker(class_=AsyncSession, expire_on_commit=False)
            owned_uow = unit_of_work.SqlAlchemyUnitOfWork(engine, session_factory)
            uow = owned_uow
            await owned_uow.connect()
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
    except BaseException:
        if owned_uow is not None or engine is not None:
            try:
                if owned_uow is not None:
                    await owned_uow.close()
                elif engine is not None:
                    await engine.dispose()
            except BaseException as cleanup_error:
                # Cleanup must not replace the initiating startup failure.
                logger.error("bootstrap_cleanup_failed category=%s", type(cleanup_error).__name__)
        raise


def inject_dependencies(handler, dependencies):
    params = inspect.signature(handler).parameters
    deps = {name: dependency for name, dependency in dependencies.items() if name in params}
    return lambda message: handler(message, **deps)


@asynccontextmanager
async def database_lifespan(app):
    """Own one engine for the app lifetime. Serving never creates schema.

    NullPool keeps the per-request connection behaviour of the former
    engine-per-request setup: websockets hold their bus connection for their
    whole lifetime, so a shared bounded pool would let open dashboards or idle
    unauthenticated sockets starve runner step reports and deployment starts.
    """
    engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
    failed = False
    try:
        orm.start_mappers()
        app.state.database_session_factory = sessionmaker(class_=AsyncSession, expire_on_commit=False)
        app.state.database_engine = engine
        yield
    except BaseException:
        failed = True
        raise
    finally:
        app.state.database_engine = None
        app.state.database_session_factory = None
        try:
            await engine.dispose()
        except BaseException as cleanup_error:
            if not failed:
                raise
            logger.error("database_cleanup_failed category=%s", type(cleanup_error).__name__[:100])


async def get_bus(connection: HTTPConnection):
    # HTTP and websocket requests each own their UOW/connection/session, while
    # only the app lifespan owns disposal of the shared engine.
    uow = unit_of_work.SqlAlchemyUnitOfWork(
        connection.app.state.database_engine,
        connection.app.state.database_session_factory,
        owns_engine=False,
    )
    failed = False
    try:
        await uow.connect()
        bus = await bootstrap(uow=uow, start_orm=False, create_db_and_tables=False)
        yield bus
    except BaseException:
        failed = True
        raise
    finally:
        try:
            await uow.close()
        except BaseException as cleanup_error:
            if not failed:
                raise
            logger.error("request_cleanup_failed category=%s", type(cleanup_error).__name__[:100])


async def get_bus_for_cli():
    # The successful caller explicitly owns and closes bus.uow.
    return await bootstrap()
