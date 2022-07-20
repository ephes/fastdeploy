from uuid import UUID

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import settings
from .helper_models import Bus
from .routers import deployed_services, deployments, services, steps, users


app = FastAPI()
app.include_router(users.router)
app.include_router(steps.router)
app.include_router(services.router)
app.include_router(deployments.router)
app.include_router(deployed_services.router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount("/static", StaticFiles(directory="frontend/dist"), name="static")


@app.get("/")
async def redirect_typer():
    return RedirectResponse("/static/index.html")


class Message(BaseModel):
    message: str


# This only works with fastapi app not with api router
# see: https://github.com/tiangolo/fastapi/issues/98
@app.websocket("/deployments/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: UUID, bus: Bus = Depends()):
    connection_manager = bus.cm
    await connection_manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("access_token") is not None:
                # try to authenticate client
                await connection_manager.authenticate(client_id, data["access_token"], bus.uow)
            else:
                message = Message(message="message from backend!")
                await connection_manager.broadcast(message)
    except WebSocketDisconnect:
        connection_manager.disconnect(client_id)
        message = Message(message=f"Client #{client_id} left")
        await connection_manager.broadcast(message)
