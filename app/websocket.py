from uuid import UUID

from fastapi import WebSocket
from jose import JWTError  # type: ignore
from pydantic import BaseModel


class ConnectionManager:
    def __init__(self) -> None:
        self.all_connections: dict[UUID, WebSocket] = {}
        self.active_connections: dict[UUID, WebSocket] = {}

    async def connect(self, client_id: UUID, websocket: WebSocket):
        await websocket.accept()
        self.all_connections[client_id] = websocket

    async def authenticate(self, client_id: UUID, access_token: str):
        from .auth import get_user_from_access_token

        try:
            user = await get_user_from_access_token(access_token)
            message = {
                "type": "authentication",
                "detail": f"access token verification successful for user {user.name}",
            }
            self.active_connections[client_id] = self.all_connections[client_id]
        except JWTError:
            message = {"type": "authentication", "detail": "access token verification failed"}
        await self.send(client_id, message)

    def disconnect(self, client_id: UUID):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        del self.all_connections[client_id]

    async def send(self, client_id, message: dict):
        await self.all_connections[client_id].send_json(message)

    async def broadcast(self, message: BaseModel):
        for connection in self.active_connections.values():
            await connection.send_text(message.json())

    async def handle_event(self, event):
        await self.broadcast(event)


connection_manager = ConnectionManager()
