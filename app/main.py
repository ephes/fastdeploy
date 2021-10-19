from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import database
from .config import settings
from .routers import deployments, users


database.create_db_and_tables()
app = FastAPI()
app.include_router(users.router)
app.include_router(deployments.router)

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
