"""Payment milestone endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.responses import success
from app.models.payment import (
    PaymentCreateRequest,
    PaymentStatus,
    PaymentSummary,
    PaymentUpdateRequest,
    derive_payment_status,
    payment_doc_to_public,
)
from app.models.user import UserPublic

router = APIRouter(prefix="/payments", tags=["Payments"])


def _oid(value: str, *, code: str, message: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail={"code": code, "message": message})


@router.get("/summary")
async def summary(current: UserPublic = Depends(get_current_user)):
    db = get_db()
    user_oid = ObjectId(current.id)
    cursor = db["payments"].find({"user_id": user_oid})

    total_earned = 0.0
    total_pending = 0.0
    total_overdue = 0.0
    paid_count = pending_count = overdue_count = 0
    async for doc in cursor:
        amount = float(doc.get("amount", 0))
        status_ = derive_payment_status(doc)
        if status_ == PaymentStatus.PAID:
            total_earned += amount
            paid_count += 1
        elif status_ == PaymentStatus.OVERDUE:
            total_overdue += amount
            overdue_count += 1
        elif status_ == PaymentStatus.PENDING:
            total_pending += amount
            pending_count += 1

    return success(
        PaymentSummary(
            total_earned=total_earned,
            total_pending=total_pending,
            total_overdue=total_overdue,
            overdue_count=overdue_count,
            pending_count=pending_count,
            paid_count=paid_count,
        ).model_dump(mode="json")
    )


@router.get("")
async def list_payments(
    contract_id: Optional[str] = Query(default=None),
    status_filter: Optional[PaymentStatus] = Query(default=None, alias="status"),
    current: UserPublic = Depends(get_current_user),
):
    db = get_db()
    query: dict = {"user_id": ObjectId(current.id)}
    if contract_id:
        query["contract_id"] = _oid(
            contract_id, code="INVALID_CONTRACT_ID", message="Invalid contract ID."
        )
    cursor = db["payments"].find(query).sort("due_date", 1)
    docs = [d async for d in cursor]
    items = [payment_doc_to_public(d) for d in docs]
    if status_filter:
        items = [p for p in items if p.status == status_filter]
    return success([p.model_dump(mode="json") for p in items])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_payment(
    payload: PaymentCreateRequest, current: UserPublic = Depends(get_current_user)
):
    db = get_db()
    contract_oid = _oid(
        payload.contract_id, code="INVALID_CONTRACT_ID", message="Invalid contract ID."
    )
    contract = await db["contracts"].find_one(
        {"_id": contract_oid, "user_id": ObjectId(current.id)}
    )
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONTRACT_NOT_FOUND", "message": "Parent contract not found."},
        )

    now = datetime.now(timezone.utc)
    doc = {
        "contract_id": contract_oid,
        "user_id": ObjectId(current.id),
        "amount": float(payload.amount),
        "currency": payload.currency,
        "due_date": payload.due_date,
        "paid_date": None,
        "status": payload.status.value,
        "notes": payload.notes,
        "created_at": now,
        "updated_at": now,
    }
    result = await db["payments"].insert_one(doc)
    doc["_id"] = result.inserted_id
    return success(payment_doc_to_public(doc).model_dump(mode="json"), message="Payment added.")


@router.patch("/{payment_id}")
async def update_payment(
    payment_id: str,
    payload: PaymentUpdateRequest,
    current: UserPublic = Depends(get_current_user),
):
    db = get_db()
    pay_oid = _oid(payment_id, code="INVALID_PAYMENT_ID", message="Invalid payment ID.")
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is not None:
        new_status: PaymentStatus = updates["status"]
        updates["status"] = new_status.value
        if new_status == PaymentStatus.PAID and "paid_date" not in updates:
            updates["paid_date"] = datetime.now(timezone.utc)
    if not updates:
        doc = await db["payments"].find_one({"_id": pay_oid, "user_id": ObjectId(current.id)})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "PAYMENT_NOT_FOUND", "message": "Payment not found."},
            )
        return success(payment_doc_to_public(doc).model_dump(mode="json"))

    updates["updated_at"] = datetime.now(timezone.utc)
    result = await db["payments"].update_one(
        {"_id": pay_oid, "user_id": ObjectId(current.id)},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PAYMENT_NOT_FOUND", "message": "Payment not found."},
        )
    doc = await db["payments"].find_one({"_id": pay_oid})
    assert doc is not None
    return success(payment_doc_to_public(doc).model_dump(mode="json"), message="Payment updated.")


@router.delete("/{payment_id}")
async def delete_payment(payment_id: str, current: UserPublic = Depends(get_current_user)):
    db = get_db()
    pay_oid = _oid(payment_id, code="INVALID_PAYMENT_ID", message="Invalid payment ID.")
    result = await db["payments"].delete_one(
        {"_id": pay_oid, "user_id": ObjectId(current.id)}
    )
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PAYMENT_NOT_FOUND", "message": "Payment not found."},
        )
    return success(None, message="Payment deleted.")
