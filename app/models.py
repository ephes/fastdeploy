from typing import Optional

from sqlalchemy import String
from sqlalchemy.sql.schema import Column
from sqlmodel import Field, SQLModel, create_engine

from .config import settings
from .filesystem import working_directory


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column("name", String, unique=True))
    password: str
    is_active: bool


class Deployment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)


def create_database():
    with working_directory(settings.project_root):
        settings.db_engine = create_engine(settings.database_url, echo=False)
        SQLModel.metadata.create_all(settings.db_engine)
