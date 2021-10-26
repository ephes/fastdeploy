from fastapi import APIRouter, BackgroundTasks, Depends

from ..dependencies import (
    get_current_active_user,
    get_current_service,
    get_service_by_id,
)
from ..models import Service, User
from ..tasks import (  # get_deploy_environment_by_user,
    get_deploy_environment_by_service,
    run_deploy,
)
from ..websocket import connection_manager


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def read_root():
    return {"Hello": "Deployments"}


# @router.post("/deploy-by-user/{service_id}")
# async def deploy_by_user(
#     service_id: int, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_active_user)
# ):
@router.post("/deploy-by-user/{service_id}")
async def deploy_by_user(
    service_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    service: Service = Depends(get_service_by_id),
):
    print("received deploy event from user: ", current_user)
    print("service_id: ", service_id)
    # print("service: ", service)
    # environment = get_deploy_environment_by_user(current_user, None)
    # background_tasks.add_task(run_deploy, environment)
    return {"message": "deploying"}


@router.post("/deploy-by-service")
async def deploy_by_service(
    background_tasks: BackgroundTasks, current_service: Service = Depends(get_current_service)
):
    print("received deploy event from service: ", current_service)
    environment = get_deploy_environment_by_service(current_service)
    background_tasks.add_task(run_deploy, environment)
    return {"message": "deploying"}


@router.post("/event")
async def receive_deploy_event(event: dict):
    print("received event: ", event)
    await connection_manager.broadcast(event)
    return {"received": True}
