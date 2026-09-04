"""PAYSCAPE-X FastAPI application.

Run with:  uvicorn app.main:app --reload
"""

import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    """Application factory — importable and testable."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        description=(
            "PAYSCAPE-X backend — from payment success to business outcome. "
            "Part 1: application foundation, health API and database schema."
        ),
        version=settings.app_version,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router)
    # Root-level liveness endpoint (unversioned convenience path).
    app.include_router(health_router)

    # Production warm-up: pre-compute the deterministic compound-failure
    # dataset scan in the background so the first /failures page load is
    # fast. Best-effort — a cold cache simply recomputes on first request.
    if settings.app_env == "production":
        from app.services import failures_service

        threading.Thread(
            target=failures_service.warm_failures_cache,
            name="failures-cache-warm",
            daemon=True,
        ).start()

    return app


app = create_app()