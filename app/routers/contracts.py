"""Contract CRUD endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.core.responses import success
from app.core.dependencies import get_current_user
from app.models.contract import (
    ContractCreateRequest,
    ContractStatus,
    ContractUpdateRequest,
    SignContractRequest,
)
from app.models.user import UserPublic
from app.services import contract_service, storage_service

router = APIRouter(prefix="/contracts", tags=["Contracts"])


@router.get("/stats/summary")
async def stats_summary(current: UserPublic = Depends(get_current_user)):
    summary = await contract_service.stats_summary(current.id)
    return success(summary.model_dump(mode="json"))


@router.get("")
async def list_contracts(
    status_filter: Optional[ContractStatus] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    current: UserPublic = Depends(get_current_user),
):
    items = await contract_service.list_contracts(
        current.id,
        status_filter=status_filter,
        search=search,
        limit=limit,
        skip=skip,
    )
    return success([c.model_dump(mode="json") for c in items])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_contract(
    payload: ContractCreateRequest,
    current: UserPublic = Depends(get_current_user),
):
    contract = await contract_service.create_contract(current.id, payload)
    return success(contract.model_dump(mode="json"), message="Contract created.")


@router.get("/{contract_id}")
async def get_contract(contract_id: str, current: UserPublic = Depends(get_current_user)):
    contract = await contract_service.get_contract(current.id, contract_id)
    return success(contract.model_dump(mode="json"))


@router.patch("/{contract_id}")
async def update_contract(
    contract_id: str,
    payload: ContractUpdateRequest,
    current: UserPublic = Depends(get_current_user),
):
    contract = await contract_service.update_contract(current.id, contract_id, payload)
    return success(contract.model_dump(mode="json"), message="Contract updated.")


@router.delete("/{contract_id}")
async def delete_contract(contract_id: str, current: UserPublic = Depends(get_current_user)):
    await contract_service.delete_contract(current.id, contract_id)
    return success(None, message="Contract deleted.")


@router.post("/{contract_id}/upload-pdf")
async def upload_pdf(
    contract_id: str,
    file: UploadFile = File(...),
    current: UserPublic = Depends(get_current_user),
):
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_FILE_TYPE", "message": "Only PDF files are accepted."},
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EMPTY_FILE", "message": "Uploaded file is empty."},
        )
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "FILE_TOO_LARGE", "message": "PDF must be 25 MB or smaller."},
        )

    filename = file.filename or f"contract_{contract_id}.pdf"
    pdf_url = await storage_service.upload_pdf_bytes(raw, filename=filename)
    contract = await contract_service.attach_pdf(current.id, contract_id, pdf_url)
    return success(contract.model_dump(mode="json"), message="PDF uploaded.")


@router.post("/{contract_id}/sign")
async def sign_contract(
    contract_id: str,
    payload: SignContractRequest,
    current: UserPublic = Depends(get_current_user),
):
    signature_url = await storage_service.upload_signature_base64(
        payload.signature_image_base64, contract_id=contract_id
    )
    contract = await contract_service.attach_signature(current.id, contract_id, signature_url)
    return success(contract.model_dump(mode="json"), message="Contract signed.")
