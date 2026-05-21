"""User Pydantic models and Mongo-document helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, EmailStr, Field


class AuthProvider(str, Enum):
    GOOGLE = "google"
    PHONE = "phone"


class UserBase(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    photo_url: Optional[str] = None


class UserPublic(UserBase):
    """User shape returned to clients."""
    id: str
    provider: AuthProvider
    created_at: datetime
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    photo_url: Optional[str] = None


def user_doc_to_public(doc: Dict[str, Any]) -> UserPublic:
    """Convert a raw Mongo user doc into a `UserPublic`."""
    return UserPublic(
        id=str(doc["_id"]),
        name=doc.get("name"),
        email=doc.get("email"),
        phone=doc.get("phone"),
        photo_url=doc.get("photo_url"),
        provider=AuthProvider(doc.get("provider", AuthProvider.GOOGLE.value)),
        created_at=doc.get("created_at", datetime.now(timezone.utc)),
        is_active=doc.get("is_active", True),
    )


def new_user_doc(
    *,
    provider: AuthProvider,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    photo_url: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "name": name,
        "email": email,
        "phone": phone,
        "photo_url": photo_url,
        "provider": provider.value,
        "created_at": datetime.now(timezone.utc),
        "is_active": True,
    }
