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


class StepOut(Step):
    type: str = "step"

    def dict(self, *args, **kwargs):
        serialized = super().dict(*args, **kwargs)
        serialized["in_progress"] = self.started is not None and self.finished is None
        serialized["done"] = self.finished is not None
        return serialized


@router.post("/")
async def steps(step_in: StepBase, deployment: Deployment = Depends(get_current_deployment)) -> StepOut:
    step = Step(**step_in.dict(), deployment_id=deployment.id)
    add_step(step)
    step_out = StepOut.parse_obj(step)
    await connection_manager.broadcast(step_out)
    return step_out


@router.put("/{step_id}")
async def step_update(
    step_id: int, step_in: StepBase, deployment: Deployment = Depends(get_current_deployment)
) -> StepOut:
    step = get_step_by_id(step_id)
    if step.deployment_id != deployment.id:
        raise CREDENTIALS_EXCEPTION
    step.name = step_in.name
    step.started = step_in.started
    step.finished = step_in.finished
    update_step(step)
    step_out = StepOut.parse_obj(step)
    await connection_manager.broadcast(step_out)
    return step_out
