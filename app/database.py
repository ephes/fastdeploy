from sqlmodel import Session, SQLModel, create_engine

from .config import settings
from .filesystem import working_directory
from .models import Deployment, Service, Step, User


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
    def add_user(self, user) -> User:
        self.users.append(user)
        user.id = len(self.users)
        return user

    def get_user_by_name(self, username: str) -> User | None:
        for user in self.users:
            if user.name == username:
                return user
        return None

    # Service
    def get_services(self) -> list[Service]:
        return self.services

    def add_service(self, service: Service) -> Service:
        self.services.append(service)
        service.id = len(self.services)
        return service

    def get_service_by_name(self, name: str) -> Service | None:
        for service in self.services:
            if service.name == name:
                return service
        return None

    def get_service_by_id(self, service_id: int) -> Service | None:
        for service in self.services:
            if service.id == service_id:
                return service
        return None

    def delete_service_by_id(self, service_id: int) -> None:
        for service in self.services:
            if service.id == service_id:
                self.services.remove(service)

    # Step
    def add_step(self, step: Step) -> Step:
        self.steps.append(step)
        step.id = len(self.steps)
        return step

    def update_step(self, step: Step) -> Step:
        for index, step in enumerate(self.steps):
            if step.id == step.id:
                self.steps[index] = step
        return step

    def get_step_by_id(self, step_id: int) -> Step | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_steps_by_name(self, name: str) -> list[Step]:
        steps = []
        for step in self.steps:
            if step.name == name:
                steps.append(step)
        return steps

    # Deployment
    def get_deployments(self) -> list[Deployment]:
        return self.deployments

    def get_deployment_by_id(self, deployment_id: int) -> Deployment | None:
        for deployment in self.deployments:
            if deployment.id == deployment_id:
                return deployment
        return None

    def add_deployment(self, deployment: Deployment) -> Deployment:
        self.deployments.append(deployment)
        deployment.id = len(self.deployments)
        return deployment

    def get_deployments_by_service_id(self, service_id: int) -> list[Deployment]:
        deployments = []
        for deployment in self.deployments:
            if deployment.service_id == service_id:
                deployments.append(deployment)
        return deployments


class SQLiteRepository:
    def __init__(self):
        self.engine = engine

    def reset(self):
        SQLModel.metadata.drop_all(self.engine)
        create_db_and_tables()

    # User
    def add_user(self, user: User) -> User:
        with Session(self.engine) as session:
            session.add(user)
            session.commit()
            session.refresh(user)
        return user

    def get_user_by_name(self, username: str) -> User | None:
        with Session(self.engine) as session:
            user = session.query(User).filter(User.name == username).first()
        return user

    # Service
    def get_services(self) -> list[Service]:
        with Session(self.engine) as session:
            services = session.query(Service).all()
        return services

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

    # Step
    def add_step(self, step: Step) -> Step:
        with Session(self.engine) as session:
            session.add(step)
            session.commit()
            session.refresh(step)
        return step

    def update_step(self, step: Step) -> Step:
        return self.add_step(step)

    def get_step_by_id(self, step_id: int) -> Step | None:
        with Session(self.engine) as session:
            step = session.query(Step).filter(Step.id == step_id).first()
        return step

    def get_steps_by_name(self, name: str) -> list[Step]:
        with Session(self.engine) as session:
            steps = session.query(Step).filter(Step.name == name).all()
        return steps

    # Deployment
    def get_deployments(self) -> list[Deployment]:
        with Session(self.engine) as session:
            deployments = session.query(Deployment).all()
        return deployments

    def get_deployment_by_id(self, deployment_id: int) -> Deployment | None:
        with Session(self.engine) as session:
            deployment = session.query(Deployment).filter(Deployment.id == deployment_id).first()
        return deployment

    def add_deployment(self, deployment: Deployment) -> Deployment:
        with Session(self.engine) as session:
            session.add(deployment)
            session.commit()
            session.refresh(deployment)
        return deployment

    def get_deployments_by_service_id(self, service_id: int) -> list[Deployment]:
        with Session(self.engine) as session:
            deployments = session.query(Deployment).filter(Deployment.service_id == service_id).all()
        return deployments


if settings.repository == "sqlite":
    repository = SQLiteRepository()
elif settings.repository == "in_memory":
    repository = InMemoryRepository()
