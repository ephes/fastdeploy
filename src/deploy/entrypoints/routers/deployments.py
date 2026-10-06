import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ... import views
from ...domain import commands, events, model
from ...tasks import DeploymentContext
from ..dependencies import (
    get_current_active_deployment,
    get_current_active_service,
    get_current_active_user,
)
from ..helper_models import (
    Bus,
    Deployment,
    DeploymentWithDetailsUrl,
    DeploymentWithSteps,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    responses={404: {"description": "Not found"}},
)


async def reconcile_orphaned_deployments(bus: Bus, deployment_id: int | None = None) -> list[int]:
    """
    Reconcile orphaned deployments (unfinished, without active steps and without
    recent activity) by finishing them as failed. Returns the ids of the deployments
    that were finished. Callers must check that the caller may access
    `deployment_id` before, because this writes.
    """
    if deployment_id is None:
        orphaned_ids = await views.get_orphaned_unfinished_deployment_ids(bus.uow)
    else:
        is_orphaned = await views.is_orphaned_unfinished_deployment(deployment_id, bus.uow)
        orphaned_ids = [deployment_id] if is_orphaned else []

    finished_ids: list[int] = []
    for orphaned_id in orphaned_ids:
        cmd = commands.FinishOrphanedDeployment(deployment_id=orphaned_id)
        if await bus.handle(cmd):
            finished_ids.append(orphaned_id)
    return finished_ids


@router.get("/", dependencies=[Depends(get_current_active_user)])
async def get_deployments(bus: Bus = Depends()) -> list[Deployment]:
    """
    Get all deployments from database.
    """
    await reconcile_orphaned_deployments(bus)
    deployments = await views.get_all_deployments(bus.uow)
    return [Deployment(**d.model_dump()) for d in deployments]


@router.get("/{deployment_id}")
async def get_deployment_details(
    deployment_id: int,
    bus: Bus = Depends(),
    service: model.Service = Depends(get_current_active_service),
) -> DeploymentWithSteps:
    """
    Fetch details of a deployment including the steps. Needs to be authenticated
    with a service token for the service which is associated with the deployment.
    Unknown deployments and deployments of other services both return 404, so the
    response does not reveal whether a deployment id exists.
    """
    not_found = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
    try:
        deployment = await views.get_deployment_with_steps(deployment_id, bus.uow)
    except views.DeploymentNotFound as e:
        raise not_found from e
    if service.id is None or service.id != deployment.service_id:
        logger.info("service %s requested deployment %s of another service", service.id, deployment_id)
        raise not_found

    # Only reconcile (which writes) after the ownership check.
    if await reconcile_orphaned_deployments(bus, deployment_id):
        deployment = await views.get_deployment_with_steps(deployment_id, bus.uow)
    return DeploymentWithSteps(**deployment.model_dump())


@router.put("/finish/")
async def finish_deployment(
    deployment: model.Deployment = Depends(get_current_active_deployment),
    bus: Bus = Depends(),
) -> dict:
    """
    Finish a deployment. Need to be authenticated with a deployment token.
    """
    if deployment.id is None:
        # this cannot happen -> it's just a type guard for command
        raise HTTPException(status_code=404, detail="Deployment not found")
    cmd = commands.FinishDeployment(deployment_id=deployment.id)
    try:
        await bus.handle(cmd)
    except Exception as e:
        raise HTTPException(status_code=404, detail="Deployment not found") from e
    return {"detail": f"Deployment {deployment.id} finished"}


@router.post("/", responses={409: {"description": "Another deployment of this service is still running"}})
async def start_deployment(
    request: Request,
    context: DeploymentContext = DeploymentContext(env={}),  # noqa: B008 -- FastAPI copies body defaults per request
    service: model.Service = Depends(get_current_active_service),
    bus: Bus = Depends(),
) -> DeploymentWithDetailsUrl:
    """
    Start a new deployment. Needs to be authenticated with a service token. Invoked
    by frontend or github action. The service token is used to get the current
    service from the database.

    Only one deployment per service may run at a time: if the service still has
    an active deployment, the request is rejected with 409 Conflict and the
    response detail names the running deployment id.
    """
    if service.id is None:
        # this cannot happen -> it's just a type guard
        raise HTTPException(status_code=404, detail="Service not found")

    # register deployment started handler to get the deployment_id
    class DeploymentStartedHandler:
        event: events.DeploymentStarted

        async def __call__(self, event: events.DeploymentStarted):
            self.event = event

    handle_deployment_started = DeploymentStartedHandler()
    bus.event_handlers[events.DeploymentStarted].append(handle_deployment_started)

    cmd = commands.StartDeployment(
        service_id=service.id, origin=service.origin, user=service.user, context=context.model_dump()
    )
    try:
        await bus.handle(cmd)
    except model.DeploymentAlreadyRunning as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Deployment {e.deployment_id} is still running for service {service.name}",
                "deployment_id": e.deployment_id,
            },
        ) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail="Something went wrong") from e

    started_event = handle_deployment_started.event
    # convert to string because url_for returns a URL and pydantic does not like that
    details_url = str(request.url_for("get_deployment_details", deployment_id=str(started_event.id)))
    return DeploymentWithDetailsUrl(**started_event.model_dump(), details=details_url)
