from fastapi import Depends, HTTPException

from .auth import get_current_user
from .models import User


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
