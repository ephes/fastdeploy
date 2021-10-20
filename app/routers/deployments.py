from fastapi import APIRouter, BackgroundTasks, Depends

from ..connection import connection_manager
from ..dependencies import get_current_active_user
from ..models import User
from ..tasks import run_deploy


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def read_root():
    return {"Hello": "Deployments"}


@router.post("/deploy")
async def deploy(background_tasks: BackgroundTasks, current_user: User = Depends(get_current_active_user)):
    print("received deploy event from user: ", current_user)
    background_tasks.add_task(run_deploy, current_user)
    return {"message": "deploying"}


@router.post("/event")
async def receive_deploy_event(event: dict):
    print("received event: ", event)
    await connection_manager.broadcast(event)
    return {"received": True}
