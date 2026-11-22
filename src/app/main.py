"""Punto de entrada principal de la API FastAPI."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from typing import Annotated, cast

import structlog
from fastapi import Depends, FastAPI, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.core.database import create_db_engine, create_session_factory
from app.core.exceptions import register_exception_handlers
from app.core.health import (
    HealthCheckFn,
    LivenessResponse,
    ReadinessResponse,
    check_database,
    check_rabbitmq,
)
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware
from app.core.security import InMemoryRateLimiter
from app.modules.pantry.router import router as pantry_router
from app.modules.users.router import router as users_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Inicializa y libera recursos compartidos durante el ciclo de vida de la app."""
    settings = get_settings()
    configure_logging(environment=settings.environment, log_level=settings.log_level)

    engine = create_db_engine(settings.database_url)
    app.state.db_engine = engine
    app.state.db_session_factory = create_session_factory(engine)
    app.state.rate_limiter = InMemoryRateLimiter(
        max_attempts=settings.auth_rate_limit_max_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    logger.info("application_started", app_name=settings.app_name, environment=settings.environment)

    try:
        yield
    finally:
        await engine.dispose()
        logger.info("application_stopped")


def get_db_check(request: Request) -> HealthCheckFn:
    """Provee la función de chequeo de PostgreSQL."""
    engine = cast(AsyncEngine, request.app.state.db_engine)
    return partial(check_database, engine)


def get_rabbitmq_check(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthCheckFn:
    """Provee la función de chequeo de RabbitMQ."""
    return partial(check_rabbitmq, settings.rabbitmq_url)


def create_app() -> FastAPI:
    """Construye y configura la instancia de FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="API orientada a eventos para el control inteligente de despensa.",
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    app.include_router(users_router)
    app.include_router(pantry_router)

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        """Información básica del servicio y enlace a la documentación OpenAPI."""
        return {
            "service": settings.app_name,
            "version": "0.1.0",
            "docs": "/docs",
        }

    @app.get("/health/live", response_model=LivenessResponse, tags=["health"])
    async def health_live() -> LivenessResponse:
        """Liveness probe: confirma que el proceso Python está respondiendo."""
        return LivenessResponse()

    @app.get(
        "/health/ready",
        response_model=ReadinessResponse,
        responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
        tags=["health"],
    )
    async def health_ready(
        response: Response,
        db_check: Annotated[HealthCheckFn, Depends(get_db_check)],
        rabbitmq_check: Annotated[HealthCheckFn, Depends(get_rabbitmq_check)],
    ) -> ReadinessResponse:
        """Readiness probe: confirma conectividad real con PostgreSQL y RabbitMQ."""
        db_ok = await db_check()
        rabbitmq_ok = await rabbitmq_check()

        all_ok = db_ok and rabbitmq_ok
        if not all_ok:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return ReadinessResponse(
            status="ready" if all_ok else "degraded",
            checks={
                "postgres": "ok" if db_ok else "error",
                "rabbitmq": "ok" if rabbitmq_ok else "error",
            },
        )

    return app
