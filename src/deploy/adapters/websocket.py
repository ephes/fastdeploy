import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import WebSocket, status
from pydantic import BaseModel

from ..auth import token_to_payload, user_from_token
from ..config import settings
from ..domain import events
from ..service_layer.unit_of_work import AbstractUnitOfWork

logger = logging.getLogger(__name__)

# add 5 seconds to avoid closing a reconnecting client
EXPIRY_GRACE_SECONDS = 5
# A broadcast waits at most this long for one client to take a message. A
# client that is slower is disconnected, so it cannot hold back the others.
BROADCAST_SEND_TIMEOUT_SECONDS = 5.0
# ... and at most this long for the close handshake of such a client.
SLOW_CLIENT_CLOSE_TIMEOUT_SECONDS = 1.0
# How long telling a client that it did not authenticate in time may take,
# and again closing its connection. Such a client may not read at all.
AUTH_TIMEOUT_CLOSE_TIMEOUT_SECONDS = 1.0


class ConnectionManager:
    """
    Keep track of websocket connections.

    A client id belongs to exactly one live connection: a second connection
    using an id that is still connected is refused instead of replacing the
    first one. After successful authentication the id is bound to the user
    of the access token for the lifetime of the connection, and only
    authenticated connections receive broadcasts. The websocket endpoint
    closes a connection that does not authenticate within
    ``WEBSOCKET_AUTH_TIMEOUT_SECONDS`` (see ``close_unauthenticated``).
    """

    def __init__(self) -> None:
        self.all_connections: dict[UUID, WebSocket] = {}
        self.active_connections: dict[UUID, WebSocket] = {}
        self.principals: dict[UUID, str] = {}
        self.expiry_tasks: dict[UUID, asyncio.Task] = {}

    async def connect(self, client_id: UUID, websocket: WebSocket) -> bool:
        """
        Accept the connection unless the client id is already in use.

        Returns False (and rejects the handshake) for a duplicate client id.
        """
        if client_id in self.all_connections:
            logger.warning("refusing websocket connection for client id already in use: %s", client_id)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return False
        # reserve the id before awaiting, so concurrent connects cannot both succeed
        self.all_connections[client_id] = websocket
        try:
            await websocket.accept()
        except BaseException:
            self.disconnect(client_id, websocket)
            raise
        return True

    async def close_unauthenticated(self, client_id: UUID, websocket: WebSocket) -> None:
        """
        Forget a connection that did not authenticate in time, tell the client
        and close the connection. Never raises and takes a bounded time: the
        client may not read at all. Telling it and closing are separate
        attempts, so a notification that cannot be sent does not prevent the
        close. The endpoint has to return afterwards, which ends the
        connection even if the close could not be sent either.
        """
        logger.info(
            "closing websocket client %s: not authenticated within %s seconds",
            client_id,
            settings.websocket_auth_timeout_seconds,
        )
        # Forget it first, a token arriving from now on is too late.
        self.disconnect(client_id, websocket)
        message = events.AuthenticationFailed(detail="authentication timeout").model_dump()
        for attempt in (
            websocket.send_json(message),
            websocket.close(code=status.WS_1008_POLICY_VIOLATION),
        ):
            try:
                await asyncio.wait_for(attempt, timeout=AUTH_TIMEOUT_CLOSE_TIMEOUT_SECONDS)
            except Exception:  # includes the timeout, the peer may be gone or not reading
                logger.debug("could not close unauthenticated websocket client %s cleanly", client_id, exc_info=True)

    def is_authenticated(self, client_id: UUID, websocket: WebSocket | None = None) -> bool:
        connection = self.active_connections.get(client_id)
        return connection is not None and (websocket is None or connection is websocket)

    async def close(self, client_id: UUID, message: str, code: int = status.WS_1000_NORMAL_CLOSURE):
        """
        Close the websocket with a message and forget about it.
        """
        websocket = self.all_connections.get(client_id)  # get, because client may have disconnected
        if websocket is None:
            return
        self.disconnect(client_id, websocket)
        try:
            await websocket.send_json({"type": "warning", "detail": message})
            await websocket.close(code=code)
        except Exception:  # connection might already be gone
            logger.debug("could not close websocket for client %s cleanly", client_id, exc_info=True)

    async def _close_after(self, client_id: UUID, websocket: WebSocket, delay: float, message: str):
        await asyncio.sleep(delay)
        if self.expiry_tasks.get(client_id) is asyncio.current_task():
            del self.expiry_tasks[client_id]
        if self.all_connections.get(client_id) is websocket:
            await self.close(client_id, message)

    def _cancel_expiry(self, client_id: UUID) -> None:
        task = self.expiry_tasks.pop(client_id, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def close_on_expire(self, client_id: UUID, expires_at: datetime):
        """
        Schedule closing websocket on token expiration.

        There is at most one pending expiry per client id. Scheduling a new
        one (re-authentication) or disconnecting cancels the previous one.
        """
        self._cancel_expiry(client_id)
        message = "Your session has expired."
        now = datetime.now(timezone.utc)
        if now >= expires_at:
            await self.close(client_id, message)
            return
        websocket = self.all_connections.get(client_id)
        if websocket is None:
            return
        delay = (expires_at - now).total_seconds() + EXPIRY_GRACE_SECONDS
        self.expiry_tasks[client_id] = asyncio.create_task(self._close_after(client_id, websocket, delay, message))

    async def reject(self, client_id: UUID, detail: str, websocket: WebSocket | None = None):
        """
        Tell the client its authentication failed and close the connection.

        If websocket is given, that connection is rejected, never a newer
        connection which reuses the client id in the meantime.
        """
        if websocket is None:
            websocket = self.all_connections.get(client_id)
            if websocket is None:
                return
        self.disconnect(client_id, websocket)
        try:
            await websocket.send_json(events.AuthenticationFailed(detail=detail).model_dump())
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:  # connection might already be gone
            logger.debug("could not reject websocket for client %s cleanly", client_id, exc_info=True)

    async def authenticate(self, client_id: UUID, access_token: str, uow: AbstractUnitOfWork) -> bool:
        """
        Authenticate the connection with a user access token.

        Any failure (invalid or expired token, a token that is not a user
        token, unknown user, ...) rejects and closes the connection. Returns
        whether the connection is authenticated afterwards.
        """
        websocket = self.all_connections.get(client_id)
        if websocket is None:
            return False
        try:
            user = await user_from_token(access_token, uow)
            payload = token_to_payload(access_token)
            expires_at = datetime.fromtimestamp(payload["exp"], timezone.utc)
            username = user.name
            if not username:
                raise ValueError("user without name")
        except Exception:
            logger.info("websocket access token verification failed for client %s", client_id, exc_info=True)
            await self.reject(client_id, "access token verification failed", websocket)
            return False

        if self.all_connections.get(client_id) is not websocket:
            # disconnected (and maybe replaced by a new connection) while verifying the token
            return False
        bound_user = self.principals.get(client_id)
        if bound_user is not None and bound_user != username:
            logger.warning("websocket client %s tried to re-authenticate as a different user", client_id)
            await self.reject(client_id, "client id is bound to a different user", websocket)
            return False

        self.principals[client_id] = username
        self.active_connections[client_id] = websocket
        # after successful authentication, add connection close callback on token expiration
        await self.close_on_expire(client_id, expires_at)
        auth_event = events.AuthenticationSucceeded(detail=f"access token verification successful for user {username}")
        await websocket.send_json(auth_event.model_dump())
        return True

    def disconnect(self, client_id: UUID, websocket: WebSocket | None = None) -> bool:
        """
        Forget about a connection. Idempotent.

        If websocket is given, only that connection is removed, never a newer
        connection reusing the same client id. Returns whether the removed
        connection was authenticated.
        """
        current = self.all_connections.get(client_id)
        if current is None or (websocket is not None and current is not websocket):
            return False
        del self.all_connections[client_id]
        was_authenticated = self.active_connections.pop(client_id, None) is not None
        self.principals.pop(client_id, None)
        self._cancel_expiry(client_id)
        return was_authenticated

    async def send(self, client_id, message: dict):
        await self.all_connections[client_id].send_json(message)

    async def broadcast(self, message: BaseModel):
        """
        Send the message to every authenticated connection.

        The sends run concurrently and each one is bounded by
        ``BROADCAST_SEND_TIMEOUT_SECONDS``, so the broadcast as a whole is
        bounded and one slow client delays neither the other clients nor the
        publisher for longer than that. A client which exceeds the budget is
        disconnected; it has to reconnect and fetch the current state.
        """
        text = message.model_dump_json()
        connections = list(self.active_connections.items())
        await asyncio.gather(*(self._send_within_budget(client_id, ws, text) for client_id, ws in connections))

    async def _send_within_budget(self, client_id: UUID, websocket: WebSocket, text: str) -> None:
        try:
            await asyncio.wait_for(websocket.send_text(text), timeout=BROADCAST_SEND_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(
                "disconnecting websocket client %s: broadcast not sent within %s seconds",
                client_id,
                BROADCAST_SEND_TIMEOUT_SECONDS,
            )
            # Forget it first: the cancelled send may have written a partial
            # frame, so this connection must not get another broadcast.
            self.disconnect(client_id, websocket)
            try:
                await asyncio.wait_for(
                    websocket.close(code=status.WS_1013_TRY_AGAIN_LATER), timeout=SLOW_CLIENT_CLOSE_TIMEOUT_SECONDS
                )
            except Exception:  # includes the timeout, the peer does not read anyway
                logger.debug("could not close slow websocket client %s cleanly", client_id, exc_info=True)
        except Exception:  # one broken connection must not stop the broadcast
            logger.info("broadcast to websocket client %s failed", client_id, exc_info=True)

    async def publish(self, channel, event):  # noqa: ARG002 -- channel is part of the publisher interface; all clients get every event
        await self.broadcast(event)


connection_manager = ConnectionManager()
