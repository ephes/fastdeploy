from uuid import UUID

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.all_connections: dict[UUID, WebSocket] = {}
        self.active_connections: dict[UUID, WebSocket] = {}

    async def connect(self, client_id: UUID, websocket: WebSocket):
        await websocket.accept()
        self.all_connections[client_id] = websocket

    def disconnect(self, client_id: UUID):
        del self.all_connections[client_id]

    async def broadcast(self, message: dict):
        for connection in self.all_connections.values():
            await connection.send_json(message)


connection_manager = ConnectionManager()
