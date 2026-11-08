import abc
from datetime import datetime, timezone

from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.exc import NoResultFound

from ..domain import model
from . import orm


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
        for service in self._services:
            if service.id == service_id:
                return service
        raise NoResultFound("Service not found")

    async def get_by_name(self, name):
        for service in self._services:
            if service.name == name:
                return service
        raise NoResultFound("Service not found")

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
        for user in self._users:
            if user.name == name:
                return user
        raise NoResultFound("User not found")

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
    async def get_for_update(self, deployment_id: int) -> model.Deployment:
        """
        Load the current state of a deployment and lock its row until the
        current transaction ends. Every writer of a deployment (finishing it,
        processing a step, the orphan cleanup) takes this lock first, so they
        are serialized.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def get_by_service(self, service_id: int) -> list[model.Deployment]:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_unfinished_by_service(self, service_id: int) -> list[model.Deployment]:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_orphaned_ids(self, *, activity_before: datetime, limit: int) -> list[int]:
        """Oldest eligible unfinished ids, bounded before materialization."""
        raise NotImplementedError

    @abc.abstractmethod
    async def list(
        self,
        *,
        limit: int | None = None,
        before_id: int | None = None,
        service_id: int | None = None,
        unfinished_only: bool = False,
    ) -> list[model.Deployment]:
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

    async def get_for_update(self, deployment_id):
        # PostgreSQL ``SELECT ... FOR UPDATE``; populate_existing refreshes an
        # instance already loaded in this session with the state seen after locking.
        stmt = (
            select(model.Deployment)
            .where(model.Deployment.id == deployment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_by_service(self, service_id):
        stmt = select(model.Deployment).where(model.Deployment.service_id == service_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_orphaned_ids(self, *, activity_before: datetime, limit: int) -> list[int]:
        # One bulk predicate includes every step's activity, without loading
        # deployment/step models or doing per-deployment activity queries.
        open_or_recent = (
            select(orm.steps.c.id)
            .where(
                orm.steps.c.deployment_id == orm.deployments.c.id,
                or_(
                    orm.steps.c.state.in_(("pending", "running")),
                    orm.steps.c.started > activity_before,
                    orm.steps.c.finished > activity_before,
                ),
            )
            .exists()
        )
        stmt = (
            select(orm.deployments.c.id)
            .where(
                orm.deployments.c.finished.is_(None),
                orm.deployments.c.started <= activity_before,
                ~open_or_recent,
            )
            .order_by(orm.deployments.c.id)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def list(self, *, limit=None, before_id=None, service_id=None, unfinished_only=False):
        stmt = select(model.Deployment).order_by(model.Deployment.id.desc())
        if before_id is not None:
            stmt = stmt.where(model.Deployment.id < before_id)
        if service_id is not None:
            stmt = stmt.where(model.Deployment.service_id == service_id)
        if unfinished_only:
            stmt = stmt.where(model.Deployment.finished.is_(None))
        if limit is not None:
            stmt = stmt.limit(limit)
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

        A deployment is successful if it is finished, has at least one step
        and all of its steps succeeded. A single failed step (including the
        failure step recorded for an orphaned deployment) disqualifies it.
        """
        statement = text(
            """
            select deployment.id
            from deployment
            where deployment.service_id = :service_id
            and deployment.finished is not null
            and exists (
                select 1 from step
                where step.deployment_id = deployment.id
                and step.state = 'success'
            )
            and not exists (
                select 1 from step
                where step.deployment_id = deployment.id
                and step.state != 'success'
            )
            order by deployment.started desc nulls last
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
        for deployment in self._deployments:
            if deployment.id == deployment_id:
                return deployment
        # same as the SQLAlchemy repository
        raise NoResultFound(f"Deployment {deployment_id} not found")

    async def get_for_update(self, deployment_id):
        # In-memory repositories never suspend, so writers cannot interleave.
        return await self.get(deployment_id)

    async def get_by_service(self, service_id):
        return [d for d in self._deployments if d.service_id == service_id]

    async def get_unfinished_by_service(self, service_id):
        return [d for d in self._deployments if d.service_id == service_id and d.finished is None]

    async def get_orphaned_ids(self, *, activity_before: datetime, limit: int) -> list[int]:
        def recent(value: datetime | None) -> bool:
            if value is None:
                return False
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value > activity_before

        candidates: list[int] = []
        for deployment in sorted(self._deployments, key=lambda d: d.id or 0):
            if deployment.id is None or deployment.finished is not None or deployment.started is None:
                continue
            if recent(deployment.started):
                continue
            steps = (
                await self.step_repository.get_steps_by_deployment(deployment.id)
                if self.step_repository is not None
                else []
            )
            if any(s.state in ("pending", "running") or recent(s.started) or recent(s.finished) for s in steps):
                continue
            candidates.append(deployment.id)
            if len(candidates) >= limit:
                break
        return candidates

    async def get_last_successful_deployment_id(self, service_id):
        last_successful = None
        if self.step_repository is None:
            return last_successful

        for deployment in self._deployments:
            if deployment.service_id != service_id or deployment.finished is None or deployment.id is None:
                continue

            steps = await self.step_repository.get_steps_by_deployment(deployment.id)
            if not steps or any(step.state != "success" for step in steps):
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

    async def list(self, *, limit=None, before_id=None, service_id=None, unfinished_only=False):
        deployments = [
            d
            for d in self._deployments
            if d.id is not None
            and (before_id is None or d.id < before_id)
            and (service_id is None or d.service_id == service_id)
            and (not unfinished_only or d.finished is None)
        ]
        return sorted(deployments, key=lambda d: d.id, reverse=True)[:limit]


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
        # populate_existing: steps loaded earlier in this session are refreshed,
        # so a reload after locking the deployment sees their current state.
        stmt = (
            select(model.Step)
            .where(model.Step.deployment_id == deployment_id)
            .execution_options(populate_existing=True)
        )
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


class AbstractServiceTokenRepository(abc.ABC):
    @abc.abstractmethod
    async def add(self, service_token: model.ServiceToken) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_by_jti(self, jti: str, for_update: bool = False) -> model.ServiceToken | None:
        """
        Return the token record or None. With ``for_update`` the row is locked
        until the current transaction ends.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def list(self) -> list[model.ServiceToken]:
        raise NotImplementedError

    @abc.abstractmethod
    async def delete_stale(self, cutoff: datetime) -> int:
        """
        Delete records of tokens that expired or were revoked before
        ``cutoff`` and return how many were deleted.
        """
        raise NotImplementedError


class SqlAlchemyServiceTokenRepository(AbstractServiceTokenRepository):
    def __init__(self, session):
        self.session = session

    async def add(self, service_token):
        self.session.add(service_token)

    async def get_by_jti(self, jti, for_update=False):
        stmt = select(model.ServiceToken).where(model.ServiceToken.jti == jti)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self):
        stmt = select(model.ServiceToken).order_by(model.ServiceToken.id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_stale(self, cutoff):
        token = model.ServiceToken
        stmt = (
            delete(token)
            .where(or_(token.expires_at < cutoff, and_(token.revoked_at.is_not(None), token.revoked_at < cutoff)))
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0


class InMemoryServiceTokenRepository(AbstractServiceTokenRepository):
    def __init__(self) -> None:
        self._service_tokens: list[model.ServiceToken] = []
        self._last_id = 0

    async def add(self, service_token):
        if service_token.id is None:
            self._service_tokens.append(service_token)
            self._last_id += 1
            service_token.id = self._last_id

    async def get_by_jti(self, jti, for_update=False):  # noqa: ARG002
        return next((t for t in self._service_tokens if t.jti == jti), None)

    async def list(self):
        return list(self._service_tokens)

    async def delete_stale(self, cutoff):
        kept = [t for t in self._service_tokens if not t.is_stale(cutoff)]
        deleted = len(self._service_tokens) - len(kept)
        self._service_tokens = kept
        return deleted
