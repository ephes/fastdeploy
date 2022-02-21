import abc

from ..domain import model


class AbstractServiceRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, service: model.Service):
        raise NotImplementedError

    @abc.abstractmethod
    def get(self, name) -> model.Service:
        raise NotImplementedError


class SqlAlchemyServiceRepository(AbstractServiceRepository):
    def __init__(self, session):
        self.session = session

    def add(self, batch):
        self.session.add(batch)

    def get(self, name):
        return self.session.query(model.Service).filter_by(name=name).one()

    def list(self):
        return self.session.query(model.Service).all()
