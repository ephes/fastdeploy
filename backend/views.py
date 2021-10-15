from fastapi import BackgroundTasks, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .connection import connection_manager
from .deployment import run_deploy


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/deploy")
async def deploy(background_tasks: BackgroundTasks):
    print("received deploy event")
    background_tasks.add_task(run_deploy, connection_manager)
    return {"message": "deploying"}
