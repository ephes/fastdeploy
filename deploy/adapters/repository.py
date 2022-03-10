import abc

from sqlalchemy import delete, select, text
from sqlalchemy.orm.exc import NoResultFound

from ..domain import model


class AbstractServiceRepository(abc.ABC):
    def __init__(self):
        self.seen: set[model.Service] = set()

    async def add(self, service: model.Service):
        await self._add(service)
        self.seen.add(service)

    async def delete(self, service):
        await self._delete(service)
        self.seen.add(service)

    @abc.abstractmethod
    async def _add(self, service: model.Service) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def _delete(self, service: model.Service) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get(self, service_id: int) -> tuple[model.Service]:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_by_name(self, name: str) -> tuple[model.Service]:
        raise NotImplementedError

    @abc.abstractmethod
    async def list(self) -> list[tuple[model.Service]]:
        raise NotImplementedError


class SqlAlchemyServiceRepository(AbstractServiceRepository):
    def __init__(self, session):
        self.session = session
        super().__init__()

    async def _add(self, service: model.Service):
        self.session.add(service)

    async def get(self, service_id) -> model.Service:
        stmt = select(model.Service).where(model.Service.id == service_id)
        result = await self.session.execute(stmt)
        return result.one()

    async def get_by_name(self, name) -> model.Service:
        stmt = select(model.Service).where(model.Service.name == name)
        result = await self.session.execute(stmt)
        return result.one()

    async def list(self):
        result = await self.session.execute(select(model.Service))
        return result.all()

    async def _delete(self, service):
        stmt = delete(model.Service).where(model.Service.id == service.id)
        await self.session.execute(stmt)


class InMemoryServiceRepository(AbstractServiceRepository):
    def __init__(self):
        self._services = []
        super().__init__()

    async def _add(self, service):
        if service.id is None:
            # insert
            self._services.append(service)
            service.id = len(self._services)
        else:
            # update
            self._services[service.id - 1] = service

    async def get(self, service_id):
        return next((s,) for s in self._services if s.id == service_id)

    async def get_by_name(self, name):
        return next((s,) for s in self._services if s.name == name)

    async def list(self):
        return [(s,) for s in self._services]

    async def _delete(self, service):
        self._services = [s for s in self._services if s.id != service.id]


class AbstractUserRepository(abc.ABC):
    @abc.abstractmethod
    async def add(self, user: model.User) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get(self, name) -> tuple[model.User]:
        return NotImplementedError

    @abc.abstractmethod
    async def list(self) -> list[tuple[model.User]]:
        return NotImplementedError


class SqlAlchemyUserRepository(AbstractUserRepository):
    def __init__(self, session):
        self.session = session

    async def add(self, user):
        self.session.add(user)

    async def get(self, name):
        stmt = select(model.User).where(model.User.name == name)
        result = await self.session.execute(stmt)
        return result.one()

    async def list(self):
        result = await self.session.execute(select(model.User))
        return result.all()


class InMemoryUserRepository(AbstractUserRepository):
    def __init__(self):
        self._users = []

    async def add(self, user):
        self._users.append(user)
        user.id = len(self._users)

    async def get(self, name):
        return next((u,) for u in self._users if u.name == name)

    async def list(self):
        return self._users


class AbstractDeploymentRepository(abc.ABC):
    def __init__(self):
        self.seen: set[model.Deployment] = set()

    @abc.abstractmethod
    async def add(self, deployment: model.Deployment) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get(self, deployment_id: int) -> tuple[model.Deployment]:
        return NotImplementedError

    @abc.abstractmethod
    async def list(self) -> list[tuple[model.Deployment]]:
        return NotImplementedError

    @abc.abstractmethod
    async def get_last_successful_deployment_id(self, service_id: int) -> int | None:
        return NotImplementedError

    @abc.abstractmethod
    async def get_most_recent_running_deployment(self, service_id: int) -> tuple[model.Deployment]:
        return NotImplementedError


