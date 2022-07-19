from __future__ import annotations

import abc

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
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
    engine = None
    connection = None
    services: repository.AbstractServiceRepository
    users: repository.AbstractUserRepository
    deployments: repository.AbstractDeploymentRepository
    steps: repository.AbstractStepRepository
    session: AbstractSession
    deployed_services: repository.AbstractDeployedServiceRepository

    async def __aenter__(self) -> AbstractUnitOfWork:
        return self

    async def __aexit__(self, *args):
        await self.rollback()

    async def commit(self):
        await self._commit()

    def collect_new_events(self):
        for repo in [self.services, self.deployments, self.steps, self.users]:
            for model in repo.seen:
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
    def __init__(self):
        self.engine = create_async_engine(settings.database_url, echo=False)
        self.session_factory = sessionmaker(class_=AsyncSession, expire_on_commit=False)
        self.connection = None

    async def connect(self):
        """
        Being able to explicitly control when the connection starts. This
        is called at the beginning of each web request via `bootstrap.get_bus`.
        """
        self.connection = await self.engine.connect()
        self.session = self.session_factory(bind=self.connection)

    async def close(self):
        """
        Being able to explicitly control when the connection is closed.
        This is called at the end of each web request via `bootstrap.get_bus`.
        """
        await self.session.close()
        await self.connection.close()
        await self.engine.dispose()

    async def __aenter__(self):
        self.services = repository.SqlAlchemyServiceRepository(self.session)
        self.users = repository.SqlAlchemyUserRepository(self.session)
        self.deployments = repository.SqlAlchemyDeploymentRepository(self.session)
        self.steps = repository.SqlAlchemyStepRepository(self.session)
        self.deployed_services = repository.SqlAlchemyDeployedServiceRepository(self.session)
        return await super().__aenter__()

    async def __aexit__(self, *args):
        self.session.expunge_all()
        await super().__aexit__(*args)

    async def _commit(self):
        await self.session.commit()

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
        self.connection = await self.engine.connect()
        self.session = self.session_factory(bind=self.connection)
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
        self.deployments = repository.InMemoryDeploymentRepository()
        self.steps = repository.InMemoryStepRepository()
        self.deployed_services = repository.InMemoryDeployedServiceRepository()
        self.committed = False

    async def __aexit__(self, *args):
        await super().__aexit__(*args)

    async def _commit(self):
        self.committed = True

    async def rollback(self):
        pass
