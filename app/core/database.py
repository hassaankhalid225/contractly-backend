"""Async MongoDB connection using Motor.

Provides a singleton ``MongoDB`` instance plus a ``get_db()`` accessor that
returns the active database. Indexes for TTLs and uniqueness are created
on application startup.
"""
from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.core.config import settings

logger = logging.getLogger(__name__)


class MongoDB:
    """Lightweight wrapper around the Motor client."""

    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None

    @classmethod
    async def connect(cls) -> None:
        if cls.client is not None:
            return
        cls.client = AsyncIOMotorClient(settings.mongodb_url, uuidRepresentation="standard")
        cls.db = cls.client[settings.mongodb_db_name]
        # Verify connection
        await cls.client.admin.command("ping")
        await cls._create_indexes()
        logger.info("MongoDB connected: db=%s", settings.mongodb_db_name)

    @classmethod
    async def disconnect(cls) -> None:
        if cls.client is not None:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("MongoDB disconnected")

    @classmethod
    async def _create_indexes(cls) -> None:
        assert cls.db is not None

        # users: unique on email (when present) and on phone (when present)
        await cls.db["users"].create_index([("email", ASCENDING)], sparse=True, unique=True)
        await cls.db["users"].create_index([("phone", ASCENDING)], sparse=True, unique=True)

        # contracts: queries by user, status, and recency
        await cls.db["contracts"].create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        await cls.db["contracts"].create_index([("user_id", ASCENDING), ("status", ASCENDING)])
        await cls.db["contracts"].create_index([("user_id", ASCENDING), ("end_date", ASCENDING)])

        # payments: queries by contract & user
        await cls.db["payments"].create_index([("contract_id", ASCENDING)])
        await cls.db["payments"].create_index([("user_id", ASCENDING), ("status", ASCENDING)])
        await cls.db["payments"].create_index([("user_id", ASCENDING), ("due_date", ASCENDING)])

        # otps: TTL on created_at (5 minutes), one active OTP per phone
        await cls.db["otps"].create_index([("phone", ASCENDING)], unique=True)
        await cls.db["otps"].create_index("created_at", expireAfterSeconds=300)

        # refresh tokens: TTL on expires_at, query by user_id
        await cls.db["refresh_tokens"].create_index([("user_id", ASCENDING)])
        await cls.db["refresh_tokens"].create_index([("token_hash", ASCENDING)], unique=True)
        await cls.db["refresh_tokens"].create_index("expires_at", expireAfterSeconds=0)


def get_db() -> AsyncIOMotorDatabase:
    """Return the active database. Raises if connection has not been initialized."""
    if MongoDB.db is None:
        raise RuntimeError("MongoDB is not connected. Call MongoDB.connect() on startup.")
    return MongoDB.db
