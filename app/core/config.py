"""Application configuration loaded from environment variables.

Uses ``pydantic-settings`` so values are validated and typed at startup.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    # App
    app_name: str = Field(default="Contractly")
    app_env: str = Field(default="development")
    api_v1_prefix: str = Field(default="/api/v1")
    debug: bool = Field(default=True)

    # MongoDB
    mongodb_url: str = Field(default="mongodb://localhost:27017")
    mongodb_db_name: str = Field(default="contractly")

    # Security
    secret_key: str = Field(default="change_me_change_me_change_me_change_me_change_me")
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=15)
    refresh_token_expire_days: int = Field(default=30)

    # Google OAuth
    google_client_id: str = Field(default="")

    # Anthropic
    anthropic_api_key: str = Field(default="")
    anthropic_model: str = Field(default="claude-3-5-sonnet-latest")

    # Cloudinary
    cloudinary_cloud_name: str = Field(default="")
    cloudinary_api_key: str = Field(default="")
    cloudinary_api_secret: str = Field(default="")

    # Twilio (optional)
    twilio_account_sid: str = Field(default="")
    twilio_auth_token: str = Field(default="")
    twilio_from_number: str = Field(default="")

    # CORS
    cors_origins: str = Field(default="*")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Derived helpers ----------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cors_origins_list(self) -> List[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_twilio(self) -> bool:
        return bool(
            self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number
        )

    @property
    def has_cloudinary(self) -> bool:
        return bool(
            self.cloudinary_cloud_name and self.cloudinary_api_key and self.cloudinary_api_secret
        )

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    @field_validator("secret_key")
    @classmethod
    def _validate_secret_key(cls, v: str) -> str:
        if len(v) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters long")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance — call wherever config is needed."""
    return Settings()


settings = get_settings()