class SqlAlchemyDeploymentRepository(AbstractDeploymentRepository):
    def __init__(self, session):
        self.session = session
        super().__init__()

    async def add(self, deployment):
        self.session.add(deployment)
        self.seen.add(deployment)

    async def get(self, deployment_id):
        stmt = select(model.Deployment).where(model.Deployment.id == deployment_id)
        result = await self.session.execute(stmt)
        return result.one()

    async def list(self):
        stmt = select(model.Deployment)
        result = await self.session.execute(stmt)
        return result.all()

    async def get_last_successful_deployment_id(self, service_id):
        """
        Returns the id of the last successful deployment for a service.
        """
        statement = text(
            """
            select step.deployment_id
            from deployment, step
            where step.deployment_id=deployment.id
            and step.state = 'success'
            and deployment.service_id = :service_id
            and deployment.finished is not null
            and step.deployment_id not in (
                select distinct(step.deployment_id)
                from step, deployment
                where step.deployment_id=deployment.id
                and deployment.service_id = :service_id
                and step.state != 'success'
                group by step.deployment_id
                having count(step.id) > 1
            )
            group by step.deployment_id, deployment.started
            having count(step.id) > 0
            order by deployment.started desc
        """
        )
        result = await self.session.execute(statement, {"service_id": service_id})
        try:
            [last_successful] = result.one()
            return last_successful
        except NoResultFound:
            return None

    async def get_most_recent_running_deployment(self, service_id):
        stmt = (
            select(model.Deployment)
            .where(model.Deployment.service_id == service_id)
            .where(model.Deployment.finished.is_(None))  # type: ignore
            .where(model.Deployment.started.is_not(None))  # type: ignore
            .order_by(model.Deployment.started.desc())  # type: ignore
        )
        result = await self.session.execute(stmt)
        return result.one()


class InMemoryDeploymentRepository(AbstractDeploymentRepository):
    def __init__(self):
        self._deployments = []
        super().__init__()

    async def add(self, deployment):
        self._deployments.append(deployment)
        deployment.id = len(self._deployments)
        self.seen.add(deployment)

    async def get(self, deployment_id):
        return next((d,) for d in self._deployments if d.id == deployment_id)

    async def get_last_successful_deployment_id(self, service_id):
        # failed_deployments = set()
        # for step in self._steps:
        #     if step.state != "success":
        #         failed_deployments.add(step.deployment_id)
        last_successful = None
        # FIXME dunno how to implement this
        # for deployment in self.deployments:
        #     is_for_service = deployment.service_id == service_id
        #     is_successful = deployment.id not in failed_deployments and deployment.finished is not None
        #     if is_successful and is_for_service:
        #         if last_successful is None or deployment.finished > last_successful.finished:
        #             last_successful = deployment.id
        return last_successful

    async def list(self):
        return self._deployments

    async def get_most_recent_running_deployment(self, service_id):
        deployments = []
        for deployment in self._deployments:
            if deployment.service_id == service_id and deployment.finished is None and deployment.started is not None:
                deployments.append(deployment)
        deployments.sort(key=lambda d: d.started, reverse=True)
        return next((d,) for d in deployments)


class AbstractStepRepository(abc.ABC):
    def __init__(self):
        self.seen: set[model.Step] = set()

    @abc.abstractmethod
    async def add(self, step: model.Step) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get(self, step_id: int) -> tuple[model.Step]:
        return NotImplementedError

    @abc.abstractmethod
    async def delete(self, step: model.Step) -> None:
        return NotImplementedError

    @abc.abstractmethod
    async def get_steps_from_deployment(self, deployment_id: int) -> list[tuple[model.Step]]:
        return NotImplementedError


class SqlAlchemyStepRepository(AbstractStepRepository):
    def __init__(self, session):
        self.session = session
        super().__init__()

    async def add(self, step):
        self.session.add(step)

    async def get(self, step_id):
        stmt = select(model.Step).where(model.Step.id == step_id)
        result = await self.session.execute(stmt)
        return result.one()

    async def delete(self, step):
        self.session.delete(step)

    async def get_steps_from_deployment(self, deployment_id):
        stmt = select(model.Step).where(model.Step.deployment_id == deployment_id)
        result = await self.session.execute(stmt)
        return result.all()


class InMemoryStepRepository(AbstractStepRepository):
    def __init__(self):
        self._steps = []
        super().__init__()

    async def add(self, step):
        self._steps.append(step)
        step.id = len(self._steps)

    async def get(self, step_id):
        return next((s,) for s in self._steps if s.id == step_id)

    async def delete(self, step):
        self._steps.remove(step)

    async def get_steps_from_deployment(self, deployment_id):
        return ((s,) for s in self._steps if s.deployment_id == deployment_id)
