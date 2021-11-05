from sqlmodel import Session, SQLModel, create_engine

from .config import settings
from .filesystem import working_directory
from .models import Service


with working_directory(settings.project_root):
    engine = create_engine(settings.database_url)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


class SQLiteRepository:
    def __init__(self):
        self.engine = engine

    def add_service(self, service):
        with Session(self.engine) as session:
            session.add(service)
            session.commit()
            session.refresh(service)
        return service

    def get_service_by_name(self, name):
        with Session(self.engine) as session:
            service = session.query(Service).filter(Service.name == name).first()
        return service


repository = SQLiteRepository()
