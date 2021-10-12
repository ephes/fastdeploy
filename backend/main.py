from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            await websocket.send_json({"message": "message from backend!"})
            print("received data: ", data)
    except WebSocketDisconnect:
        print("client has closed connection")
