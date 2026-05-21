"""Contract domain models."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class ContractStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class WorkType(str, Enum):
    WEB_DEV = "web_dev"
    DESIGN = "design"
    CONTENT = "content"
    VIDEO = "video"
    OTHER = "other"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ContractCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    client_name: str = Field(..., min_length=1, max_length=120)
    client_email: Optional[EmailStr] = None
    description: Optional[str] = Field(default=None, max_length=20000)
    value: float = Field(..., ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=4)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[ContractStatus] = ContractStatus.DRAFT
    work_type: Optional[WorkType] = None
    notes: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        return v.upper()


class ContractUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    client_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    client_email: Optional[EmailStr] = None
    description: Optional[str] = Field(default=None, max_length=20000)
    value: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=4)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[ContractStatus] = None
    work_type: Optional[WorkType] = None
    notes: Optional[str] = None
    ai_analysis: Optional[Dict[str, Any]] = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v


class SignContractRequest(BaseModel):
    signature_image_base64: str = Field(..., min_length=10)


class GenerateContractRequest(BaseModel):
    title: str
    client_name: str
    client_email: Optional[EmailStr] = None
    description: str
    value: float = Field(..., ge=0)
    currency: str = Field(default="USD")
    duration_days: int = Field(..., ge=1, le=3650)
    work_type: WorkType = WorkType.OTHER
    freelancer_name: Optional[str] = None
    start_date: Optional[datetime] = None


class AnalyzeContractRequest(BaseModel):
    contract_text: Optional[str] = None
    pdf_url: Optional[str] = None

    @field_validator("contract_text")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v


class SuggestTemplateRequest(BaseModel):
    work_type: WorkType


class RiskyClause(BaseModel):
    clause: str
    risk: str
    severity: RiskLevel


class ContractAnalysis(BaseModel):
    risk_level: RiskLevel
    summary: str
    risky_clauses: List[RiskyClause] = []
    missing_sections: List[str] = []
    recommendations: List[str] = []
    freelancer_protection_score: int = Field(default=5, ge=1, le=10)


class ContractPublic(BaseModel):
    id: str
    user_id: str
    title: str
    client_name: str
    client_email: Optional[str] = None
    description: Optional[str] = None
    value: float
    currency: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: ContractStatus
    work_type: Optional[WorkType] = None
    pdf_url: Optional[str] = None
    signature_url: Optional[str] = None
    signed_at: Optional[datetime] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ---- Helpers ---------------------------------------------------------------


def derive_status(doc: Dict[str, Any]) -> ContractStatus:
    """Auto-derive ``ContractStatus`` from end_date when applicable.

    Manual final states (completed/cancelled) are never overwritten.
    """
    raw_status = doc.get("status", ContractStatus.DRAFT.value)
    try:
        current = ContractStatus(raw_status)
    except ValueError:
        current = ContractStatus.DRAFT

    if current in (ContractStatus.COMPLETED, ContractStatus.CANCELLED, ContractStatus.DRAFT):
        return current

    end_date: Optional[datetime] = doc.get("end_date")
    if end_date is None:
        return current

    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if end_date < now:
        return ContractStatus.EXPIRED
    delta = end_date - now
    if delta.days <= 14:
        return ContractStatus.EXPIRING_SOON
    return ContractStatus.ACTIVE


def contract_doc_to_public(doc: Dict[str, Any]) -> ContractPublic:
    status = derive_status(doc)
    work_type_raw = doc.get("work_type")
    work_type = WorkType(work_type_raw) if work_type_raw else None
    return ContractPublic(
        id=str(doc["_id"]),
        user_id=str(doc["user_id"]),
        title=doc.get("title", ""),
        client_name=doc.get("client_name", ""),
        client_email=doc.get("client_email"),
        description=doc.get("description"),
        value=float(doc.get("value", 0.0)),
        currency=doc.get("currency", "USD"),
        start_date=doc.get("start_date"),
        end_date=doc.get("end_date"),
        status=status,
        work_type=work_type,
        pdf_url=doc.get("pdf_url"),
        signature_url=doc.get("signature_url"),
        signed_at=doc.get("signed_at"),
        ai_analysis=doc.get("ai_analysis"),
        notes=doc.get("notes"),
        created_at=doc.get("created_at", datetime.now(timezone.utc)),
        updated_at=doc.get("updated_at", datetime.now(timezone.utc)),
    )


class ContractStatsSummary(BaseModel):
    total: int
    active: int
    expiring: int
    expired: int
    draft: int
    completed: int
    total_value: float
    currency_breakdown: Dict[str, float] = {}
