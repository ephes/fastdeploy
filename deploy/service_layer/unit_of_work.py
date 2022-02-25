from __future__ import annotations

import abc

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..adapters import repository
from ..config import settings


class AbstractUnitOfWork(abc.ABC):
    services: repository.AbstractServiceRepository
    users: repository.AbstractUserRepository

    def __enter__(self) -> AbstractUnitOfWork:
        return self

    def __exit__(self, *args):
        self.rollback()

    def commit(self):
        self._commit()

    def collect_new_events(self):
        return []
        # for product in self.products.seen:
        #     while product.events:
        #         yield product.events.pop(0)

    @abc.abstractmethod
    def _commit(self):
        raise NotImplementedError

    @abc.abstractmethod
    def rollback(self):
        raise NotImplementedError


DEFAULT_SESSION_FACTORY = sessionmaker(bind=create_engine(settings.database_url, future=True))


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory=DEFAULT_SESSION_FACTORY):
        self.session_factory = session_factory

    def __enter__(self):
        self.session = self.session_factory()
        self.services = repository.SqlAlchemyServiceRepository(self.session)
        self.users = repository.SqlAlchemyUserRepository(self.session)
        return super().__enter__()

    def __exit__(self, *args):
        super().__exit__(*args)
        self.session.close()

    def _commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


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

    def __exit__(self, *args):
        pass
