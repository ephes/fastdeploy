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

    def add_service(self, service: Service) -> Service:
        with Session(self.engine) as session:
            session.add(service)
            session.commit()
            session.refresh(service)
        return service

    def get_service_by_name(self, name: str) -> Service | None:
        with Session(self.engine) as session:
            service = session.query(Service).filter(Service.name == name).first()
        return service

    def get_service_by_id(self, service_id: int) -> Service | None:
        with Session(self.engine) as session:
            service = session.query(Service).filter(Service.id == service_id).first()
        return service

    def delete_service_by_id(self, service_id: int) -> None:
        with Session(self.engine) as session:
            service = session.query(Service).filter(Service.id == service_id).first()
            session.delete(service)
            session.commit()


repository = SQLiteRepository()
