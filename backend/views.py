from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .connection import connection_manager

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    await connection_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await connection_manager.broadcast({"message": "message from backend!"})
            print("received data: ", data)
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
        await connection_manager.broadcast(f"Client #{client_id} left the chat")
