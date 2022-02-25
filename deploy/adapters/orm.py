from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.orm import mapper

from ..config import settings
from ..domain import model


# engine = create_engine(settings.database_url, echo=True, future=True)
engine = create_engine(settings.database_url, future=True)
metadata_obj = MetaData()
# session = Session(engine)

users = Table(
    "user",
    metadata_obj,
    Column("id", Integer, primary_key=True),
    Column("name", String(255), unique=True),
    Column("password", String(255)),
)


services = Table(
    "service",
    metadata_obj,
    Column("id", Integer, primary_key=True),
    Column("name", String(255), unique=True),
    Column("data", JSON, default={}),
)


def create_db_and_tables():
    metadata_obj.create_all(engine)


def drop_db_and_tables():
    metadata_obj.drop_all(engine)


def start_mappers():
    print("start mappers")
    mapper(model.User, users)
    mapper(model.Service, services)


def get_engine():
    start_mappers()
    return engine
