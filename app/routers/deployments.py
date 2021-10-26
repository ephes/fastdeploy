from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import Session, select

from .. import database
from ..dependencies import get_current_active_user, get_current_service
from ..models import Service, User
from ..tasks import (
    get_deploy_environment_by_service,
    get_deploy_environment_by_user,
    run_deploy,
)
from ..websocket import connection_manager


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
    with Session(database.engine) as session:
        service_from_db = session.exec(select(Service).where(Service.name == service.name)).first()
    if service_from_db is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service not found",
        )
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


@router.post("/event")
async def receive_deploy_event(event: dict):
    print("received event: ", event)
    await connection_manager.broadcast(event)
    return {"received": True}
