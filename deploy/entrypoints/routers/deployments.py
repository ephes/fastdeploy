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


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    responses={404: {"description": "Not found"}},
)


@router.get("/", dependencies=[Depends(get_current_active_user)])
async def get_deployments(bus: Bus = Depends()) -> list[Deployment]:
    """
    Get all deployments from database.
    """
    deployments = await views.get_all_deployments(bus.uow)
    return [Deployment(**d.dict()) for d in deployments]


@router.get("/{deployment_id}")
async def get_deployment_details(
    deployment_id: int,
    bus: Bus = Depends(),
    service: model.Service = Depends(get_current_active_service),
) -> DeploymentWithSteps:
    """
    Fetch details of a deployment including the steps. Needs to be authenticated
    with a service token for the service which is associated with the deployment.
    """
    try:
        deployment = await views.get_deployment_with_steps(deployment_id, bus.uow)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=404, detail="Deployment not found")
    if service.id != deployment.service_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wrong service token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # steps = [Step(**s.dict()) for s in deployment.steps]
    deployment_with_steps = DeploymentWithSteps(**deployment.dict())
    return deployment_with_steps


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
    except Exception:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return {"detail": f"Deployment {deployment.id} finished"}


@router.post("/")
async def start_deployment(
    request: Request,
    context: DeploymentContext = DeploymentContext(env={}),
    service: model.Service = Depends(get_current_active_service),
    bus: Bus = Depends(),
) -> DeploymentWithDetailsUrl:
    """
    Start a new deployment. Needs to be authenticated with a service token. Invoked
    by frontend or github action. The service token is used to get the current
    service from the database.
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
        service_id=service.id, origin=service.origin, user=service.user, context=context.dict()
    )
    try:
        await bus.handle(cmd)
    except Exception:
        raise HTTPException(status_code=400, detail="Something went wrong")

    started_event = handle_deployment_started.event
    details_url = request.url_for("get_deployment_details", deployment_id=str(started_event.id))
    return DeploymentWithDetailsUrl(**started_event.dict(), details=details_url)
