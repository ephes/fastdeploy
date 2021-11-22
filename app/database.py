from sqlmodel import Session, SQLModel, create_engine

from .config import settings
from .filesystem import working_directory
from .models import Deployment, DeploymentOut, Service, ServiceOut, Step, StepOut, User
from .websocket import connection_manager


with working_directory(settings.project_root):
    engine = create_engine(settings.database_url)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


class InMemoryRepository:
    def __init__(self):
        self.reset()

    def reset(self):
        self.deployments = []
        self.services = []
        self.steps = []
        self.users = []

    # User
    async def add_user(self, user) -> User:
        self.users.append(user)
        user.id = len(self.users)
        return user

    async def get_user_by_name(self, username: str) -> User | None:
        for user in self.users:
            if user.name == username:
                return user
        return None

    # Service
    async def get_services(self) -> list[Service]:
        return self.services

    async def add_service(self, service: Service) -> Service:
        self.services.append(service)
        if service.id is None:
            service.id = len(self.services)
        await connection_manager.broadcast(ServiceOut.parse_obj(service))
        return service

    async def get_service_by_name(self, name: str) -> Service | None:
        for service in self.services:
            if service.name == name:
                return service
        return None

    async def get_service_by_id(self, service_id: int) -> Service | None:
        for service in self.services:
            if service.id == service_id:
                return service
        return None

    async def delete_service_by_id(self, service_id: int) -> None:
        await self.delete_deployments_by_service_id(service_id)
        for service in self.services:
            if service.id == service_id:
                self.services.remove(service)
                service_out = ServiceOut.parse_obj(service)
                service_out.deleted = True
                await connection_manager.broadcast(service_out)
                break

    # Step
    async def get_steps_by_deployment_id(self, deployment_id: int) -> list[Step]:
        steps = []
        for step in self.steps:
            if step.deployment_id == deployment_id:
                steps.append(step)
        return steps

    async def add_step(self, step: Step) -> Step:
        self.steps.append(step)
        step.id = len(self.steps)
        await connection_manager.broadcast(StepOut.parse_obj(step))
        return step

    async def update_step(self, step: Step) -> Step:
        for index, step in enumerate(self.steps):
            if step.id == step.id:
                self.steps[index] = step
        await connection_manager.broadcast(StepOut.parse_obj(step))
        return step

    async def get_step_by_id(self, step_id: int) -> Step | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    async def get_steps_by_name(self, name: str) -> list[Step]:
        steps = []
        for step in self.steps:
            if step.name == name:
                steps.append(step)
        return steps

    async def delete_steps_by_deployment_id(self, deployment_id: int) -> None:
        for step in self.steps:
            if step.deployment_id == deployment_id:
                self.steps.remove(step)
                step_out = StepOut.parse_obj(step)
                step_out.deleted = True
                await connection_manager.broadcast(step_out)

    # Deployment
    async def get_deployments(self) -> list[Deployment]:
        return self.deployments

    async def get_deployment_by_id(self, deployment_id: int) -> Deployment | None:
        for deployment in self.deployments:
            if deployment.id == deployment_id:
                return deployment
        return None

    async def add_deployment(self, deployment: Deployment) -> Deployment:
        self.deployments.append(deployment)
        deployment.id = len(self.deployments)
        await connection_manager.broadcast(DeploymentOut.parse_obj(deployment))
        return deployment

    async def get_deployments_by_service_id(self, service_id: int) -> list[Deployment]:
        deployments = []
        for deployment in self.deployments:
            if deployment.service_id == service_id:
                deployments.append(deployment)
        return deployments

    async def delete_deployments_by_service_id(self, service_id: int) -> None:
        for deployment in self.deployments:
            if deployment.service_id == service_id:
                await self.delete_steps_by_deployment_id(deployment.id)
                self.deployments.remove(deployment)
                deployment_out = DeploymentOut.parse_obj(deployment)
                deployment_out.deleted = True
                await connection_manager.broadcast(deployment_out)


