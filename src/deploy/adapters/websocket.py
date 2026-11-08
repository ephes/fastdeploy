import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from fastapi import WebSocket, status
from pydantic import BaseModel

from ..auth import token_to_payload, user_from_token
from ..domain import events
from ..service_layer.unit_of_work import AbstractUnitOfWork

logger = logging.getLogger(__name__)

# add 5 seconds to avoid closing a reconnecting client
EXPIRY_GRACE_SECONDS = 5
# A broadcast or control send waits at most this long for a client. A
# client that is slower is disconnected, so it cannot hold back the others.
BROADCAST_SEND_TIMEOUT_SECONDS = 5.0
# ... and at most this long waiting for the server's close handshake.
SLOW_CLIENT_CLOSE_TIMEOUT_SECONDS = 1.0
SHUTDOWN_TIMEOUT_SECONDS = 2.0


async def _finish_close(websocket: WebSocket, code: int, reason: str) -> None:
    with contextlib.suppress(Exception):  # the peer may already be gone
        await websocket.close(code=code, reason=reason)


async def close_websocket(websocket: WebSocket, code: int, reason: str, owned_tasks: set[asyncio.Task[None]]) -> None:
    """Bound the caller's wait, letting the server finish its transport teardown."""
    # Cancelling the server close while its send buffer is full can skip its
    # transport abort. Keep it alive under the server's own close deadline.
    task = asyncio.create_task(_finish_close(websocket, code, reason))
    owned_tasks.add(task)
    task.add_done_callback(owned_tasks.discard)
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(asyncio.shield(task), timeout=SLOW_CLIENT_CLOSE_TIMEOUT_SECONDS)


@dataclass
class _SendState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    failed: bool = False


