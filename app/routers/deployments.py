from fastapi import APIRouter, BackgroundTasks, Depends, WebSocket, WebSocketDisconnect

from ..connection import connection_manager
from ..dependencies import get_current_active_user
from ..deployment import run_deploy


router = APIRouter(
    prefix="/deployments",
    tags=["deployments"],
    dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def read_root():
    return {"Hello": "Deployments"}


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    await connection_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await connection_manager.broadcast({"message": "message from backend!"})
            print("received data: ", data)
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
        await connection_manager.broadcast(f"Client #{client_id} left the chat")


@router.post("/deploy")
async def deploy(background_tasks: BackgroundTasks):
    print("received deploy event")
    background_tasks.add_task(run_deploy)
    return {"message": "deploying"}
