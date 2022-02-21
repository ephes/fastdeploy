from pydantic import BaseModel


class Event(BaseModel):
    pass


class ServiceCreated(Event):
    id: int
    name: str
    data: dict = {}