class ConnectionManager:
    """
    Keep track of websocket connections.

    A client id belongs to exactly one live connection: a second connection
    using an id that is still connected is refused instead of replacing the
    first one. After successful authentication the id is bound to the user
    of the access token for the lifetime of the connection, and only
    authenticated connections receive broadcasts. The websocket endpoint
    closes a connection that does not authenticate within
    ``WEBSOCKET_AUTH_TIMEOUT_SECONDS``.
    """

    def __init__(self) -> None:
        self.all_connections: dict[UUID, WebSocket] = {}
        self.active_connections: dict[UUID, WebSocket] = {}
        self.principals: dict[UUID, str] = {}
        self.expiry_tasks: dict[UUID, asyncio.Task] = {}
        self.send_locks: dict[UUID, _SendState] = {}
        self.close_tasks: set[asyncio.Task[None]] = set()
        self.owned_timers: set[asyncio.Task] = set()
        self.shutting_down = False

    def startup(self) -> None:
        self.shutting_down = False

    async def close_socket(self, websocket: WebSocket, code: int, reason: str = "") -> None:
        if self.shutting_down:
            # Late request teardown must not create detached work after drain.
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(_finish_close(websocket, code, reason), SLOW_CLIENT_CLOSE_TIMEOUT_SECONDS)
            return
        await close_websocket(websocket, code, reason, self.close_tasks)

    async def shutdown(self) -> None:
        """Stop admission, forget sockets, and drain this manager's owned tasks."""
        self.shutting_down = True
        timers = set(self.owned_timers)
        for task in timers:
            task.cancel()
        sockets = list(self.all_connections.items())
        for client_id, websocket in sockets:
            self.disconnect(client_id, websocket)
            task = asyncio.create_task(_finish_close(websocket, status.WS_1001_GOING_AWAY, "server shutdown"))
            self.close_tasks.add(task)
            task.add_done_callback(self.close_tasks.discard)
        tasks = timers | self.close_tasks
        if tasks:
            try:
                await asyncio.wait(tasks, timeout=SHUTDOWN_TIMEOUT_SECONDS)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        self.close_tasks.difference_update(tasks)
        self.owned_timers.difference_update(tasks)

    async def _send_ordered(self, client_id: UUID, websocket: WebSocket, message: dict | str, *, final=False) -> bool:
        if self.all_connections.get(client_id) is not websocket:
            return False
        # Capture ownership before any await. Disconnect removes the map entry;
        # existing waiters retain this lock, while replacements get a fresh one.
        sender = self.send_locks.setdefault(client_id, _SendState())
        if final:
            self.disconnect(client_id, websocket)

        async def deliver():
            async with sender.lock:
                if sender.failed or (not final and self.all_connections.get(client_id) is not websocket):
                    return False
                try:
                    if isinstance(message, str):
                        await websocket.send_text(message)
                    else:
                        await websocket.send_json(message)
                except BaseException:
                    # The send may have written a partial frame. Poison every
                    # waiter, including final control sends, before unlocking.
                    sender.failed = True
                    self.disconnect(client_id, websocket)
                    raise
                return True

        # The same deadline covers both queue wait and transport send.
        return await asyncio.wait_for(deliver(), timeout=BROADCAST_SEND_TIMEOUT_SECONDS)

    async def connect(self, client_id: UUID, websocket: WebSocket) -> bool:
        """
        Accept the connection unless the client id is already in use.

        Returns False (and rejects the handshake) for a duplicate client id.
        """
        if self.shutting_down or client_id in self.all_connections:
            reason = "server shutting down" if self.shutting_down else "client id already in use"
            logger.warning("refusing websocket connection: %s", reason)
            await self.close_socket(websocket, status.WS_1008_POLICY_VIOLATION)
            return False
        # reserve the id before awaiting, so concurrent connects cannot both succeed
        self.all_connections[client_id] = websocket
        self.send_locks[client_id] = _SendState()
        try:
            await websocket.accept()
        except BaseException:
            self.disconnect(client_id, websocket)
            raise
        return True

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
        try:
            await self._send_ordered(client_id, websocket, {"type": "warning", "detail": message}, final=True)
        except Exception:  # connection might already be gone
            logger.debug("could not close websocket for client %s cleanly", client_id, exc_info=True)
        finally:
            await self.close_socket(websocket, code)

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
        task = asyncio.create_task(self._close_after(client_id, websocket, delay, message))
        self.expiry_tasks[client_id] = task
        self.owned_timers.add(task)
        task.add_done_callback(self.owned_timers.discard)

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
        try:
            await self._send_ordered(
                client_id, websocket, events.AuthenticationFailed(detail=detail).model_dump(), final=True
            )
        except Exception:  # connection might already be gone
            logger.debug("could not reject websocket for client %s cleanly", client_id, exc_info=True)
        finally:
            await self.close_socket(websocket, status.WS_1008_POLICY_VIOLATION)

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
        try:
            return await self._send_ordered(client_id, websocket, auth_event.model_dump())
        except Exception:
            self.disconnect(client_id, websocket)
            await self.close_socket(websocket, status.WS_1013_TRY_AGAIN_LATER)
            return False

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
        self.send_locks.pop(client_id, None)
        was_authenticated = self.active_connections.pop(client_id, None) is not None
        self.principals.pop(client_id, None)
        self._cancel_expiry(client_id)
        return was_authenticated

    async def send(self, client_id, message: dict):
        websocket = self.all_connections[client_id]
        await self._send_ordered(client_id, websocket, message)

    async def broadcast(self, message: BaseModel):
        """
        Send the message to every authenticated connection.

        The sends run concurrently and each one is bounded by
        ``BROADCAST_SEND_TIMEOUT_SECONDS``, so the broadcast as a whole is
        bounded and one slow client delays neither the other clients nor the
        publisher for longer than that. A client which exceeds the budget is
        disconnected, as is a client whose send fails; it has to reconnect
        and fetch the current state.
        """
        text = message.model_dump_json()
        connections = list(self.active_connections.items())
        await asyncio.gather(*(self._send_within_budget(client_id, ws, text) for client_id, ws in connections))

    async def _send_within_budget(self, client_id: UUID, websocket: WebSocket, text: str) -> None:
        try:
            await self._send_ordered(client_id, websocket, text)
        except asyncio.TimeoutError:
            logger.warning(
                "disconnecting websocket client %s: broadcast not sent within %s seconds",
                client_id,
                BROADCAST_SEND_TIMEOUT_SECONDS,
            )
            # Forget it first: the cancelled send may have written a partial
            # frame, so this connection must not get another broadcast.
            self.disconnect(client_id, websocket)
            await self.close_socket(websocket, status.WS_1013_TRY_AGAIN_LATER)
        except Exception:  # one broken connection must not stop the broadcast
            logger.info("broadcast to websocket client %s failed", client_id, exc_info=True)
            self.disconnect(client_id, websocket)
            await self.close_socket(websocket, status.WS_1013_TRY_AGAIN_LATER)

    async def publish(self, channel, event):  # noqa: ARG002 -- channel is part of the publisher interface; all clients get every event
        await self.broadcast(event)


connection_manager = ConnectionManager()
