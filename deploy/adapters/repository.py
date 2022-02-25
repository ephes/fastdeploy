import abc

from sqlalchemy import select

from ..domain import model


class AbstractServiceRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, service) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get(self, name) -> tuple[model.Service]:
        raise NotImplementedError

    @abc.abstractmethod
    def list(self) -> list[tuple[model.Service]]:
        raise NotImplementedError


class SqlAlchemyServiceRepository(AbstractServiceRepository):
    def __init__(self, session):
        self.session = session

    def add(self, service):
        self.session.add(service)

    def get(self, name):
        stmt = select(model.Service).where(model.Service.name == name)
        return self.session.execute(stmt).one()

    def list(self):
        return self.session.execute(select(model.Service)).all()


class AbstractUserRepository(abc.ABC):
    @abc.abstractmethod
    def get(self, name):
        return NotImplementedError


class SqlAlchemyUserRepository(AbstractUserRepository):
    def __init__(self, session):
        self.session = session

    def add(self, user):
        self.session.add(user)

    def get(self, name):
        stmt = select(model.User).where(model.User.name == name)
        return self.session.execute(stmt).one()
