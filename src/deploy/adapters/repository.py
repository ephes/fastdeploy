import abc

from sqlalchemy import delete, select, text

from ..domain import model


class AbstractServiceRepository(abc.ABC):
    def __init__(self) -> None:
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
    async def get(self, service_id: int) -> model.Service:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_by_name(self, name: str) -> model.Service:
        raise NotImplementedError

    @abc.abstractmethod
    async def list(self) -> list[model.Service]:
        raise NotImplementedError

    @abc.abstractmethod
    async def lock_for_deployment(self, service_id: int) -> None:
        """
        Serialize deployment starts for a service until the current
        transaction ends (commit or rollback).
        """
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
        return result.scalar_one()

    async def get_by_name(self, name) -> model.Service:
        stmt = select(model.Service).where(model.Service.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list(self) -> list[model.Service]:
        result = await self.session.execute(select(model.Service))
        return result.scalars().all()

    async def _delete(self, service):
        stmt = delete(model.Service).where(model.Service.id == service.id)
        await self.session.execute(stmt)

    async def lock_for_deployment(self, service_id):
        # Row lock on the service (PostgreSQL ``SELECT ... FOR UPDATE``). Concurrent
        # starts for the same service block here until the holder's transaction ends.
        stmt = select(model.Service).where(model.Service.id == service_id).with_for_update()
        await self.session.execute(stmt)


class InMemoryServiceRepository(AbstractServiceRepository):
    def __init__(self) -> None:
        self._services: list[model.Service] = []
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
        return next(s for s in self._services if s.id == service_id)

    async def get_by_name(self, name):
        return next(s for s in self._services if s.name == name)

    async def list(self):
        return list(self._services)

    async def _delete(self, service):
        self._services = [s for s in self._services if s.id != service.id]

    async def lock_for_deployment(self, service_id: int) -> None:  # noqa: ARG002
        # In-memory repositories never suspend, so check and insert cannot interleave.
        return None


class AbstractUserRepository(abc.ABC):
    def __init__(self) -> None:
        self.seen: set[model.User] = set()

    @abc.abstractmethod
    async def _add(self, user: model.User) -> None:
        raise NotImplementedError

    async def add(self, user: model.User) -> None:
        await self._add(user)
        self.seen.add(user)

    @abc.abstractmethod
    async def get(self, name) -> model.User:
        raise NotImplementedError

    @abc.abstractmethod
    async def list(self) -> list[model.User]:
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
        return result.scalar_one()

    async def list(self):
        result = await self.session.execute(select(model.User))
        return result.scalars().all()


class InMemoryUserRepository(AbstractUserRepository):
    def __init__(self) -> None:
        self._users: list[model.User] = []
        super().__init__()

    async def _add(self, user):
        self._users.append(user)
        user.id = len(self._users)

    async def get(self, name):
        return next(u for u in self._users if u.name == name)

    async def list(self):
        return list(self._users)


class AbstractDeploymentRepository(abc.ABC):
    def __init__(self) -> None:
        self.seen: set[model.Deployment] = set()

    @abc.abstractmethod
    async def _add(self, deployment: model.Deployment) -> None:
        raise NotImplementedError

    async def add(self, deployment: model.Deployment) -> None:
        await self._add(deployment)
        self.seen.add(deployment)

    @abc.abstractmethod
    async def get(self, deployment_id: int) -> model.Deployment:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_by_service(self, service_id: int) -> list[model.Deployment]:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_unfinished_by_service(self, service_id: int) -> list[model.Deployment]:
        raise NotImplementedError

    @abc.abstractmethod
    async def list(self) -> list[model.Deployment]:
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
        return result.scalar_one()

    async def get_by_service(self, service_id):
        stmt = select(model.Deployment).where(model.Deployment.service_id == service_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list(self):
        stmt = select(model.Deployment)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_unfinished_by_service(self, service_id):
        stmt = (
            select(model.Deployment)
            .where(model.Deployment.service_id == service_id)
            .where(model.Deployment.finished.is_(None))
            .order_by(model.Deployment.id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

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
            limit 1
        """
        )
        result = await self.session.execute(statement, {"service_id": service_id})
        return result.scalar_one_or_none()


class InMemoryDeploymentRepository(AbstractDeploymentRepository):
    def __init__(self, step_repository=None) -> None:
        self._deployments: list[model.Deployment] = []
        self.step_repository = step_repository
        super().__init__()

    async def _add(self, deployment):
        if deployment.id is None:
            self._deployments.append(deployment)
            deployment.id = len(self._deployments)
            return

        for idx, existing in enumerate(self._deployments):
            if existing.id == deployment.id:
                self._deployments[idx] = deployment
                return

        self._deployments.append(deployment)

    async def get(self, deployment_id):
        return next(d for d in self._deployments if d.id == deployment_id)

    async def get_by_service(self, service_id):
        return [d for d in self._deployments if d.service_id == service_id]

    async def get_unfinished_by_service(self, service_id):
        return [d for d in self._deployments if d.service_id == service_id and d.finished is None]

    async def get_last_successful_deployment_id(self, service_id):
        last_successful = None
        if self.step_repository is None:
            return last_successful

        for deployment in self._deployments:
            if deployment.service_id != service_id or deployment.finished is None or deployment.id is None:
                continue

            steps = await self.step_repository.get_steps_by_deployment(deployment.id)
            successful_steps = [step for step in steps if step.state == "success"]
            failed_steps = [step for step in steps if step.state != "success"]
            if not successful_steps or len(failed_steps) > 1:
                continue

            if last_successful is None:
                last_successful = deployment
                continue

            if deployment.started is not None and (
                last_successful.started is None or deployment.started > last_successful.started
            ):
                last_successful = deployment

        if last_successful is None:
            return None
        return last_successful.id

    async def list(self):
        return list(self._deployments)


class AbstractStepRepository(abc.ABC):
    def __init__(self) -> None:
        self.seen: set[model.Step] = set()

    @abc.abstractmethod
    async def _add(self, step: model.Step) -> None:
        raise NotImplementedError

    async def add(self, step: model.Step) -> None:
        await self._add(step)
        self.seen.add(step)

    @abc.abstractmethod
    async def get(self, step_id: int) -> model.Step:
        raise NotImplementedError

    @abc.abstractmethod
    async def _delete(self, step: model.Step) -> None:
        raise NotImplementedError

    async def delete(self, step: model.Step) -> None:
        await self._delete(step)
        self.seen.add(step)

    @abc.abstractmethod
    async def get_steps_by_deployment(self, deployment_id: int) -> list[model.Step]:
        raise NotImplementedError

    @abc.abstractmethod
    async def list(self) -> list[model.Step]:
        # list has to be after get_steps_by_deployment otherwise
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
        return result.scalar_one()

    async def list(self):
        stmt = select(model.Step)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def _delete(self, step):
        await self.session.delete(step)

    async def get_steps_by_deployment(self, deployment_id):
        stmt = select(model.Step).where(model.Step.deployment_id == deployment_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class InMemoryStepRepository(AbstractStepRepository):
    def __init__(self) -> None:
        self._steps: list[model.Step] = []
        super().__init__()

    async def _add(self, step):
        self._steps.append(step)
        step.id = len(self._steps)

    async def get(self, step_id):
        return next(s for s in self._steps if s.id == step_id)

    async def list(self):
        return list(self._steps)

    async def _delete(self, step):
        self._steps.remove(step)

    async def get_steps_by_deployment(self, deployment_id):
        return [s for s in self._steps if s.deployment_id == deployment_id]


class AbstractDeployedServiceRepository(abc.ABC):
    def __init__(self) -> None:
        self.seen: set[model.DeployedService] = set()

    @abc.abstractmethod
    async def _add(self, deployed_service: model.DeployedService) -> None:
        raise NotImplementedError

    async def add(self, deployed_service: model.DeployedService) -> None:
        await self._add(deployed_service)
        self.seen.add(deployed_service)

    # @abc.abstractmethod
    # async def _delete(self, deployed_service: model.DeployedService) -> None:
    #     raise NotImplementedError

    @abc.abstractmethod
    async def list(self) -> list[model.DeployedService]:
        raise NotImplementedError


class SqlAlchemyDeployedServiceRepository(AbstractDeployedServiceRepository):
    def __init__(self, session):
        self.session = session
        super().__init__()

    async def _add(self, deployed_service):
        print("adding: ", deployed_service)
        self.session.add(deployed_service)

    async def list(self):
        stmt = select(model.DeployedService)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class InMemoryDeployedServiceRepository(AbstractDeployedServiceRepository):
    def __init__(self) -> None:
        self._deployed_services: list[model.DeployedService] = []
        super().__init__()

    async def _add(self, deployed_service):
        self._deployed_services.append(deployed_service)
        deployed_service.id = len(self._deployed_services)

    async def list(self):
        return list(self._deployed_services)
