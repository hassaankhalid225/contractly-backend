"""Cloudinary file storage helpers (PDFs, signatures)."""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import Any, Dict

from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


def _ensure_configured() -> None:
    if not settings.has_cloudinary:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "CLOUDINARY_NOT_CONFIGURED",
                "message": "File storage is not configured on the server.",
            },
        )

    import cloudinary

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )


async def upload_pdf_bytes(data: bytes, filename: str, folder: str = "contractly/pdfs") -> str:
    """Upload PDF bytes to Cloudinary and return the secure URL."""
    _ensure_configured()
    import cloudinary.uploader

    def _sync_upload() -> Dict[str, Any]:
        return cloudinary.uploader.upload(
            io.BytesIO(data),
            resource_type="raw",
            folder=folder,
            public_id=filename.rsplit(".", 1)[0],
            overwrite=True,
            use_filename=True,
            unique_filename=True,
        )

    try:
        result = await asyncio.to_thread(_sync_upload)
    except Exception as exc:  # pragma: no cover - network errors
        logger.error("Cloudinary upload failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "UPLOAD_FAILED", "message": "Could not upload the file. Please try again."},
        )

    return str(result["secure_url"])


async def upload_signature_base64(b64: str, contract_id: str, folder: str = "contractly/signatures") -> str:
    """Decode a base64-encoded PNG (with or without data-URL prefix) and upload."""
    _ensure_configured()
    import cloudinary.uploader

    cleaned = b64.split(",", 1)[1] if "," in b64 and b64.strip().startswith("data:") else b64
    try:
        raw = base64.b64decode(cleaned, validate=True)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_SIGNATURE", "message": "Signature image is not valid base64 data."},
        )

    def _sync_upload() -> Dict[str, Any]:
        return cloudinary.uploader.upload(
            io.BytesIO(raw),
            resource_type="image",
            folder=folder,
            public_id=f"signature_{contract_id}",
            overwrite=True,
            format="png",
        )

    try:
        result = await asyncio.to_thread(_sync_upload)
    except Exception as exc:  # pragma: no cover
        logger.error("Cloudinary signature upload failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "UPLOAD_FAILED", "message": "Could not save your signature. Please try again."},
        )

    return str(result["secure_url"])


async def fetch_pdf_text(pdf_url: str, max_chars: int = 30000) -> str:
    """Fetch a remote PDF and extract its text. Returns the text (truncated)."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(pdf_url)
            resp.raise_for_status()
    except Exception as exc:
        logger.error("PDF fetch failed for %s: %s", pdf_url, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "PDF_FETCH_FAILED", "message": "Could not download the PDF for analysis."},
        )

    raw = resp.content

    # Try pypdf if available; otherwise return base64 as a fallback so the AI
    # can still attempt to answer (though that is not ideal).
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return raw.decode("utf-8", errors="ignore")[:max_chars]

    try:
        reader = PdfReader(io.BytesIO(raw))
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        text = "\n".join(text_parts).strip()
        if not text:
            return raw.decode("utf-8", errors="ignore")[:max_chars]
        return text[:max_chars]
    except Exception as exc:  # pragma: no cover
        logger.warning("PDF text extraction failed: %s", exc)
        return raw.decode("utf-8", errors="ignore")[:max_chars]
