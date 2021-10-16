from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import deployments, users


app = FastAPI()
app.include_router(users.router)
app.include_router(deployments.router)

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
async def read_root():
    return {"Hello": "World"}
