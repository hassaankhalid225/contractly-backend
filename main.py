"""Contractly FastAPI application entry-point.

Run locally with:

    uvicorn main:app --reload
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import MongoDB
from app.middleware.cors import configure_cors
from app.middleware.error_handler import configure_exception_handlers
from app.routers import ai, auth, contracts, notifications, payments, users

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("contractly")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    logger.info("Starting %s (%s)", settings.app_name, settings.app_env)
    await MongoDB.connect()
    try:
        yield
    finally:
        await MongoDB.disconnect()
        logger.info("Stopped %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Contractly — your freelance contracts, always in control.",
    lifespan=lifespan,
    debug=settings.debug,
)

configure_cors(app)
configure_exception_handlers(app)

# Routes
prefix = settings.api_v1_prefix
app.include_router(auth.router, prefix=prefix)
app.include_router(users.router, prefix=prefix)
app.include_router(contracts.router, prefix=prefix)
app.include_router(payments.router, prefix=prefix)
app.include_router(ai.router, prefix=prefix)
app.include_router(notifications.router, prefix=prefix)


@app.get("/", tags=["Health"])
async def root():
    return {
        "success": True,
        "data": {
            "name": settings.app_name,
            "version": "1.0.0",
            "env": settings.app_env,
        },
        "message": "Contractly API is up.",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"success": True, "data": {"status": "ok"}, "message": None}