class SQLiteRepository:
    def __init__(self):
        self.engine = engine

    def reset(self):
        SQLModel.metadata.drop_all(self.engine)
        create_db_and_tables()

    # User
    async def add_user(self, user: User) -> User:
        with Session(self.engine) as session:
            session.add(user)
            session.commit()
            session.refresh(user)
        return user

    async def get_user_by_name(self, username: str) -> User | None:
        with Session(self.engine) as session:
            user = session.query(User).filter(User.name == username).first()
        return user

    # Service
    async def get_services(self) -> list[Service]:
        with Session(self.engine) as session:
            services = session.query(Service).all()
        return services

    async def add_service(self, service: Service) -> Service:
        with Session(self.engine) as session:
            session.add(service)
            session.commit()
            session.refresh(service)
        await connection_manager.broadcast(ServiceOut.parse_obj(service))
        return service

    async def get_service_by_name(self, name: str) -> Service | None:
        with Session(self.engine) as session:
            service = session.query(Service).filter(Service.name == name).first()
        return service

    async def get_service_by_id(self, service_id: int) -> Service | None:
        with Session(self.engine) as session:
            service = session.query(Service).filter(Service.id == service_id).first()
        return service

    async def delete_service_by_id(self, service_id: int) -> None:
        await self.delete_deployments_by_service_id(service_id)
        with Session(self.engine) as session:
            service = session.query(Service).filter(Service.id == service_id).first()
            session.delete(service)
            service_out = ServiceOut.parse_obj(service)
            service_out.deleted = True
            await connection_manager.broadcast(service_out)
            session.commit()

    # Step
    async def get_steps_by_deployment_id(self, deployment_id: int) -> list[Step]:
        with Session(self.engine) as session:
            steps = session.query(Step).filter(Step.deployment_id == deployment_id).all()
        return steps

    async def add_step(self, step: Step) -> Step:
        with Session(self.engine) as session:
            session.add(step)
            session.commit()
            session.refresh(step)
        await connection_manager.broadcast(StepOut.parse_obj(step))
        return step

    async def update_step(self, step: Step) -> Step:
        step = await self.add_step(step)
        await connection_manager.broadcast(StepOut.parse_obj(step))
        return step

    async def get_step_by_id(self, step_id: int) -> Step | None:
        with Session(self.engine) as session:
            step = session.query(Step).filter(Step.id == step_id).first()
        return step

    async def get_steps_by_name(self, name: str) -> list[Step]:
        with Session(self.engine) as session:
            steps = session.query(Step).filter(Step.name == name).all()
        return steps

    async def delete_steps_by_deployment_id(self, deployment_id: int) -> None:
        with Session(self.engine) as session:
            steps = session.query(Step).filter(Step.deployment_id == deployment_id).all()
            for step in steps:
                session.delete(step)
                step_out = StepOut.parse_obj(step)
                step_out.deleted = True
                await connection_manager.broadcast(step_out)
            session.commit()

    # Deployment
    async def get_deployments(self) -> list[Deployment]:
        with Session(self.engine) as session:
            deployments = session.query(Deployment).all()
        return deployments

    async def get_deployment_by_id(self, deployment_id: int) -> Deployment | None:
        with Session(self.engine) as session:
            deployment = session.query(Deployment).filter(Deployment.id == deployment_id).first()
        return deployment

    async def add_deployment(self, deployment: Deployment) -> Deployment:
        with Session(self.engine) as session:
            session.add(deployment)
            session.commit()
            session.refresh(deployment)
        await connection_manager.broadcast(DeploymentOut.parse_obj(deployment))
        return deployment

    async def get_deployments_by_service_id(self, service_id: int) -> list[Deployment]:
        with Session(self.engine) as session:
            deployments = session.query(Deployment).filter(Deployment.service_id == service_id).all()
        return deployments

    async def delete_deployments_by_service_id(self, service_id: int) -> None:
        with Session(self.engine) as session:
            deployments = session.query(Deployment).filter(Deployment.service_id == service_id).all()
            for deployment in deployments:
                await self.delete_steps_by_deployment_id(deployment.id)
                session.delete(deployment)
                deployment_out = DeploymentOut.parse_obj(deployment)
                deployment_out.deleted = True
                await connection_manager.broadcast(deployment_out)
            session.commit()


repository: SQLiteRepository | InMemoryRepository
if settings.repository == "sqlite":
    repository = SQLiteRepository()
elif settings.repository == "in_memory":
    repository = InMemoryRepository()
