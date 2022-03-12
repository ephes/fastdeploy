from fastapi import APIRouter, Depends, HTTPException

from ... import views
from ...bootstrap import get_bus
from ...domain import commands, model
from ...service_layer.messagebus import MessageBus
from ..dependencies import get_current_active_deployment, get_current_active_user
from .helper_models import Deployment, Step, StepResult


router = APIRouter(
    prefix="/steps",
    tags=["steps"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
async def process_step_result(
    step: StepResult,
    deployment: Deployment = Depends(get_current_active_deployment),
    bus: MessageBus = Depends(get_bus),
) -> dict:
    """
    When a step is finished, the deployment process sends a result back to this endpoint.
    Needs to be authenticated with a deployment token.
    """
    assert isinstance(deployment.id, int)
    cmd = commands.ProcessStep(**step.dict(), deployment_id=deployment.id)
    try:
        await bus.handle(cmd)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail="Something went wrong")
    return {"detail": "step processed"}


@router.get("/")
async def get_steps_by_deployment(
    deployment_id: int,
    _: model.User = Depends(get_current_active_user),
    bus: MessageBus = Depends(get_bus),
) -> list[Step]:
    """
    Get all steps for a deployment.
    """
    async with bus.uow as uow:
        deployment = await views.get_deployment_with_steps(deployment_id, uow)

    return [Step(**step.dict()) for step in deployment.steps]
