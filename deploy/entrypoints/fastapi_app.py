from fastapi import FastAPI

from .routers import services


app = FastAPI()
app.include_router(services.router)
