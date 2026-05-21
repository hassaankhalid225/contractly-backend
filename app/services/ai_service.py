"""Anthropic-backed AI services: contract generation, analysis, templates.

Falls back to deterministic markdown if no Anthropic API key is configured so
that the app always functions in local development without an API key.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from app.core.config import settings
from app.models.contract import (
    AnalyzeContractRequest,
    ContractAnalysis,
    GenerateContractRequest,
    RiskLevel,
    RiskyClause,
    SuggestTemplateRequest,
    WorkType,
)

logger = logging.getLogger(__name__)


GENERATE_PROMPT = """\
You are a professional legal contract drafter specializing in freelance agreements.

Generate a complete, professional freelance contract based on:
- Title: {title}
- Freelancer Name: {freelancer_name}
- Client Name: {client_name}
- Client Email: {client_email}
- Work Type: {work_type}
- Project Description: {description}
- Contract Value: {currency} {value}
- Duration: {duration_days} days
- Start Date: {start_date}
- End Date: {end_date}

Generate a complete contract with these sections:
1. Parties Involved
2. Scope of Work
3. Deliverables
4. Payment Terms
5. Timeline & Milestones
6. Revisions Policy
7. Intellectual Property Rights
8. Confidentiality Clause
9. Termination Clause
10. Dispute Resolution
11. Signatures Section

Format as clean markdown. Be specific and professional. Protect both parties fairly.
Return ONLY the contract markdown, with no preamble or commentary."""


ANALYZE_PROMPT = """\
You are a legal expert reviewing a freelance contract for potential risks.

Contract Text:
{contract_text}

Analyze this contract and respond in valid JSON only — no commentary, no markdown fences:
{{
  "risk_level": "low|medium|high",
  "summary": "2-3 sentence plain English summary of what this contract says",
  "risky_clauses": [
    {{"clause": "exact text of risky clause", "risk": "explanation of why this is risky", "severity": "low|medium|high"}}
  ],
  "missing_sections": ["list of important sections not present"],
  "recommendations": ["actionable recommendation 1", "recommendation 2"],
  "freelancer_protection_score": 7
}}"""


TEMPLATE_PROMPT = """\
You are a freelance contract specialist. Produce a clean, ready-to-fill markdown
contract template for a {work_type_label} project. Include placeholders in
square brackets such as [CLIENT_NAME], [PROJECT_DESCRIPTION], [VALUE],
[CURRENCY], [START_DATE], [END_DATE].

Cover these sections (in order):
1. Parties Involved
2. Scope of Work
3. Deliverables
4. Payment Terms
5. Timeline & Milestones
6. Revisions Policy
7. Intellectual Property Rights
8. Confidentiality Clause
9. Termination Clause
10. Dispute Resolution
11. Signatures Section

Return ONLY the markdown template."""


# ---- Internal Anthropic helper ---------------------------------------------


async def _anthropic_complete(prompt: str, *, max_tokens: int = 3000, system: Optional[str] = None) -> str:
    """Call Claude. Raises HTTPException on failure."""
    if not settings.has_anthropic:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "AI_NOT_CONFIGURED",
                "message": "AI features are not configured on the server.",
            },
        )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = await _run_in_thread(
            lambda: client.messages.create(
                model=settings.anthropic_model,
                max_tokens=max_tokens,
                system=system or "You are a helpful assistant.",
                messages=[{"role": "user", "content": prompt}],
            )
        )
        if not message.content:
            return ""
        chunks = [getattr(b, "text", "") for b in message.content if getattr(b, "type", "") == "text"]
        return "".join(chunks).strip()
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - network/runtime
        logger.exception("Anthropic call failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "AI_CALL_FAILED", "message": f"AI service error: {exc}"},
        )


async def _run_in_thread(fn):
    import asyncio

    return await asyncio.to_thread(fn)


# ---- Generation -------------------------------------------------------------


def _fallback_contract(req: GenerateContractRequest) -> str:
    start = req.start_date or datetime.now(timezone.utc)
    end = start + timedelta(days=req.duration_days)
    freelancer = req.freelancer_name or "[FREELANCER_NAME]"
    return f"""# {req.title}

## 1. Parties Involved
This Freelance Services Agreement (the "Agreement") is entered into as of \
{start.strftime('%B %d, %Y')} between **{freelancer}** ("Freelancer") and \
**{req.client_name}** ("Client", contact: {req.client_email or 'N/A'}).

## 2. Scope of Work
{req.description}

The work is categorised as a **{req.work_type.value.replace('_', ' ').title()}** engagement.

