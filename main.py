"""FastAPI application entrypoint.

Wires together routers, exception handlers, logging, and lifecycle events.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.leads import router as leads_router
from app.api.routes.webhooks import router as webhooks_router
from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info(
        "app_startup",
        app_env=settings.app_env,
        llm_provider=settings.llm_provider_name,
        log_level=settings.log_level,
    )
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("app_shutdown")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    app = FastAPI(
        title="Zizzet AI Lead Recovery Engine",
        description=(
            "A backend service that analyzes inactive / high-intent leads with "
            "an LLM and produces lead scores, priority, intent, conversation "
            "stage, summaries, next best actions, and personalized follow-up "
            "messages. Multi-tenant, idempotent webhooks, structured output "
            "validation, and opt-out handling.\n\n"
            "All requests require the `X-Tenant-ID` header."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(leads_router)
    app.include_router(webhooks_router)
    return app


app = create_app()
