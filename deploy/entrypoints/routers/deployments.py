from fastapi import APIRouter, Depends, HTTPException, Request, status

from ... import views
from ...bootstrap import get_bus
from ...domain import commands, model
from ...service_layer.messagebus import MessageBus
from ...tasks import DeploymentContext
from ..dependencies import (
    get_current_active_deployment,
    get_current_active_service,
    get_current_active_user,
)
from .helper_models import Deployment, DeploymentWithDetailsUrl, DeploymentWithSteps


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_deployments(
    _: model.User = Depends(get_current_active_user), bus: MessageBus = Depends(get_bus)
) -> list[Deployment]:
    """
    Get all deployments from database.
    """
    deployments = await views.get_all_deployments(bus.uow)
    return [Deployment(**d.dict()) for d in deployments]


@router.get("/{deployment_id}")
async def get_deployment_details(
    deployment_id: int,
    bus: MessageBus = Depends(get_bus),
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
    deployment: model.Deployment = Depends(get_current_active_deployment), bus: MessageBus = Depends(get_bus)
) -> dict:
    """
    Finish a deployment. Need to be authenticated with a deployment token.
    """
    if deployment.id is None:
        # this cannot happen -> it's just a type guard for command
        raise HTTPException(status_code=404, detail="Deployment not found")
    cmd = commands.FinishDeployment(id=deployment.id)
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
    bus: MessageBus = Depends(get_bus),
) -> DeploymentWithDetailsUrl:
    """
    Start a new deployment. Needs to be authenticated with a service token. Invoked
    by frontend or github action. The service token is used to get the current
    service from the database.
    """
    if service.id is None:
        # this cannot happen -> it's just a type guard
        raise HTTPException(status_code=404, detail="Service not found")

    cmd = commands.StartDeployment(
        service_id=service.id, origin=service.origin, user=service.user, context=context.dict()
    )
    try:
        await bus.handle(cmd)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail="Something went wrong")

    try:
        started_deployment = await views.get_most_recently_started_deployment_for_service(cmd.service_id, bus.uow)
    except Exception:
        raise HTTPException(status_code=404, detail="Started Deployment not found")

    details_url = request.url_for("get_deployment_details", deployment_id=str(started_deployment.id))
    return DeploymentWithDetailsUrl(**started_deployment.dict(), details=details_url)
