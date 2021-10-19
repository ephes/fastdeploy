from sqlmodel import SQLModel, create_engine

from .config import settings
from .filesystem import working_directory


with working_directory(settings.project_root):
    engine = create_engine(settings.database_url)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
