from __future__ import annotations

import abc

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..adapters import repository
from ..config import settings


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
    services: repository.AbstractServiceRepository
    users: repository.AbstractUserRepository
    deployments: repository.AbstractDeploymentRepository
    session: AbstractSession

    def __enter__(self) -> AbstractUnitOfWork:
        return self

    async def __aenter__(self) -> AbstractUnitOfWork:
        return self

    async def __aexit__(self, *args):
        await self.rollback()

    async def commit(self):
        await self._commit()

    def collect_new_events(self):
        for service in self.services.seen:
            while service.events:
                yield service.events.pop(0)

    @abc.abstractmethod
    async def _commit(self):
        raise NotImplementedError

    @abc.abstractmethod
    async def rollback(self):
        raise NotImplementedError


DEFAULT_SESSION_FACTORY = sessionmaker(bind=create_engine(settings.database_url, future=True))


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory=DEFAULT_SESSION_FACTORY):
        self.session_factory = session_factory

    async def __aenter__(self):
        self.session = await self.session_factory()
        self.services = repository.SqlAlchemyServiceRepository(self.session)
        self.users = repository.SqlAlchemyUserRepository(self.session)
        return super().__enter__()

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        await self.session.close()

    async def _commit(self):
        await self.session.commit()

    async def rollback(self):
        print("Rolling back")
        await self.session.rollback()


class TestableSqlAlchemyUnitOfWork(SqlAlchemyUnitOfWork):
    """
    Since we want to wrap our tests in a transaction we can roll
    back at the end of the test to leave the database untouched,
    we cannot use SqlAlchemyUnitOfWork directly. It will call
    session.close() and session.rollback() on __exit__. And this
    will trigger the outer transaction to rollback :(.

    Therefore we just override the __exit__ method and do nothing
    instead.

    See https://docs.sqlalchemy.org/en/14/orm/session_transaction.html
        #joining-a-session-into-an-external-transaction-such-as-for-test-suites
    """

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
        self.committed = False

    async def __aexit__(self, *args):
        await super().__aexit__(*args)

    async def _commit(self):
        self.committed = True

    async def rollback(self):
        pass