## 3. Deliverables
The Freelancer will provide all deliverables described above, in formats agreed in writing.

## 4. Payment Terms
- Total Contract Value: **{req.currency} {req.value:,.2f}**
- Payment Schedule: 50% upfront, 50% on final delivery (unless otherwise agreed).
- Late payments accrue interest at 1.5% per month after 14 days.

## 5. Timeline & Milestones
- Start Date: {start.strftime('%B %d, %Y')}
- End Date: {end.strftime('%B %d, %Y')}
- Duration: {req.duration_days} day(s)

## 6. Revisions Policy
The Freelancer will provide up to two (2) rounds of revisions per deliverable.
Additional revisions are billed at the Freelancer's standard hourly rate.

## 7. Intellectual Property Rights
Upon receipt of full payment, the Freelancer assigns to the Client all rights to
final deliverables. The Freelancer retains the right to display non-confidential
work in their portfolio.

## 8. Confidentiality Clause
Both parties agree to keep all non-public information shared during the
engagement strictly confidential, indefinitely beyond the term of this Agreement.

## 9. Termination Clause
Either party may terminate this Agreement with seven (7) days' written notice.
The Client shall pay for all work completed up to the termination date.

## 10. Dispute Resolution
Any disputes arising from this Agreement will first be resolved through good-faith
negotiation, then mediation, and finally binding arbitration if required.

## 11. Signatures
**Freelancer:** {freelancer}            Date: ____________________

**Client:** {req.client_name}           Date: ____________________
"""


async def generate_contract(req: GenerateContractRequest) -> str:
    if not settings.has_anthropic:
        logger.info("[AI] Falling back to local generator (no API key configured).")
        return _fallback_contract(req)

    start = req.start_date or datetime.now(timezone.utc)
    end = start + timedelta(days=req.duration_days)
    prompt = GENERATE_PROMPT.format(
        title=req.title,
        freelancer_name=req.freelancer_name or "[FREELANCER_NAME]",
        client_name=req.client_name,
        client_email=req.client_email or "N/A",
        work_type=req.work_type.value.replace("_", " ").title(),
        description=req.description,
        currency=req.currency,
        value=f"{req.value:,.2f}",
        duration_days=req.duration_days,
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
    )
    text = await _anthropic_complete(
        prompt,
        max_tokens=3500,
        system="You write precise, professional, fair freelance contracts in markdown.",
    )
    return text or _fallback_contract(req)


# ---- Analysis ---------------------------------------------------------------


_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def _parse_analysis_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if match:
            return json.loads(match.group(0))
        raise


def _fallback_analysis(contract_text: str) -> ContractAnalysis:
    lower = contract_text.lower()
    risky: list[RiskyClause] = []

    if "unlimited revisions" in lower:
        risky.append(
            RiskyClause(
                clause="unlimited revisions",
                risk="Unlimited revisions can cause endless scope creep with no extra compensation.",
                severity=RiskLevel.HIGH,
            )
        )
    if "no kill fee" in lower or ("termination" in lower and "no compensation" in lower):
        risky.append(
            RiskyClause(
                clause="termination without compensation",
                risk="Termination clause does not guarantee payment for work already completed.",
                severity=RiskLevel.HIGH,
            )
        )
    if "work for hire" in lower:
        risky.append(
            RiskyClause(
                clause="work for hire",
                risk="All IP transfers immediately to the client even before payment is made.",
                severity=RiskLevel.MEDIUM,
            )
        )
    if "non-compete" in lower or "noncompete" in lower:
        risky.append(
            RiskyClause(
                clause="non-compete",
                risk="A non-compete clause could limit your ability to work with similar clients.",
                severity=RiskLevel.MEDIUM,
            )
        )

    missing = []
    for term, label in [
        ("payment", "Payment Terms"),
        ("intellectual", "Intellectual Property Rights"),
        ("termination", "Termination Clause"),
        ("confidential", "Confidentiality Clause"),
        ("dispute", "Dispute Resolution"),
    ]:
        if term not in lower:
            missing.append(label)

    risk_level = RiskLevel.LOW
    if any(c.severity == RiskLevel.HIGH for c in risky) or len(missing) >= 3:
        risk_level = RiskLevel.HIGH
    elif risky or missing:
        risk_level = RiskLevel.MEDIUM

    score = 9 - (3 if risk_level == RiskLevel.HIGH else 1 if risk_level == RiskLevel.MEDIUM else 0)
    score = max(1, min(10, score))

    summary = (
        "This contract was analyzed locally without an AI service. "
        "It outlines the parties, scope, and terms for a freelance engagement. "
        "Review the highlighted clauses and missing sections before signing."
    )

    recommendations: list[str] = []
    if missing:
        recommendations.append(f"Add the following sections: {', '.join(missing)}.")
    if not risky:
        recommendations.append("Confirm payment milestones are clearly tied to deliverables.")
    recommendations.append("Have the contract reviewed by a qualified attorney before signing.")

    return ContractAnalysis(
        risk_level=risk_level,
        summary=summary,
        risky_clauses=risky,
        missing_sections=missing,
        recommendations=recommendations,
        freelancer_protection_score=score,
    )


async def analyze_contract(req: AnalyzeContractRequest, contract_text_resolved: str) -> ContractAnalysis:
    if not settings.has_anthropic:
        logger.info("[AI] Falling back to heuristic analyzer (no API key configured).")
        return _fallback_analysis(contract_text_resolved)

    prompt = ANALYZE_PROMPT.format(contract_text=contract_text_resolved[:20000])
    text = await _anthropic_complete(
        prompt,
        max_tokens=2000,
        system="You output strictly valid JSON. No markdown fences, no commentary.",
    )
    try:
        data = _parse_analysis_json(text)
    except Exception as exc:
        logger.error("Failed to parse AI analysis JSON: %s | text=%s", exc, text[:300])
        return _fallback_analysis(contract_text_resolved)

    try:
        clauses = [
            RiskyClause(
                clause=str(c.get("clause", "")),
                risk=str(c.get("risk", "")),
                severity=RiskLevel(str(c.get("severity", "low")).lower()),
            )
            for c in (data.get("risky_clauses") or [])
            if c.get("clause")
        ]
        return ContractAnalysis(
            risk_level=RiskLevel(str(data.get("risk_level", "low")).lower()),
            summary=str(data.get("summary", "")),
            risky_clauses=clauses,
            missing_sections=[str(s) for s in (data.get("missing_sections") or [])],
            recommendations=[str(r) for r in (data.get("recommendations") or [])],
            freelancer_protection_score=int(data.get("freelancer_protection_score", 5)),
        )
    except Exception as exc:
        logger.error("Failed to coerce AI analysis fields: %s", exc)
        return _fallback_analysis(contract_text_resolved)


# ---- Template suggestion ----------------------------------------------------


_TEMPLATE_FALLBACK: Dict[WorkType, str] = {
    WorkType.WEB_DEV: "web development project",
    WorkType.DESIGN: "graphic & UI design project",
    WorkType.CONTENT: "content writing project",
    WorkType.VIDEO: "video editing & production project",
    WorkType.OTHER: "freelance services project",
}


def _fallback_template(work_type: WorkType) -> str:
    label = _TEMPLATE_FALLBACK[work_type]
    return f"""# Freelance {label.title()} Agreement

