from typing import Optional

from sqlalchemy import String
from sqlalchemy.sql.schema import Column
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column("name", String, unique=True))
    password: str
    deploy_only: bool


class Deployment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
