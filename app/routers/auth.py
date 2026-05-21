"""Authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Header, Request

from app.core.responses import success
from app.models.token import (
    AuthResponse,
    GoogleLoginRequest,
    LogoutRequest,
    PhoneSendOtpRequest,
    PhoneVerifyOtpRequest,
    RefreshTokenRequest,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


def _device_info(user_agent: str | None, request: Request) -> str:
    parts = [user_agent or "unknown-agent"]
    client = request.client.host if request.client else "unknown-ip"
    parts.append(client)
    return " | ".join(parts)


@router.post("/google")
async def login_with_google(
    payload: GoogleLoginRequest,
    request: Request,
    user_agent: str | None = Header(default=None, alias="User-Agent"),
):
    access, refresh, user = await auth_service.login_with_google(
        payload.id_token, _device_info(user_agent, request)
    )
    response = AuthResponse(access_token=access, refresh_token=refresh, user=user)
    return success(response.model_dump(), message="Signed in with Google.")


@router.post("/phone/send-otp")
async def send_phone_otp(payload: PhoneSendOtpRequest):
    await auth_service.send_phone_otp(payload.phone)
    return success({"phone": payload.phone}, message="OTP sent.")


@router.post("/phone/verify")
async def verify_phone_otp(
    payload: PhoneVerifyOtpRequest,
    request: Request,
    user_agent: str | None = Header(default=None, alias="User-Agent"),
):
    access, refresh, user = await auth_service.verify_phone_otp(
        payload.phone, payload.otp, _device_info(user_agent, request)
    )
    response = AuthResponse(access_token=access, refresh_token=refresh, user=user)
    return success(response.model_dump(), message="Phone verified.")


@router.post("/refresh")
async def refresh_token(payload: RefreshTokenRequest):
    access = await auth_service.refresh_access_token(payload.refresh_token)
    return success({"access_token": access, "token_type": "bearer"}, message="Token refreshed.")


@router.post("/logout")
async def logout(payload: LogoutRequest):
    await auth_service.revoke_refresh_token(payload.refresh_token)
    return success(None, message="Logged out.")
