from fastapi import APIRouter, Depends

from ..dependencies import get_current_active_user
from ..models import User


router = APIRouter()


@router.get("/users/me/", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    print("in read_users_me")
    return current_user
