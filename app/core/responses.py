"""Standard success/error response envelope helpers."""
from __future__ import annotations

from typing import Any, Optional


def success(data: Any = None, message: Optional[str] = None) -> dict:
    return {"success": True, "data": data, "message": message}


def error(code: str, message: str, details: Any = None) -> dict:
    return {
        "success": False,
        "error": {"code": code, "message": message, "details": details},
    }
