"""Notification (alerts) endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.core.responses import success
from app.models.user import UserPublic
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_alerts(current: UserPublic = Depends(get_current_user)):
    items = await notification_service.list_user_alerts(current.id)
    return success(items)
