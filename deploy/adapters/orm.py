from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
)
from sqlalchemy.orm import registry

from ..domain import model


metadata_obj = MetaData()
mapper_registry = registry()

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


deployments = Table(
    "deployment",
    metadata_obj,
    Column("id", Integer, primary_key=True),
    Column("service_id", Integer, ForeignKey("service.id")),
    Column("origin", String(255)),
    Column("user", String(255)),
    Column("started", DateTime),
    Column("finished", DateTime),
    Column("context", JSON, default={}),
)


steps = Table(
    "step",
    metadata_obj,
    Column("id", Integer, primary_key=True),
    Column("name", String(255)),
    Column("started", DateTime),
    Column("finished", DateTime),
    Column("state", String(20), default="pending"),
    Column("message", String(255)),
    Column("deployment_id", Integer, ForeignKey("deployment.id")),
)


async def create_db_and_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(metadata_obj.create_all)


MAPPERS_STARTED = False


def start_mappers():
    global MAPPERS_STARTED
    if MAPPERS_STARTED:
        return
    mapper_registry.map_imperatively(model.User, users)
    mapper_registry.map_imperatively(model.Service, services)
    mapper_registry.map_imperatively(model.Deployment, deployments)
    mapper_registry.map_imperatively(model.Step, steps)
    MAPPERS_STARTED = True
