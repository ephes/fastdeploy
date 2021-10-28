from uuid import UUID

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import database
from .config import settings
from .routers import deployments, steps, users
from .websocket import connection_manager


database.create_db_and_tables()
app = FastAPI()
app.include_router(users.router)
app.include_router(deployments.router)
app.include_router(steps.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def read_root():
    return {"Hello": "World"}


# This only works with fastapi app not with api router
# see: https://github.com/tiangolo/fastapi/issues/98
@app.websocket("/deployments/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: UUID):
    await connection_manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            print("received data: ", data)
            if data.get("access_token") is not None:
                # try to authenticate client
                await connection_manager.authenticate(client_id, data["access_token"])
                print("client authenticated..")
            else:
                await connection_manager.broadcast({"message": "message from backend!"})
    except WebSocketDisconnect:
        connection_manager.disconnect(client_id)
        await connection_manager.broadcast(f"Client #{client_id} left the chat")
