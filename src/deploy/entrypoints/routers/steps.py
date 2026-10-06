import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ... import views
from ...domain import commands
from ..dependencies import get_current_active_deployment, get_current_active_user
from ..helper_models import Bus, Deployment, Step, StepResult

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/steps",
    tags=["steps"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
async def process_step_result(
    step: StepResult,
    deployment: Deployment = Depends(get_current_active_deployment),
    bus: Bus = Depends(),
) -> dict:
    """
    When a step is finished, the deployment process sends a result back to this endpoint.
    Needs to be authenticated with a deployment token.
    """
    assert isinstance(deployment.id, int)
    cmd = commands.ProcessStep(**step.model_dump(), deployment_id=deployment.id)
    try:
        await bus.handle(cmd)
    except Exception as e:
        logger.warning("could not process step for deployment %s", deployment.id, exc_info=True)
        raise HTTPException(status_code=400, detail="Something went wrong") from e
    return {"detail": "step processed"}


@router.get("/", dependencies=[Depends(get_current_active_user)])
async def get_steps_by_deployment(
    deployment_id: int,
    bus: Bus = Depends(),
) -> list[Step]:
    """
    Get all steps for a deployment.
    """
    try:
        deployment = await views.get_deployment_with_steps(deployment_id, bus.uow)
    except views.DeploymentNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found") from e

    return [Step(**step.model_dump()) for step in deployment.steps]
