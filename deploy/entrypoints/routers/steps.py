from fastapi import APIRouter, Depends

from ..dependencies import get_current_active_deployment
from .helper_models import Deployment, Step


router = APIRouter(
    prefix="/steps",
    tags=["steps"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
async def process_step_result(step_in: Step, deployment: Deployment = Depends(get_current_active_deployment)) -> Step:
    """
    When a step is finished, the deployment process sends a result back to this endpoint.
    Needs to be authenticated with a deployment token.
    """
    assert isinstance(deployment.id, int)
    # step = Step(**step_in.dict(), deployment_id=deployment.id)
    # step = await deployment.process_step(step)
    # return step
    return Step(
        id=2, name="foobar", deployment_id=deployment.id, state="finished", started=None, finished=None, message=""
    )
