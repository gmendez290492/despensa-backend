"""Verificaciones de salud (liveness y readiness) para API y dependencias."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal

import aio_pika
import structlog
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger(__name__)

HealthCheckFn = Callable[[], Awaitable[bool]]


class LivenessResponse(BaseModel):
    """Respuesta del endpoint de vida del proceso."""

    status: Literal["alive"] = "alive"


class ReadinessResponse(BaseModel):
    """Respuesta del endpoint de disponibilidad de dependencias."""

    status: Literal["ready", "degraded"]
    checks: dict[str, Literal["ok", "error"]]


async def check_database(engine: AsyncEngine, timeout_seconds: float = 2.0) -> bool:
    """Ejecuta una consulta mínima (SELECT 1) para verificar PostgreSQL."""
    try:
        async with asyncio.timeout(timeout_seconds):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("health_check_failed", dependency="postgres", error=str(exc))
        return False


async def check_rabbitmq(rabbitmq_url: str, timeout_seconds: float = 2.0) -> bool:
    """Abre y cierra una conexión breve para verificar el broker RabbitMQ."""
    try:
        connection = await aio_pika.connect(rabbitmq_url, timeout=timeout_seconds)
        async with connection:
            return True
    except Exception as exc:
        logger.warning("health_check_failed", dependency="rabbitmq", error=str(exc))
        return False
