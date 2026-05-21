"""JWT token generation/verification and password hashing helpers."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---- Password hashing ------------------------------------------------------


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(password, hashed)
    except Exception:
        return False


# ---- JWT -------------------------------------------------------------------


def _create_token(data: Dict[str, Any], expires_delta: timedelta, token_type: str) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": token_type})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: str, extra: Dict[str, Any] | None = None) -> str:
    data: Dict[str, Any] = {"sub": subject}
    if extra:
        data.update(extra)
    return _create_token(
        data,
        timedelta(minutes=settings.access_token_expire_minutes),
        token_type="access",
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(
        {"sub": subject},
        timedelta(days=settings.refresh_token_expire_days),
        token_type="refresh",
    )


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT. Raises ``JWTError`` on failure."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


# ---- Hash helper for refresh-token storage ---------------------------------


def hash_token(token: str) -> str:
    """SHA-256 a refresh token before persisting (we never store raw tokens)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


__all__ = [
    "JWTError",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "hash_token",
    "verify_password",
]
