from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ... import views
from ...bootstrap import get_bus
from ...domain import model
from ...service_layer.messagebus import MessageBus
from ..dependencies import get_current_active_service, get_current_active_user
from .steps import Step


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    responses={404: {"description": "Not found"}},
)


class Deployment(BaseModel):
    id: int
    service_id: int
    origin: str
    user: str
    started: datetime | None
    finished: datetime | None
    context: dict


@router.get("/")
async def get_deployments(
    _: model.User = Depends(get_current_active_user), bus: MessageBus = Depends(get_bus)
) -> list[Deployment]:
    """
    Get all deployments from database.
    """
    deployments = await views.get_all_deployments(bus.uow)
    return [Deployment(**d.dict()) for d in deployments]


class DeploymentWithSteps(Deployment):
    steps: list[Step] = []


@router.get("/{deployment_id}")
async def get_deployment_details(
    deployment_id: int,
    bus: MessageBus = Depends(get_bus),
    service: model.Service = Depends(get_current_active_service),
) -> DeploymentWithSteps:
    """
    Fetch details of a deployment including the steps. Needs to be authenticated with a
    valid service token for the service which is associated with the deployment.
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
