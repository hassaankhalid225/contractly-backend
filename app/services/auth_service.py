"""Authentication helpers — Google ID-token verification, OTP issuance and verification,
refresh-token persistence."""
from __future__ import annotations

import logging
import random
import re
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from bson import ObjectId
from fastapi import HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
    JWTError,
)
from app.models.user import (
    AuthProvider,
    UserPublic,
    new_user_doc,
    user_doc_to_public,
)

logger = logging.getLogger(__name__)


# ---- Test bypass numbers (per spec) ----------------------------------------

TEST_PHONE_NUMBERS = {"+923001234567", "+923009876543"}
TEST_OTP = "123456"


# ---- Helpers ---------------------------------------------------------------


def _normalize_phone(phone: str) -> str:
    phone = phone.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        # assume already E.164-ish; accept but require digits
        if not re.fullmatch(r"\d{8,15}", phone):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_PHONE",
                    "message": "Phone number must be in international format (e.g. +14155551234).",
                },
            )
        phone = "+" + phone
    if not re.fullmatch(r"\+\d{8,15}", phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_PHONE",
                "message": "Phone number must be in international format (e.g. +14155551234).",
            },
        )
    return phone


async def _store_refresh_token(user_id: str, refresh_token: str, device_info: Optional[str]) -> None:
    db = get_db()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    await db["refresh_tokens"].insert_one(
        {
            "user_id": ObjectId(user_id),
            "token_hash": hash_token(refresh_token),
            "device_info": device_info,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def _build_token_pair(user_id: str, device_info: Optional[str]) -> Tuple[str, str]:
    access = create_access_token(subject=user_id)
    refresh = create_refresh_token(subject=user_id)
    await _store_refresh_token(user_id, refresh, device_info)
    return access, refresh


# ---- Google -----------------------------------------------------------------


async def login_with_google(google_id_token_value: str, device_info: Optional[str]) -> Tuple[str, str, UserPublic]:
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "GOOGLE_NOT_CONFIGURED",
                "message": "Google Sign-In is not configured on the server.",
            },
        )

    try:
        info = google_id_token.verify_oauth2_token(
            google_id_token_value,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError as exc:
        logger.warning("Invalid Google ID token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_GOOGLE_TOKEN", "message": "Invalid Google ID token."},
        )

    email: Optional[str] = info.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "GOOGLE_EMAIL_MISSING", "message": "Google account has no email."},
        )

    name = info.get("name") or info.get("given_name") or email.split("@")[0]
    photo_url = info.get("picture")

    db = get_db()
    user = await db["users"].find_one({"email": email})
    if user is None:
        doc = new_user_doc(
            provider=AuthProvider.GOOGLE,
            name=name,
            email=email,
            photo_url=photo_url,
        )
        result = await db["users"].insert_one(doc)
        doc["_id"] = result.inserted_id
        user = doc
    else:
        # Update photo / name if missing
        update: Dict[str, Any] = {}
        if photo_url and user.get("photo_url") != photo_url:
            update["photo_url"] = photo_url
        if name and not user.get("name"):
            update["name"] = name
        if update:
            await db["users"].update_one({"_id": user["_id"]}, {"$set": update})
            user.update(update)

    user_public = user_doc_to_public(user)
    access, refresh = await _build_token_pair(user_public.id, device_info)
    return access, refresh, user_public


# ---- Phone OTP --------------------------------------------------------------


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


async def send_phone_otp(phone: str) -> str:
    """Generate (or bypass) an OTP for ``phone`` and persist it. Returns the OTP
    only in dev mode — production callers should ignore the return value."""
    phone = _normalize_phone(phone)

    if phone in TEST_PHONE_NUMBERS:
        # No persistence needed; verification will compare against TEST_OTP.
        logger.info("[OTP] Test number %s — bypass active. Use OTP %s.", phone, TEST_OTP)
        return TEST_OTP

    otp = _generate_otp()
    db = get_db()
    await db["otps"].update_one(
        {"phone": phone},
        {"$set": {"phone": phone, "otp": otp, "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

    if settings.has_twilio:
        try:
            from twilio.rest import Client  # local import to keep startup lean

            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            client.messages.create(
                body=f"Your Contractly verification code is {otp}. It expires in 5 minutes.",
                from_=settings.twilio_from_number,
                to=phone,
            )
            logger.info("[OTP] Sent via Twilio to %s.", phone)
        except Exception as exc:  # pragma: no cover - network/runtime failures
            logger.error("[OTP] Twilio send failed for %s: %s", phone, exc)
            # Fall back to logging in dev; in prod this is an error.
            if settings.is_production:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "code": "OTP_DELIVERY_FAILED",
                        "message": "We couldn't send the OTP. Please try again.",
                    },
                )
            logger.info("[OTP] DEV fallback OTP for %s = %s", phone, otp)
    else:
        logger.info("[OTP] (DEV) phone=%s otp=%s", phone, otp)

    return otp


async def verify_phone_otp(phone: str, otp: str, device_info: Optional[str]) -> Tuple[str, str, UserPublic]:
    phone = _normalize_phone(phone)
    otp = otp.strip()

    is_test = phone in TEST_PHONE_NUMBERS
    if is_test:
        if otp != TEST_OTP:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_OTP", "message": "Invalid OTP. Please try again."},
            )
    else:
        db = get_db()
        record = await db["otps"].find_one({"phone": phone})
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "OTP_EXPIRED",
                    "message": "OTP has expired. Please request a new one.",
                },
            )
        if record.get("otp") != otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_OTP", "message": "Invalid OTP. Please try again."},
            )
        # Single-use OTP
        await db["otps"].delete_one({"_id": record["_id"]})

    db = get_db()
    user = await db["users"].find_one({"phone": phone})
    if user is None:
        doc = new_user_doc(provider=AuthProvider.PHONE, phone=phone)
        result = await db["users"].insert_one(doc)
        doc["_id"] = result.inserted_id
        user = doc

    user_public = user_doc_to_public(user)
    access, refresh = await _build_token_pair(user_public.id, device_info)
    return access, refresh, user_public


# ---- Refresh / logout -------------------------------------------------------


async def refresh_access_token(refresh_token_value: str) -> str:
    try:
        payload = decode_token(refresh_token_value)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Refresh token is invalid or expired."},
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN_TYPE", "message": "Refresh token required."},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Token has no subject."},
        )

    db = get_db()
    record = await db["refresh_tokens"].find_one({"token_hash": hash_token(refresh_token_value)})
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_REVOKED", "message": "Refresh token has been revoked."},
        )

    return create_access_token(subject=user_id)


async def revoke_refresh_token(refresh_token_value: str) -> None:
    db = get_db()
    await db["refresh_tokens"].delete_one({"token_hash": hash_token(refresh_token_value)})
