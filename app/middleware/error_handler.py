"""Global exception handlers — produces the unified error envelope."""
from __future__ import annotations

import logging
import traceback
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


def _envelope(code: str, message: str, details: Any = None, http_status: int = 400) -> JSONResponse:
    body: Dict[str, Any] = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }
    return JSONResponse(status_code=http_status, content=body)


def configure_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http_exc_handler(request: Request, exc: HTTPException):  # noqa: ARG001
        detail = exc.detail
        if isinstance(detail, dict) and "message" in detail:
            return _envelope(
                code=detail.get("code", f"HTTP_{exc.status_code}"),
                message=detail.get("message", "Request failed."),
                details=detail.get("details"),
                http_status=exc.status_code,
            )
        return _envelope(
            code=f"HTTP_{exc.status_code}",
            message=str(detail) if detail else "Request failed.",
            http_status=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):  # noqa: ARG001
        return _envelope(
            code="VALIDATION_ERROR",
            message="One or more request fields are invalid.",
            details=exc.errors(),
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):  # noqa: ARG001
        logger.exception("Unhandled exception: %s", exc)
        details = None
        if not settings.is_production and settings.debug:
            details = {
                "type": type(exc).__name__,
                "trace": traceback.format_exc().splitlines()[-5:],
            }
        return _envelope(
            code="INTERNAL_SERVER_ERROR",
            message="Something went wrong. Please try again.",
            details=details,
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
