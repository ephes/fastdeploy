from datetime import datetime

from fastapi import APIRouter, Depends
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
    service: model.Service = Depends(get_current_active_service),
) -> DeploymentWithSteps:
    """
    Fetch details of a deployment including the steps. Needs to be authenticated with a
    valid service token for the service which is associated with the deployment.
    """
    # deployment = await repository.get_deployment_by_id(deployment_id)
    # if deployment is None:
    #     raise HTTPException(status_code=404, detail="Deployment does not exist")
    # if service.id != deployment.service_id:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Wrong service token",
    #         headers={"WWW-Authenticate": "Bearer"},
    #     )
    # steps = await repository.get_steps_by_deployment_id(deployment_id)
    # deployment_with_steps = DeploymentWithSteps(**deployment.dict(), steps=steps)
    # return deployment_with_steps
