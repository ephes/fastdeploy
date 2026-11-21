from __future__ import annotations

import abc
import logging
from contextlib import suppress

from ..adapters import repository

logger = logging.getLogger(__name__)


class AbstractSession(abc.ABC):
    @abc.abstractmethod
    def expunge_all(self):
        raise NotImplementedError

    @abc.abstractmethod
    def expunge(self, obj):
        raise NotImplementedError

    @abc.abstractmethod
    def close(self):
        raise NotImplementedError

    @abc.abstractmethod
    def commit(self):
        raise NotImplementedError

    @abc.abstractmethod
    def rollback(self):
        raise NotImplementedError


class AbstractUnitOfWork(abc.ABC):
    engine = None
    connection = None
    services: repository.AbstractServiceRepository
    users: repository.AbstractUserRepository
    deployments: repository.AbstractDeploymentRepository
    steps: repository.AbstractStepRepository
    session: AbstractSession
    deployed_services: repository.AbstractDeployedServiceRepository
    service_tokens: repository.AbstractServiceTokenRepository

    async def __aenter__(self) -> AbstractUnitOfWork:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        try:
            await self.rollback()
        except Exception as cleanup_error:
            if exc_type is None:
                raise
            # Keep the initiating failure (including cancellation) and record
            # only a bounded category, never cleanup messages or a traceback.
            with suppress(Exception):
                logger.error("uow_rollback_failed category=%s", type(cleanup_error).__name__[:100])

    async def commit(self):
        await self._commit()

    @abc.abstractmethod
    async def flush(self):
        """
        Send pending changes to the database without committing, so that new
        models get their ids while the transaction (and its locks) stays open.
        """
        raise NotImplementedError

    def collect_new_events(self):
        for repo in [self.services, self.deployments, self.steps, self.users]:
            for model in repo.seen.values():
                model.raise_recorded_events()
                while model.events:
                    yield model.events.pop(0)

    @abc.abstractmethod
    async def _commit(self):
        raise NotImplementedError

    @abc.abstractmethod
    async def rollback(self):
        raise NotImplementedError


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, engine, session_factory, *, owns_engine: bool = True):
        self.engine = engine
        self.owns_engine = owns_engine
        self._engine_needs_disposal = True
        self.session_factory = session_factory
        self.connection = None

    async def connect(self):
        """
        Being able to explicitly control when the connection starts. This
        is called at the beginning of each web request via `bootstrap.get_bus`.
        """
        self._engine_needs_disposal = True
        self.connection = await self.engine.connect()
        self.session = self.session_factory(bind=self.connection)

    async def close(self):
        """
        Being able to explicitly control when the connection is closed.
        This is called at the end of each web request via `bootstrap.get_bus`.
        """
        # Release ownership before the first await so a second close cannot
        # retry failed cleanup or race the current cleanup for these handles.
        session = getattr(self, "session", None)
        if session is not None:
            del self.session
        connection, self.connection = self.connection, None
        engine = self.engine if self.owns_engine and self._engine_needs_disposal else None
        self._engine_needs_disposal = False
        try:
            if session is not None:
                await session.close()
        finally:
            try:
                if connection is not None:
                    await connection.close()
            finally:
                if engine is not None:
                    await engine.dispose()

    async def __aenter__(self):
        self.services = repository.SqlAlchemyServiceRepository(self.session)
        self.users = repository.SqlAlchemyUserRepository(self.session)
        self.deployments = repository.SqlAlchemyDeploymentRepository(self.session)
        self.steps = repository.SqlAlchemyStepRepository(self.session)
        self.deployed_services = repository.SqlAlchemyDeployedServiceRepository(self.session)
        self.service_tokens = repository.SqlAlchemyServiceTokenRepository(self.session)
        return await super().__aenter__()

    async def __aexit__(self, exc_type, exc_value, traceback):
        primary = (exc_type, exc_value, traceback)
        try:
            try:
                self.session.expunge_all()
            except Exception as cleanup_error:
                if exc_type is None:
                    primary = (type(cleanup_error), cleanup_error, cleanup_error.__traceback__)
                    raise
                with suppress(Exception):
                    logger.error("uow_expunge_failed category=%s", type(cleanup_error).__name__[:100])
        finally:
            # Rollback must run even when detaching rows fails. With no body
            # failure, the expunge error becomes primary for the base guard.
            await super().__aexit__(*primary)

    async def _commit(self):
        await self.session.commit()

    async def flush(self):
        await self.session.flush()

    async def rollback(self):
        await self.session.rollback()


class TestableSqlAlchemyUnitOfWork(SqlAlchemyUnitOfWork):
    """
    Since we want to wrap our tests in a transaction we can roll
    back at the end of the test to leave the database untouched,
    we cannot use SqlAlchemyUnitOfWork directly. It will call
    session.close() and session.rollback() on __exit__. And this
    will trigger the outer transaction to rollback :(.

    Therefore, we just override the __exit__ method and do nothing
    instead.

    See https://docs.sqlalchemy.org/en/14/orm/session_transaction.html
        #joining-a-session-into-an-external-transaction-such-as-for-test-suites
    """

    async def __aenter__(self):
        """
        Create a new connection implicitly when used in an async context_manager.
        """
        await self.connect()
        return await super().__aenter__()

    async def __aexit__(self, *args):
        pass


class DoNothingSession(AbstractSession):
    def expunge_all(self):
        pass

    def expunge(self, obj):
        pass

    def close(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


class InMemoryUnitOfWork(AbstractUnitOfWork):
    def __init__(self):
        self.session = DoNothingSession()
        self.services = repository.InMemoryServiceRepository()
        self.users = repository.InMemoryUserRepository()
        self.steps = repository.InMemoryStepRepository()
        self.deployments = repository.InMemoryDeploymentRepository(self.steps)
        self.deployed_services = repository.InMemoryDeployedServiceRepository()
        self.service_tokens = repository.InMemoryServiceTokenRepository()
        self.committed = False

    async def __aexit__(self, *args):
        await super().__aexit__(*args)

    async def _commit(self):
        self.committed = True

    async def flush(self):
        pass  # ids are assigned when a model is added

    async def rollback(self):
        pass
