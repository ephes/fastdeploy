import abc

from sqlalchemy import delete, select

from ..domain import model


class AbstractServiceRepository(abc.ABC):
    def __init__(self):
        self.seen = set()  # type: set[model.Service]

    def add(self, service: model.Service):
        self._add(service)
        self.seen.add(service)

    def delete(self, service):
        self._delete(service)
        self.seen.add(service)

    @abc.abstractmethod
    def _add(self, service: model.Service) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def _delete(self, service: model.Service) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get(self, service_id: int) -> tuple[model.Service]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_by_name(self, name: str) -> tuple[model.Service]:
        raise NotImplementedError

    @abc.abstractmethod
    def list(self) -> list[tuple[model.Service]]:
        raise NotImplementedError


class SqlAlchemyServiceRepository(AbstractServiceRepository):
    def __init__(self, session):
        self.session = session
        super().__init__()

    def _add(self, service: model.Service):
        self.session.add(service)

    def get(self, service_id) -> model.Service:
        stmt = select(model.Service).where(model.Service.id == service_id)
        return self.session.execute(stmt).one()

    def get_by_name(self, name) -> model.Service:
        stmt = select(model.Service).where(model.Service.name == name)
        return self.session.execute(stmt).one()

    def list(self):
        return self.session.execute(select(model.Service)).all()

    def _delete(self, service):
        stmt = delete(model.Service).where(model.Service.id == service.id)
        self.session.execute(stmt)


class InMemoryServiceRepository(AbstractServiceRepository):
    def __init__(self):
        self._services = []
        super().__init__()

    def _add(self, service):
        if service.id is None:
            # insert
            self._services.append(service)
            service.id = len(self._services)
        else:
            # update
            self._services[service.id - 1] = service

    def get(self, service_id):
        return next((s,) for s in self._services if s.id == service_id)

    def get_by_name(self, name):
        return next((s,) for s in self._services if s.name == name)

    def list(self):
        return [(s,) for s in self._services]

    def _delete(self, service):
        self._services = [s for s in self._services if s.id != service.id]


class AbstractUserRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, user: model.User) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get(self, name) -> tuple[model.User]:
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


class AbstractDeploymentRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, deployment: model.Deployment) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def get(self, deployment_id: int) -> tuple[model.Deployment]:
        return NotImplementedError


class SqlAlchemyDeploymentRepository(AbstractDeploymentRepository):
    def __init__(self, session):
        self.session = session

    def add(self, deployment):
        self.session.add(deployment)

    def get(self, deployment_id):
        stmt = select(model.Deployment).where(model.Deployment.id == deployment_id)
        return self.session.execute(stmt).one()


class InMemoryDeploymentRepository(AbstractDeploymentRepository):
    def __init__(self):
        self._deployments = []

    def add(self, deployment):
        self._deployments.append(deployment)
        deployment.id = len(self._deployments)

    def get(self, deployment_id):
        return next((d,) for d in self._deployments if d.id == deployment_id)
