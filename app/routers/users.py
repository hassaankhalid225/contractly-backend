"""User profile endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.responses import success
from app.models.user import UserPublic, UserUpdateRequest, user_doc_to_public

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me")
async def get_me(current: UserPublic = Depends(get_current_user)):
    return success(current.model_dump(mode="json"))


@router.patch("/me")
async def update_me(payload: UserUpdateRequest, current: UserPublic = Depends(get_current_user)):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return success(current.model_dump(mode="json"), message="Nothing to update.")
    updates["updated_at"] = datetime.now(timezone.utc)

    db = get_db()
    await db["users"].update_one({"_id": ObjectId(current.id)}, {"$set": updates})
    doc = await db["users"].find_one({"_id": ObjectId(current.id)})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "User not found."},
        )
    return success(user_doc_to_public(doc).model_dump(mode="json"), message="Profile updated.")


@router.delete("/me")
async def delete_me(current: UserPublic = Depends(get_current_user)):
    db = get_db()
    user_oid = ObjectId(current.id)
    await db["contracts"].delete_many({"user_id": user_oid})
    await db["payments"].delete_many({"user_id": user_oid})
    await db["refresh_tokens"].delete_many({"user_id": user_oid})
    await db["users"].delete_one({"_id": user_oid})
    return success(None, message="Account deleted.")
