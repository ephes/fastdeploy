from pydantic import BaseModel


class PService(BaseModel):
    id: int | None
    name: str
    data: dict = {}


class PServiceOut(PService):
    """
    Additional type and deleted attributes to make it easier to identify
    them when received via websocket and to decide whether they should be
    added/updated or deleted.
    """

    type: str = "service"
    deleted: bool = False
