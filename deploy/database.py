from sqlmodel import Session, SQLModel, create_engine

from .config import settings
from .filesystem import get_directories, get_service_config, working_directory
from .models import (
    Deployment,
    DeploymentOut,
    Service,
    ServiceOut,
    Step,
    StepBase,
    StepOut,
    User,
)
from .pydantic_models import PServiceOut


with working_directory(settings.project_root):
    engine = create_engine(settings.database_url)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


class BaseRepository:
    def __init__(self):
        self.event_handlers = []

    def register_event_handler(self, handler):
        self.event_handlers.append(handler)

    async def dispatch_event(self, event):
        for handler in self.event_handlers:
            await handler.handle_event(event)

    async def get_service_names(self) -> set[str]:
        return set(get_directories(settings.services_root))

    async def get_service_data(self, service_name: str) -> dict:
        return get_service_config(service_name)

    async def get_source_services(self) -> list[Service]:
        """Return all source services from filesystem."""
        names = await self.get_service_names()
        services = []
        for name in names:
            services.append(Service(name=name, data=await self.get_service_data(name)))
        return services

    async def get_services(self) -> list[Service]:
        raise NotImplementedError

    async def get_all_services(self) -> tuple[list[Service], list[Service]]:
        """Return all source services from filesystem and all services
        already in database."""
        fs_services = await self.get_source_services()
        db_services = await self.get_services()
        return fs_services, db_services

    @staticmethod
    def sync_services(
        source_services: list[Service], target_services: list[Service]
    ) -> tuple[list[Service], list[Service]]:
        # compare source and target services and add/update accordingly
        updated_services = []
        target_name_lookup = {service.name: service for service in target_services}
        for service in source_services:
            if service.name in target_name_lookup:
                # service exists in target, check if it needs to be updated
                target_service = target_name_lookup[service.name]
                if target_service.data != service.data:
                    # it's sufficient to check if the data is different, because
                    # if name differs, it's a new/deleted service
                    target_service.data = service.data
                    # use target_service to keep the id
                    updated_services.append(target_service)
            else:
                # service does not exist in target, add it
                updated_services.append(service)

        # check if any services in target are not in source
        deleted_services = []
        source_name_lookup = {service.name: service for service in source_services}
        for service in target_services:
            if service.name not in source_name_lookup:
                deleted_services.append(service)
        return updated_services, deleted_services

    async def delete_service_by_id(self, service_id: int) -> None:
        raise NotImplementedError

    async def add_service(self, service: Service) -> Service:
        raise NotImplementedError

    async def persist_synced_services(self, updated_services: list[Service], deleted_services: list[Service]) -> None:
        for to_delete in deleted_services:
            if to_delete.id is not None:
                await self.delete_service_by_id(to_delete.id)
        for to_update in updated_services:
            await self.add_service(to_update)


class InMemoryRepository(BaseRepository):
    def __init__(self):
        super().__init__()
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
        if service.id is None:
            # insert
            self.services.append(service)
            service.id = len(self.services)
        else:
            # update
            self.services[service.id - 1] = service
        await self.dispatch_event(ServiceOut.parse_obj(service))
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
                await self.dispatch_event(service_out)
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
        await self.dispatch_event(StepOut.parse_obj(step))
        return step

    async def update_step(self, step: Step) -> Step:
        for index, step in enumerate(self.steps):
            if step.id == step.id:
                self.steps[index] = step
        await self.dispatch_event(StepOut.parse_obj(step))
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

    async def delete_step(self, step: Step) -> None:
        self.steps.remove(step)
        step_out = StepOut.parse_obj(step)
        step_out.deleted = True
        await self.dispatch_event(step_out)

    async def delete_steps_by_deployment_id(self, deployment_id: int) -> None:
        for step in self.steps:
            if step.deployment_id == deployment_id:
                self.steps.remove(step)
                step_out = StepOut.parse_obj(step)
                step_out.deleted = True
                await self.dispatch_event(step_out)

    # Deployment
    async def get_deployments(self) -> list[Deployment]:
        return self.deployments

    async def get_deployment_by_id(self, deployment_id: int) -> Deployment | None:
        for deployment in self.deployments:
            if deployment.id == deployment_id:
                return deployment
        return None

    async def add_deployment(self, deployment: Deployment, steps: list[StepBase]) -> tuple[Deployment, list[Step]]:
        self.deployments.append(deployment)
        deployment.id = len(self.deployments)
        await self.dispatch_event(DeploymentOut.parse_obj(deployment))
        added_steps = []
        for base_step in steps:
            step = Step(**base_step.dict(), deployment_id=deployment.id)
            added_steps.append(await self.add_step(step))
        return deployment, added_steps

    async def update_deployment(self, deployment: Deployment) -> Deployment:
        for index, deployment in enumerate(self.deployments):
            if deployment.id == deployment.id:
                self.deployments[index] = deployment
        await self.dispatch_event(DeploymentOut.parse_obj(deployment))
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
                await self.dispatch_event(deployment_out)

    async def get_last_successful_deployment_id(self, service_id: int) -> int | None:
        failed_deployments = set()
        for step in self.steps:
            if step.state != "success":
                failed_deployments.add(step.deployment_id)
        last_successful = None
        for deployment in self.deployments:
            is_for_service = deployment.service_id == service_id
            is_successful = deployment.id not in failed_deployments and deployment.finished is not None
            if is_successful and is_for_service:
                if last_successful is None or deployment.finished > last_successful.finished:
                    last_successful = deployment.id
        return last_successful


