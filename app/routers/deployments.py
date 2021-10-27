from fastapi import APIRouter, BackgroundTasks, Depends

from ..dependencies import (
    get_current_active_user,
    get_current_service,
    get_service_by_name,
)
from ..models import Service, User
from ..tasks import (
    get_deploy_environment_by_service,
    get_deploy_environment_by_user,
    run_deploy,
)


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def read_root():
    return {"Hello": "Deployments"}


@router.post("/deploy-by-user")
async def deploy_by_user(
    service: Service,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
):
    print("received deploy event from user: ", current_user)
    service_from_db = get_service_by_name(service.name)
    environment = get_deploy_environment_by_user(current_user, service_from_db)
    background_tasks.add_task(run_deploy, environment)
    return {"message": "deploying"}


@router.post("/deploy-by-service")
async def deploy_by_service(
    background_tasks: BackgroundTasks, current_service: Service = Depends(get_current_service)
):
    print("received deploy event from service: ", current_service)
    environment = get_deploy_environment_by_service(current_service)
    background_tasks.add_task(run_deploy, environment)
    return {"message": "deploying"}
