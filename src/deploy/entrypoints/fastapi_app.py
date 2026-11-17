import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketState

from ..adapters.websocket import connection_manager
from ..bootstrap import database_lifespan
from ..config import settings
from .helper_models import Bus
from .routers import deployed_services, deployments, services, steps, users

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with database_lifespan(_app):
        connection_manager.startup()
        try:
            yield
        finally:
            await connection_manager.shutdown()


HTTP_BODY_MAX_BYTES = 1024 * 1024
HTTP_BODY_TIMEOUT_SECONDS = 10.0


class RequestBodyAdmission:
    """Bound actual mutation body bytes and time before FastAPI parses anything."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH", "DELETE"}:
            await self.app(scope, receive, send)
            return
        # Content-Length is only an early refusal; actual bytes always decide admission.
        for key, value in scope["headers"]:
            if key.lower() == b"content-length" and value.isdigit():
                length = value.lstrip(b"0")
                if len(length) > 7 or int(length or b"0") > HTTP_BODY_MAX_BYTES:
                    await JSONResponse({"detail": "Request body is too large"}, status_code=413)(scope, receive, send)
                    return
        body = bytearray()
        try:
            async with asyncio.timeout(HTTP_BODY_TIMEOUT_SECONDS):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > HTTP_BODY_MAX_BYTES:
                        await JSONResponse({"detail": "Request body is too large"}, status_code=413)(
                            scope, receive, send
                        )
                        return
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await JSONResponse({"detail": "Request body timed out"}, status_code=408)(scope, receive, send)
            return
        admitted = bytes(body)
        del body
        consumed = False

        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": admitted, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


app = FastAPI(lifespan=lifespan)
app.add_middleware(RequestBodyAdmission)


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


@app.middleware("http")
async def private_responses(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Keep credentials and complete service configurations out of HTTP caches."""
    try:
        response = await call_next(request)
    except Exception as exc:
        # Handle before ServerErrorMiddleware: its exception handler re-raises
        # and would let the ASGI server print backend exception text.
        logger.error("request_failed category=%s", type(exc).__name__)
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    path = request.url.path.rstrip("/")
    if path in {"/token", "/service-token", "/services", "/deployed-services"} or any(
        path == prefix or path.startswith(prefix + "/") for prefix in ("/deployments", "/steps")
    ):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers.add_vary_header("Authorization")
    return response


app.mount("/static", StaticFiles(directory="frontend/dist"), name="static")


@app.get("/")
async def redirect_typer():
    return RedirectResponse("/static/index.html")


class Message(BaseModel):
    message: str


# Clients only send small control messages ({"access_token": "<jwt>"}). Admit
# them before any JSON decoding or credential work: the transport accepts much
# larger frames, and decoding one builds its whole object tree at once.
WEBSOCKET_CONTROL_MAX_BYTES = 8 * 1024
WEBSOCKET_ACCESS_TOKEN_MAX_LENGTH = 4096


class InadmissibleFrame(Exception):
    """A client frame that is refused before decoding or credential work."""

    def __init__(self, code: int, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _unique_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate member")
        result[key] = value
    return result


def admit_control_frame(message: Mapping[str, Any]) -> dict:
    """Return the decoded control object of a received frame or raise InadmissibleFrame."""
    text = message.get("text")
    if not isinstance(text, str):
        raise InadmissibleFrame(status.WS_1008_POLICY_VIOLATION, "text frames only")
    # A str cannot hold more UTF-8 bytes than four per character: check the
    # cheap bound before encoding.
    if len(text) > WEBSOCKET_CONTROL_MAX_BYTES or len(text.encode("utf-8", "surrogatepass")) > (
        WEBSOCKET_CONTROL_MAX_BYTES
    ):
        raise InadmissibleFrame(status.WS_1009_MESSAGE_TOO_BIG, "control message too large")
    try:
        data = json.loads(text, object_pairs_hook=_unique_members)
    except (ValueError, RecursionError):
        raise InadmissibleFrame(status.WS_1008_POLICY_VIOLATION, "invalid control message") from None
    if not isinstance(data, dict):
        raise InadmissibleFrame(status.WS_1008_POLICY_VIOLATION, "invalid control message")
    token = data.get("access_token")
    if token is not None and (
        not isinstance(token, str) or not token or len(token) > WEBSOCKET_ACCESS_TOKEN_MAX_LENGTH
    ):
        raise InadmissibleFrame(status.WS_1008_POLICY_VIOLATION, "invalid control message")
    return data


async def receive_control(websocket: WebSocket) -> dict:
    """Receive one client frame and admit it as a control message."""
    message = await websocket.receive()
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", status.WS_1000_NORMAL_CLOSURE), message.get("reason"))
    return admit_control_frame(message)


async def _first_authentication(websocket: WebSocket, client_id: UUID, bus: Bus) -> bool:
    """
    Wait for the first access token of a connection and verify it. Messages
    without a token are ignored. Returns whether the connection is
    authenticated; a failed attempt has already closed it.
    """
    while True:
        data = await receive_control(websocket)
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
            data = await receive_control(websocket)
            if data.get("access_token") is not None:
                # re-authentication, a failed attempt closes the connection
                if not await connection_manager.authenticate(client_id, data["access_token"], bus.uow):
                    break
            elif connection_manager.is_authenticated(client_id, websocket):
                message = Message(message="message from backend!")
                await connection_manager.broadcast(message)
    except WebSocketDisconnect:
        pass
    except InadmissibleFrame as refusal:
        logger.info("websocket client %s sent an inadmissible frame: %s", client_id, refusal.reason)
        close_code, close_reason = refusal.code, refusal.reason
    finally:
        # always forget the connection, whatever ended the loop
        was_authenticated = connection_manager.disconnect(client_id, websocket)
        if (
            websocket.client_state != WebSocketState.DISCONNECTED
            and websocket.application_state != WebSocketState.DISCONNECTED
        ):
            await connection_manager.close_socket(websocket, close_code, close_reason)
    if was_authenticated:
        await connection_manager.broadcast(Message(message="Client left"))
