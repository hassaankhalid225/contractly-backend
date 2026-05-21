"""Auth token request/response models."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.user import UserPublic


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(..., min_length=10)


class PhoneSendOtpRequest(BaseModel):
    phone: str = Field(..., min_length=8, max_length=20)


class PhoneVerifyOtpRequest(BaseModel):
    phone: str = Field(..., min_length=8, max_length=20)
    otp: str = Field(..., min_length=4, max_length=10)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic


class AccessOnlyResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
