import contextlib
from uuid import UUID

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.websockets import WebSocketState

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
    if not await connection_manager.connect(client_id, websocket):
        return  # client id already in use by a live connection
    was_authenticated = False
    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                break
            if data.get("access_token") is not None:
                # try to authenticate client, a failed attempt closes the connection
                if not await connection_manager.authenticate(client_id, data["access_token"], bus.uow):
                    break
            elif connection_manager.is_authenticated(client_id, websocket):
                message = Message(message="message from backend!")
                await connection_manager.broadcast(message)
    except WebSocketDisconnect:
        pass
    finally:
        # always forget the connection, whatever ended the loop
        was_authenticated = connection_manager.disconnect(client_id, websocket)
        if (
            websocket.client_state != WebSocketState.DISCONNECTED
            and websocket.application_state != WebSocketState.DISCONNECTED
        ):
            with contextlib.suppress(Exception):
                await websocket.close()
    if was_authenticated:
        await connection_manager.broadcast(Message(message="Client left"))
