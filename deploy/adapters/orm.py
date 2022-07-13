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
from sqlalchemy.orm import registry  # type: ignore

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
    Column("service_id", Integer, ForeignKey("service.id", ondelete="CASCADE")),
    Column("origin", String(255)),
    Column("user", String(255)),
    Column("started", DateTime(timezone=True)),
    Column("finished", DateTime(timezone=True)),
    Column("context", JSON, default={}),
)


steps = Table(
    "step",
    metadata_obj,
    Column("id", Integer, primary_key=True),
    Column("name", String(255)),
    Column("started", DateTime(timezone=True)),
    Column("finished", DateTime(timezone=True)),
    Column("state", String(20), default="pending"),
    Column("message", String(4096)),
    Column("deployment_id", Integer, ForeignKey("deployment.id", ondelete="CASCADE")),
)


deployed_services = Table(
    "deployed_service",
    metadata_obj,
    Column("id", Integer, primary_key=True),
    Column("deployment_id", Integer, ForeignKey("deployment.id", ondelete="CASCADE")),
    Column("config", JSON, default={}),
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
    mapper_registry.map_imperatively(model.Step, steps)
    mapper_registry.map_imperatively(model.Deployment, deployments)
    mapper_registry.map_imperatively(model.Service, services)
    mapper_registry.map_imperatively(model.DeployedService, deployed_services)
    MAPPERS_STARTED = True
    # Maybe define relationships?
    # steps_mapper = mapper_registry.map_imperatively(model.Step, steps)
    # deployments_mapper = mapper_registry.map_imperatively(
    #     model.Deployment,
    #     deployments,
    #     properties={"_steps": relationship(steps_mapper, collection_class=list, cascade="all, delete-orphan")},
    # )
    # mapper_registry.map_imperatively(
    #     model.Service,
    #     services,
    #     properties={"_deployments": relationship(deployments_mapper, collection_class=list, cascade="all, delete")},
    # )
