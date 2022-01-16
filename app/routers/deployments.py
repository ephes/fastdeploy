from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ..auth import ServiceToken
from ..database import repository
from ..dependencies import (
    get_current_active_deployment,
    get_current_active_service_token,
    get_current_active_user,
)
from ..models import Deployment, DeploymentOut, Step, User
from ..tasks import get_deploy_environment, run_deploy


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_deployments(_: User = Depends(get_current_active_user)) -> list[Deployment]:
    """
    Get all deployments from database. Needs to be authenticated with a user
    access token.
    """
    return await repository.get_deployments()


WRONG_SERVICE_EXCEPTION = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Wrong service token",
    headers={"WWW-Authenticate": "Bearer"},
)


class DeploymentWithSteps(Deployment):
    steps: list[Step] = []


@router.get("/{deployment_id}")
async def get_deployment_details(
    deployment_id: int,
    service_token: ServiceToken = Depends(get_current_active_service_token),
) -> DeploymentWithSteps:
    """
    Fetch details of a deployment including the steps. Needs to be authenticated with a
    valid service token for the service which is associated with the deployment.
    """
    deployment = await repository.get_deployment_by_id(deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment does not exist")
    service = await repository.get_service_by_id(deployment.service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Service does not exist")
    if service_token.service != service.name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wrong service token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    steps = await repository.get_steps_by_deployment_id(deployment_id)
    deployment_with_steps = DeploymentWithSteps(**deployment.dict(), steps=steps)
    return deployment_with_steps


@router.post("/")
async def start_deployment(
    background_tasks: BackgroundTasks, service_token: ServiceToken = Depends(get_current_active_service_token)
) -> DeploymentOut:
    """
    Start a new deployment. Needs to be authenticated with a service token. Invoked
    by frontend or github action. The service token is used to get the current
    service from the database. The list of steps is fetched from service or last
    successful deployment. The deployment is started a background task (forking a new
    process later on).

    What should start deployment do?

    * Create a deployment model with created = now() and finished = None timestamps
    * Look up the steps from last deployment and recreate them as "pending" with new deployment id
    * If there are no last steps, create one new dummy step
    * Start deployment task
    * Mark the first step as "running"
    """
    service = service_token.service_model
    assert service is not None
    service_id = service.id
    assert service_id is not None

    deployment = Deployment(service_id=service_id, origin=service_token.origin, user=service_token.user)
    deployment.started = datetime.now(timezone.utc)  # FIXME: use CURRENT_TIMESTAMP from database
    pending_steps = await service.get_steps()
    deployment, steps = await repository.add_deployment(deployment, pending_steps)
    steps[0].state = "running"
    await repository.update_step(steps[0])
    environment = get_deploy_environment(deployment, steps, service.get_deploy_script())
    background_tasks.add_task(run_deploy, environment)
    return DeploymentOut(**deployment.dict())


@router.put("/finish/")
async def finish_deployment(deployment: Deployment = Depends(get_current_active_deployment)) -> DeploymentOut:
    """
    Finish a deployment. Need to be authenticated with a deployment access token.
    We set the finished timestamp on the server side because it should not be
    possible to update any deployment attributes.

    * Set the finished timestamp
    * Remove all steps with state "running" or "pending"
    """
    deployment.finished = datetime.now(timezone.utc)
    deployment = await repository.update_deployment(deployment)
    assert deployment.id is not None
    steps = await repository.get_steps_by_deployment_id(deployment.id)
    for step in steps:
        if step.state in ("running", "pending"):
            await repository.delete_step(step)
    return DeploymentOut(**deployment.dict())
