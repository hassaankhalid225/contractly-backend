"""AI-powered endpoints for contract generation, analysis and templates."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.core.responses import success
from app.models.contract import (
    AnalyzeContractRequest,
    GenerateContractRequest,
    SuggestTemplateRequest,
)
from app.models.user import UserPublic
from app.services import ai_service, storage_service

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/generate-contract")
async def generate_contract(
    payload: GenerateContractRequest, current: UserPublic = Depends(get_current_user)
):
    if not payload.freelancer_name and current.name:
        payload = payload.model_copy(update={"freelancer_name": current.name})
    text = await ai_service.generate_contract(payload)
    return success({"contract_text_markdown": text}, message="Contract drafted.")


@router.post("/analyze-contract")
async def analyze_contract(
    payload: AnalyzeContractRequest, current: UserPublic = Depends(get_current_user)
):
    if not payload.contract_text and not payload.pdf_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "MISSING_INPUT",
                "message": "Provide either contract_text or pdf_url for analysis.",
            },
        )

    text = payload.contract_text
    if not text and payload.pdf_url:
        text = await storage_service.fetch_pdf_text(payload.pdf_url)

    if not text or not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "EMPTY_CONTRACT",
                "message": "Could not extract any text from the contract.",
            },
        )

    analysis = await ai_service.analyze_contract(payload, text)
    return success(analysis.model_dump(mode="json"), message="Contract analyzed.")


@router.post("/suggest-template")
async def suggest_template(
    payload: SuggestTemplateRequest, current: UserPublic = Depends(get_current_user)
):
    template = await ai_service.suggest_template(payload)
    return success({"template_markdown": template})
