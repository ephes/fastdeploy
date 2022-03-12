import asyncio

from datetime import datetime, timezone
from uuid import UUID

from fastapi import WebSocket
from jose import JWTError  # type: ignore
from pydantic import BaseModel

from ..auth import token_to_payload, user_from_token
from ..domain import events
from ..domain.model import User
from ..service_layer.unit_of_work import AbstractUnitOfWork


class ConnectionManager:
    def __init__(self) -> None:
        self.all_connections: dict[UUID, WebSocket] = {}
        self.active_connections: dict[UUID, WebSocket] = {}

    async def connect(self, client_id: UUID, websocket: WebSocket):
        await websocket.accept()
        self.all_connections[client_id] = websocket

    async def close(self, client_id: UUID, message: str):
        """
        Close the websocket with a message.
        """
        websocket = self.all_connections.get(client_id)  # get, because client may have disconnected
        if websocket is not None:
            print("closing websocket: ", datetime.now(timezone.utc))
            await websocket.send_json({"type": "warning", "detail": message})
            await websocket.close()

    async def close_on_expire(self, client_id: UUID, expires_at: datetime):
        """
        Schedule closing websocket on token expiration.
        """
        print("close on expire called..")
        message = "Your session has expired."
        now = datetime.now(timezone.utc)
        if now >= expires_at:
            await self.close(client_id, message)
        else:
            # add 5 seconds to avoid closing a reconnecting client
            expires_in_seconds = int((expires_at - now).total_seconds()) + 5
            print("expires in seconds: ", expires_in_seconds)
            loop = asyncio.get_event_loop()
            loop.call_later(expires_in_seconds, asyncio.create_task, self.close(client_id, message))

    async def authenticate(self, client_id: UUID, access_token: str, uow: AbstractUnitOfWork):
        try:
            user = await user_from_token(access_token, uow)
            token = token_to_payload(access_token)
            expires_at = datetime.fromtimestamp(token["exp"], timezone.utc)
            connection = self.all_connections[client_id]
            # after successful authentication, add connection close callback on token expiration
            await self.close_on_expire(client_id, expires_at)
            print("authenticated: ", user.name)
            assert isinstance(user, User)
            auth_event = events.AuthenticationSucceeded(
                detail=f"access token verification successful for user {user.name}"
            )
            self.active_connections[client_id] = connection
            print("client successfully authenticated: ", client_id)
        except JWTError:
            print("verification failed")
            auth_event = events.AuthenticationFailed(detail="access token verification failed")
        await self.send(client_id, auth_event.dict())

    def disconnect(self, client_id: UUID):
        print("disconnecting client: ", client_id)
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        del self.all_connections[client_id]

    async def send(self, client_id, message: dict):
        await self.all_connections[client_id].send_json(message)

    async def broadcast(self, message: BaseModel):
        print("active connections: ", self.active_connections)
        for connection in self.active_connections.values():
            await connection.send_text(message.json())

    async def publish(self, channel, event):
        print("websocket publish: ", channel, event)
        await self.broadcast(event)


connection_manager = ConnectionManager()
