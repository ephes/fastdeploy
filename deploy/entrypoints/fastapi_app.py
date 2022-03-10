from fastapi import FastAPI

from .routers import deployments, services, steps, users


app = FastAPI()
app.include_router(users.router)
app.include_router(steps.router)
app.include_router(services.router)
app.include_router(deployments.router)
