"""Payment milestone domain models."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class PaymentCreateRequest(BaseModel):
    contract_id: str
    amount: float = Field(..., ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=4)
    due_date: datetime
    notes: Optional[str] = None
    status: PaymentStatus = PaymentStatus.PENDING

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class PaymentUpdateRequest(BaseModel):
    amount: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    due_date: Optional[datetime] = None
    paid_date: Optional[datetime] = None
    status: Optional[PaymentStatus] = None
    notes: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v


class PaymentPublic(BaseModel):
    id: str
    contract_id: str
    user_id: str
    amount: float
    currency: str
    due_date: datetime
    paid_date: Optional[datetime] = None
    status: PaymentStatus
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PaymentSummary(BaseModel):
    total_earned: float
    total_pending: float
    total_overdue: float
    overdue_count: int
    pending_count: int
    paid_count: int


def derive_payment_status(doc: Dict[str, Any]) -> PaymentStatus:
    raw = doc.get("status", PaymentStatus.PENDING.value)
    try:
        current = PaymentStatus(raw)
    except ValueError:
        current = PaymentStatus.PENDING

    if current in (PaymentStatus.PAID, PaymentStatus.CANCELLED):
        return current

    due: Optional[datetime] = doc.get("due_date")
    if due is None:
        return current

    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)

    if due < datetime.now(timezone.utc):
        return PaymentStatus.OVERDUE
    return PaymentStatus.PENDING


def payment_doc_to_public(doc: Dict[str, Any]) -> PaymentPublic:
    return PaymentPublic(
        id=str(doc["_id"]),
        contract_id=str(doc["contract_id"]),
        user_id=str(doc["user_id"]),
        amount=float(doc.get("amount", 0.0)),
        currency=doc.get("currency", "USD"),
        due_date=doc.get("due_date"),
        paid_date=doc.get("paid_date"),
        status=derive_payment_status(doc),
        notes=doc.get("notes"),
        created_at=doc.get("created_at", datetime.now(timezone.utc)),
        updated_at=doc.get("updated_at", datetime.now(timezone.utc)),
    )
