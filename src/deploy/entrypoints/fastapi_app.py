import asyncio
import contextlib
from uuid import UUID

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, status
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


async def _first_authentication(websocket: WebSocket, client_id: UUID, bus: Bus) -> bool:
    """
    Wait for the first access token of a connection and verify it. Messages
    without a token are ignored. Returns whether the connection is
    authenticated; a failed attempt has already closed it.
    """
    while True:
        data = await websocket.receive_json()
        if not isinstance(data, dict):
            return False
        if data.get("access_token") is not None:
            return await bus.cm.authenticate(client_id, data["access_token"], bus.uow)


# This only works with fastapi app not with api router
# see: https://github.com/tiangolo/fastapi/issues/98
@app.websocket("/deployments/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: UUID, bus: Bus = Depends()):
    connection_manager = bus.cm
    if not await connection_manager.connect(client_id, websocket):
        return  # client id already in use by a live connection
    was_authenticated = False
    close_code, close_reason = status.WS_1000_NORMAL_CLOSURE, ""
    try:
        # One budget for everything up to the first successful authentication:
        # waiting for the token and verifying it, whatever else is sent.
        try:
            authenticated = await asyncio.wait_for(
                _first_authentication(websocket, client_id, bus),
                timeout=settings.websocket_auth_timeout_seconds,
            )
        except asyncio.TimeoutError:
            authenticated = False
            close_code, close_reason = status.WS_1008_POLICY_VIOLATION, "authentication timeout"
        while authenticated:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                break
            if data.get("access_token") is not None:
                # re-authentication, a failed attempt closes the connection
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
            # Not wrapped in a timeout of our own: the server's close gives up
            # on a peer that does not answer and then drops the TCP connection,
            # cancelling it early would skip exactly that.
            with contextlib.suppress(Exception):
                await websocket.close(code=close_code, reason=close_reason)
    if was_authenticated:
        await connection_manager.broadcast(Message(message="Client left"))