class SQLiteRepository(BaseRepository):
    def __init__(self):
        super().__init__()
        self.engine = engine

    def reset(self):
        # SQLModel.metadata.drop_all(self.engine)
        # drop_db_and_tables()
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
        await self.dispatch_event(PServiceOut(**service.dict()))
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
            await self.dispatch_event(service_out)
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
        await self.dispatch_event(StepOut.parse_obj(step))
        return step

    async def update_step(self, step: Step) -> Step:
        step = await self.add_step(step)
        await self.dispatch_event(StepOut.parse_obj(step))
        return step

    async def get_step_by_id(self, step_id: int) -> Step | None:
        with Session(self.engine) as session:
            step = session.query(Step).filter(Step.id == step_id).first()
        return step

    async def get_steps_by_name(self, name: str) -> list[Step]:
        with Session(self.engine) as session:
            steps = session.query(Step).filter(Step.name == name).all()
        return steps

    async def delete_step(self, step: Step) -> None:
        with Session(self.engine) as session:
            session.delete(step)
            step_out = StepOut.parse_obj(step)
            step_out.deleted = True
            await self.dispatch_event(step_out)
            session.commit()

    async def delete_steps_by_deployment_id(self, deployment_id: int) -> None:
        with Session(self.engine) as session:
            steps = session.query(Step).filter(Step.deployment_id == deployment_id).all()
            for step in steps:
                session.delete(step)
                step_out = StepOut.parse_obj(step)
                step_out.deleted = True
                await self.dispatch_event(step_out)
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

    async def add_deployment(self, deployment: Deployment, steps: list[StepBase]) -> tuple[Deployment, list[Step]]:
        with Session(self.engine) as session:
            session.add(deployment)
            session.commit()
            session.refresh(deployment)
        await self.dispatch_event(DeploymentOut.parse_obj(deployment))
        added_steps = []
        for base_step in steps:
            if deployment.id is not None:
                step = Step(**base_step.dict(), deployment_id=deployment.id)
                added_steps.append(await self.add_step(step))
        return deployment, added_steps

    async def update_deployment(self, deployment: Deployment) -> Deployment:
        with Session(self.engine) as session:
            session.add(deployment)
            session.commit()
            session.refresh(deployment)
        await self.dispatch_event(DeploymentOut.parse_obj(deployment))
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
                await self.dispatch_event(deployment_out)
            session.commit()

    async def get_last_successful_deployment_id(self, service_id: int) -> int | None:
        """
        Returns the id of the last successful deployment for a service.
        """
        statement = """
            select step.deployment_id
            from deployment, step
            where step.deployment_id=deployment.id
            and step.state == "success"
            and deployment.service_id = :service_id
            and deployment.finished is not null
            and step.deployment_id not in (
                select distinct(step.deployment_id)
                from step, deployment
                    on step.deployment_id=deployment.id
                where deployment.service_id = :service_id
                and step.state != 'success'
                group by step.deployment_id
                having count(step.id) > 1
            )
            group by step.deployment_id
            having count(step.id) > 0
            order by deployment.started desc
        """
        last_successful = None
        with Session(self.engine) as session:
            try:
                last_successful = session.exec(statement, params={"service_id": service_id}).all()[0][  # type: ignore
                    0
                ]
            except IndexError:
                last_successful = None
        return last_successful


repository: SQLiteRepository | InMemoryRepository
if settings.repository == "sqlite":
    repository = SQLiteRepository()
elif settings.repository == "in_memory":
    repository = InMemoryRepository()


# class SQLAlchemyServiceRepository:
#     def __init__(self, session):
#         self.session = session


# services_repo = SQLAlchemyServiceRepository(sessionmaker(bind=get_engine()))