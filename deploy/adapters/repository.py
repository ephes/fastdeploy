import abc

from sqlalchemy import select

from ..domain import model


class AbstractServiceRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, service: model.Service) -> None:
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

    def add(self, service: model.Service):
        self.session.add(service)

    def get(self, name) -> model.Service:
        stmt = select(model.Service).where(model.Service.name == name)
        return self.session.execute(stmt).one()

    def list(self):
        return self.session.execute(select(model.Service)).all()


class InMemoryServiceRepository(AbstractServiceRepository):
    def __init__(self):
        self._services = []

    def add(self, service):
        if service.id is None:
            # insert
            self._services.append(service)
            service.id = len(self._services)
        else:
            # update
            self._services[service.id - 1] = service

    def get(self, name):
        return next((s,) for s in self._services if s.name == name)

    def list(self):
        return [(s,) for s in self._services]


class AbstractUserRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, user: model.User) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get(self, name) -> model.User:
        return NotImplementedError


class SqlAlchemyUserRepository(AbstractUserRepository):
    def __init__(self, session):
        self.session = session

    def add(self, user):
        self.session.add(user)

    def get(self, name):
        stmt = select(model.User).where(model.User.name == name)
        return self.session.execute(stmt).one()


class InMemoryUserRepository(AbstractUserRepository):
    def __init__(self):
        self._users = []

    def add(self, user):
        self._users.append(user)
        user.id = len(self._users)

    def get(self, name):
        return next((u,) for u in self._users if u.name == name)
