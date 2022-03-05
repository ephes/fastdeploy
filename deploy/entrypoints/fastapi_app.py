from fastapi import FastAPI

from .routers import services, users


app = FastAPI()
app.include_router(users.router)
app.include_router(services.router)
