from uuid import UUID

from fastapi import WebSocket
from jose import JWTError

from .auth import verify_access_token


class ConnectionManager:
    def __init__(self) -> None:
        self.all_connections: dict[UUID, WebSocket] = {}
        self.active_connections: dict[UUID, WebSocket] = {}

    async def connect(self, client_id: UUID, websocket: WebSocket):
        await websocket.accept()
        self.all_connections[client_id] = websocket

    async def authenticate(self, client_id: UUID, access_token: str):
        try:
            token_data = verify_access_token(access_token)
            message = {
                "type": "authentication",
                "detail": f"access token verification successful for user {token_data.username}",
            }
            self.active_connections[client_id] = self.all_connections[client_id]
        except JWTError:
            message = {"type": "authentication", "detail": "access token verification failed"}
        await self.send(client_id, message)

    def disconnect(self, client_id: UUID):
        del self.all_connections[client_id]

    async def send(self, client_id, message: dict):
        await self.all_connections[client_id].send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.all_connections.values():
            await connection.send_json(message)


connection_manager = ConnectionManager()
