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

    async def get(self, service_id) -> tuple[model.Service]:
        stmt = select(model.Service).where(model.Service.id == service_id)
        result = await self.session.execute(stmt)
        return result.one()

    async def get_by_name(self, name) -> tuple[model.Service]:
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
    def __init__(self):
        self.seen: set[model.User] = set()

    @abc.abstractmethod
    async def _add(self, user: model.User) -> None:
        raise NotImplementedError

    async def add(self, user: model.User) -> None:
        await self._add(user)
        self.seen.add(user)

    @abc.abstractmethod
    async def get(self, name) -> tuple[model.User]:
        raise NotImplementedError

    @abc.abstractmethod
    async def list(self) -> list[tuple[model.User]]:
        raise NotImplementedError


class SqlAlchemyUserRepository(AbstractUserRepository):
    def __init__(self, session):
        self.session = session
        super().__init__()

    async def _add(self, user):
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
        super().__init__()

    async def _add(self, user):
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
    async def _add(self, deployment: model.Deployment) -> None:
        raise NotImplementedError

    async def add(self, deployment: model.Deployment) -> None:
        await self._add(deployment)
        self.seen.add(deployment)

    @abc.abstractmethod
    async def get(self, deployment_id: int) -> tuple[model.Deployment]:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_by_service(self, service_id: int) -> list[tuple[model.Deployment]]:
        raise NotImplementedError

    @abc.abstractmethod
    async def list(self) -> list[tuple[model.Deployment]]:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_last_successful_deployment_id(self, service_id: int) -> int | None:
        raise NotImplementedError


class SqlAlchemyDeploymentRepository(AbstractDeploymentRepository):
    def __init__(self, session):
        self.session = session
        super().__init__()

    async def _add(self, deployment):
        self.session.add(deployment)

    async def get(self, deployment_id):
        stmt = select(model.Deployment).where(model.Deployment.id == deployment_id)
        result = await self.session.execute(stmt)
        return result.one()

    async def get_by_service(self, service_id):
        stmt = select(model.Deployment).where(model.Deployment.service_id == service_id)
        result = await self.session.execute(stmt)
        return result.all()

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
            # [last_successful] = result.first()
            last_successful = result.first()
            if last_successful is not None:
                [last_successful] = last_successful
            return last_successful
        except NoResultFound:
            return None


class InMemoryDeploymentRepository(AbstractDeploymentRepository):
    def __init__(self):
        self._deployments = []
        super().__init__()

    async def _add(self, deployment):
        self._deployments.append(deployment)
        deployment.id = len(self._deployments)

    async def get(self, deployment_id):
        return next((d,) for d in self._deployments if d.id == deployment_id)

    async def get_by_service(self, service_id):
        return [(d,) for d in self._deployments if d.service_id == service_id]

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


class AbstractStepRepository(abc.ABC):
    def __init__(self):
        self.seen: set[model.Step] = set()

    @abc.abstractmethod
    async def _add(self, step: model.Step) -> None:
        raise NotImplementedError

    async def add(self, step: model.Step) -> None:
        await self._add(step)
        self.seen.add(step)

    @abc.abstractmethod
    async def get(self, step_id: int) -> tuple[model.Step]:
        raise NotImplementedError

    @abc.abstractmethod
    async def _delete(self, step: model.Step) -> None:
        raise NotImplementedError

    async def delete(self, step: model.Step) -> None:
        await self._delete(step)
        self.seen.add(step)

    @abc.abstractmethod
    async def get_steps_from_deployment(self, deployment_id: int) -> list[tuple[model.Step]]:
        raise NotImplementedError

    @abc.abstractmethod
    async def list(self) -> list[tuple[model.Step]]:
        # list has to be after get_steps_from_deployment otherwise
        # type annotation wont work, duh :/ - maybe a bug in pylance..
        raise NotImplementedError


class SqlAlchemyStepRepository(AbstractStepRepository):
    def __init__(self, session):
        self.session = session
        super().__init__()

    async def _add(self, step):
        self.session.add(step)

    async def get(self, step_id):
        stmt = select(model.Step).where(model.Step.id == step_id)
        result = await self.session.execute(stmt)
        return result.one()

    async def list(self):
        stmt = select(model.Step)
        result = await self.session.execute(stmt)
        return result.all()

    async def _delete(self, step):
        await self.session.delete(step)

    async def get_steps_from_deployment(self, deployment_id):
        stmt = select(model.Step).where(model.Step.deployment_id == deployment_id)
        result = await self.session.execute(stmt)
        return result.all()


class InMemoryStepRepository(AbstractStepRepository):
    def __init__(self):
        self._steps = []
        super().__init__()

    async def _add(self, step):
        self._steps.append(step)
        step.id = len(self._steps)

    async def get(self, step_id):
        return next((s,) for s in self._steps if s.id == step_id)

    async def list(self):
        return [(s,) for s in self._steps]

    async def _delete(self, step):
        self._steps.remove(step)

    async def get_steps_from_deployment(self, deployment_id):
        return ((s,) for s in self._steps if s.deployment_id == deployment_id)
