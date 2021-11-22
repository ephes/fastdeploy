from datetime import datetime, timezone
from typing import cast

from fastapi import APIRouter, BackgroundTasks, Depends

from ..auth import ServiceToken
from ..database import repository
from ..dependencies import get_current_active_user, get_current_service_token
from ..models import Deployment, Service, User
from ..tasks import get_deploy_environment, run_deploy


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_deployments(current_user: User = Depends(get_current_active_user)) -> list[Deployment]:
    return await repository.get_deployments()


@router.post("/")
async def create_deployment(
    background_tasks: BackgroundTasks, service_token: ServiceToken = Depends(get_current_service_token)
):
    assert isinstance(service_token.item_from_db, Service)
    service = cast(Service, service_token.item_from_db)
    assert isinstance(service.id, int)
    service_id = cast(int, service.id)

    deployment = Deployment(service_id=service_id, origin=service_token.origin, user=service_token.user)
    deployment.created = datetime.now(timezone.utc)  # FIXME: use CURRENT_TIMESTAMP from database
    await repository.add_deployment(deployment)

    environment = get_deploy_environment(service, deployment)
    background_tasks.add_task(run_deploy, environment)
    return deployment
