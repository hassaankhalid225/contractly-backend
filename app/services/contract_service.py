"""Contract CRUD + summary statistics."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.core.database import get_db
from app.models.contract import (
    ContractCreateRequest,
    ContractPublic,
    ContractStatsSummary,
    ContractStatus,
    ContractUpdateRequest,
    contract_doc_to_public,
    derive_status,
)


def _to_oid(value: str, *, code: str = "INVALID_ID", message: str = "Invalid identifier.") -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail={"code": code, "message": message})


async def create_contract(user_id: str, payload: ContractCreateRequest) -> ContractPublic:
    db = get_db()
    now = datetime.now(timezone.utc)
    doc: Dict[str, Any] = {
        "user_id": ObjectId(user_id),
        "title": payload.title,
        "client_name": payload.client_name,
        "client_email": payload.client_email,
        "description": payload.description,
        "value": float(payload.value),
        "currency": payload.currency,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "status": (payload.status or ContractStatus.DRAFT).value,
        "work_type": payload.work_type.value if payload.work_type else None,
        "notes": payload.notes,
        "pdf_url": None,
        "signature_url": None,
        "signed_at": None,
        "ai_analysis": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db["contracts"].insert_one(doc)
    doc["_id"] = result.inserted_id
    return contract_doc_to_public(doc)


async def list_contracts(
    user_id: str,
    *,
    status_filter: Optional[ContractStatus] = None,
    search: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
) -> List[ContractPublic]:
    db = get_db()
    query: Dict[str, Any] = {"user_id": ObjectId(user_id)}

    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"client_name": {"$regex": search, "$options": "i"}},
        ]

    cursor = db["contracts"].find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = [d async for d in cursor]
    items = [contract_doc_to_public(d) for d in docs]
    if status_filter is not None:
        items = [c for c in items if c.status == status_filter]
    return items


async def get_contract(user_id: str, contract_id: str) -> ContractPublic:
    db = get_db()
    oid = _to_oid(contract_id, code="INVALID_CONTRACT_ID", message="Invalid contract ID.")
    doc = await db["contracts"].find_one({"_id": oid, "user_id": ObjectId(user_id)})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONTRACT_NOT_FOUND", "message": "The requested contract does not exist."},
        )
    return contract_doc_to_public(doc)


async def update_contract(
    user_id: str, contract_id: str, payload: ContractUpdateRequest
) -> ContractPublic:
    db = get_db()
    oid = _to_oid(contract_id, code="INVALID_CONTRACT_ID", message="Invalid contract ID.")
    updates: Dict[str, Any] = {}
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None:
        data["status"] = data["status"].value if hasattr(data["status"], "value") else data["status"]
    if "work_type" in data and data["work_type"] is not None:
        data["work_type"] = (
            data["work_type"].value if hasattr(data["work_type"], "value") else data["work_type"]
        )
    updates.update(data)
    if not updates:
        return await get_contract(user_id, contract_id)
    updates["updated_at"] = datetime.now(timezone.utc)
    result = await db["contracts"].update_one(
        {"_id": oid, "user_id": ObjectId(user_id)},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONTRACT_NOT_FOUND", "message": "The requested contract does not exist."},
        )
    return await get_contract(user_id, contract_id)


async def delete_contract(user_id: str, contract_id: str) -> None:
    db = get_db()
    oid = _to_oid(contract_id, code="INVALID_CONTRACT_ID", message="Invalid contract ID.")
    result = await db["contracts"].delete_one({"_id": oid, "user_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONTRACT_NOT_FOUND", "message": "The requested contract does not exist."},
        )
    # Cascade-delete payments tied to this contract
    await db["payments"].delete_many({"contract_id": oid, "user_id": ObjectId(user_id)})


async def attach_pdf(user_id: str, contract_id: str, pdf_url: str) -> ContractPublic:
    db = get_db()
    oid = _to_oid(contract_id, code="INVALID_CONTRACT_ID", message="Invalid contract ID.")
    result = await db["contracts"].update_one(
        {"_id": oid, "user_id": ObjectId(user_id)},
        {"$set": {"pdf_url": pdf_url, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONTRACT_NOT_FOUND", "message": "The requested contract does not exist."},
        )
    return await get_contract(user_id, contract_id)


async def attach_signature(user_id: str, contract_id: str, signature_url: str) -> ContractPublic:
    db = get_db()
    oid = _to_oid(contract_id, code="INVALID_CONTRACT_ID", message="Invalid contract ID.")
    now = datetime.now(timezone.utc)
    result = await db["contracts"].update_one(
        {"_id": oid, "user_id": ObjectId(user_id)},
        {
            "$set": {
                "signature_url": signature_url,
                "signed_at": now,
                "status": ContractStatus.ACTIVE.value,
                "updated_at": now,
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONTRACT_NOT_FOUND", "message": "The requested contract does not exist."},
        )
    return await get_contract(user_id, contract_id)


async def attach_analysis(user_id: str, contract_id: str, analysis: Dict[str, Any]) -> ContractPublic:
    db = get_db()
    oid = _to_oid(contract_id, code="INVALID_CONTRACT_ID", message="Invalid contract ID.")
    result = await db["contracts"].update_one(
        {"_id": oid, "user_id": ObjectId(user_id)},
        {"$set": {"ai_analysis": analysis, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONTRACT_NOT_FOUND", "message": "The requested contract does not exist."},
        )
    return await get_contract(user_id, contract_id)


async def stats_summary(user_id: str) -> ContractStatsSummary:
    db = get_db()
    cursor = db["contracts"].find({"user_id": ObjectId(user_id)})
    total = active = expiring = expired = draft = completed = 0
    total_value = 0.0
    currency_breakdown: Dict[str, float] = {}
    async for doc in cursor:
        total += 1
        derived = derive_status(doc)
        if derived == ContractStatus.ACTIVE:
            active += 1
        elif derived == ContractStatus.EXPIRING_SOON:
            expiring += 1
        elif derived == ContractStatus.EXPIRED:
            expired += 1
        elif derived == ContractStatus.DRAFT:
            draft += 1
        elif derived == ContractStatus.COMPLETED:
            completed += 1
        value = float(doc.get("value", 0.0))
        total_value += value
        currency = doc.get("currency", "USD")
        currency_breakdown[currency] = currency_breakdown.get(currency, 0.0) + value
    return ContractStatsSummary(
        total=total,
        active=active,
        expiring=expiring,
        expired=expired,
        draft=draft,
        completed=completed,
        total_value=total_value,
        currency_breakdown=currency_breakdown,
    )
