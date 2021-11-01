from fastapi import APIRouter, Depends

from ..auth import CREDENTIALS_EXCEPTION
from ..dependencies import get_current_deployment
from ..models import Deployment, Step, StepBase, add_step, get_step_by_id, update_step
from ..websocket import connection_manager


router = APIRouter(
    prefix="/steps",
    tags=["steps"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
async def steps(step_in: StepBase, deployment: Deployment = Depends(get_current_deployment)) -> Step:
    step = Step(**step_in.dict(), deployment_id=deployment.id)
    add_step(step)
    await connection_manager.broadcast(step)
    return step


@router.put("/{step_id}")
async def step_update(
    step_id: int, step_in: StepBase, deployment: Deployment = Depends(get_current_deployment)
) -> Step:
    step = get_step_by_id(step_id)
    if step.deployment_id != deployment.id:
        raise CREDENTIALS_EXCEPTION
    step.name = step_in.name
    update_step(step)
    await connection_manager.broadcast(step)
    return step
