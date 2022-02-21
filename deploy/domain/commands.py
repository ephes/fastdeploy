from pydantic import BaseModel


class Command(BaseModel):
    pass


class CreateService(Command):
    name: str
    data: dict