## 1. Parties Involved
This Agreement is between **[FREELANCER_NAME]** and **[CLIENT_NAME]**, dated [START_DATE].

## 2. Scope of Work
[PROJECT_DESCRIPTION]

## 3. Deliverables
- [DELIVERABLE_1]
- [DELIVERABLE_2]
- [DELIVERABLE_3]

## 4. Payment Terms
Total: **[CURRENCY] [VALUE]**, paid as 50% upfront and 50% on final delivery.

## 5. Timeline & Milestones
- Start: [START_DATE]
- End: [END_DATE]

## 6. Revisions Policy
Two rounds of revisions per deliverable. Extra rounds billed at the standard hourly rate.

## 7. Intellectual Property Rights
All rights transfer to the Client upon full payment.

## 8. Confidentiality Clause
Both parties keep non-public information confidential indefinitely.

## 9. Termination Clause
Either party may terminate with 7 days' written notice; Client pays for completed work.

## 10. Dispute Resolution
Negotiation, then mediation, then binding arbitration.

## 11. Signatures
**Freelancer:** [FREELANCER_NAME]    Date: ______________
**Client:** [CLIENT_NAME]            Date: ______________
"""


async def suggest_template(req: SuggestTemplateRequest) -> str:
    if not settings.has_anthropic:
        return _fallback_template(req.work_type)
    prompt = TEMPLATE_PROMPT.format(work_type_label=_TEMPLATE_FALLBACK[req.work_type])
    text = await _anthropic_complete(
        prompt,
        max_tokens=2500,
        system="You write clean, fair, ready-to-fill freelance contract templates in markdown.",
    )
    return text or _fallback_template(req.work_type)
