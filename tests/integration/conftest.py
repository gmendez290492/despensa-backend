"""Fixtures de integración con base de datos aislada (despensa_test)."""

from collections.abc import AsyncIterator

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.core.idempotency  # noqa: F401
import app.core.rate_limit  # noqa: F401
import app.modules.notifications.models  # noqa: F401
import app.modules.pantry.models  # noqa: F401
import app.modules.recipes.models  # noqa: F401
import app.modules.users.models  # noqa: F401
import app.shared.outbox  # noqa: F401
from app.core.config import Settings, get_settings, settings_dependency
from app.core.database import Base, create_db_engine, create_session_factory
from app.core.rate_limit import PostgresRateLimiter
from app.main import create_app


def _build_test_settings() -> Settings:
    base = get_settings()
    db_url = base.database_url
    if db_url.endswith("/despensa"):
        db_url = f"{db_url}_test"
    secret = (
        base.jwt_secret_key
        if len(base.jwt_secret_key) >= 32
        else "integration-test-secret-key-at-least-32-chars"
    )
    return base.model_copy(
        update={
            "database_url": db_url,
            "jwt_secret_key": secret,
            "auth_rate_limit_max_attempts": 5,
            "auth_rate_limit_window_seconds": 60,
            "register_rate_limit_max_attempts": 20,
            "register_rate_limit_window_seconds": 3600,
            "refresh_rate_limit_max_attempts": 30,
            "refresh_rate_limit_window_seconds": 60,
            "auth_email_rate_limit_max_attempts": 20,
            "auth_email_rate_limit_window_seconds": 900,
        },
    )


async def _ensure_test_database_exists(test_db_url: str) -> None:
    if not test_db_url.endswith("/despensa_test"):
        return
    admin_dsn = test_db_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "/despensa_test",
        "/postgres",
    )
    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = 'despensa_test'",
        )
        if not exists:
            await conn.execute("CREATE DATABASE despensa_test")
    finally:
        await conn.close()


@pytest.fixture
def test_settings() -> Settings:
    """Configuración aislada para pruebas de integración."""
    return _build_test_settings()


@pytest.fixture
async def db_engine(test_settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Crea tablas en despensa_test y limpia entre pruebas."""
    await _ensure_test_database_exists(test_settings.database_url)
    engine = create_db_engine(test_settings.database_url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "TRUNCATE TABLE idempotency_keys, rate_limit_buckets, password_reset_tokens, "
                "refresh_tokens, auth_sessions, users, outbox_events, processed_events, "
                "notifications, recipe_ingredients, recipes, stock_movements, food_batches, "
                "locations, pantry_members, pantries, products, categories, "
                "units_of_measure CASCADE",
            ),
        )
        await conn.execute(
            text(
                "INSERT INTO units_of_measure "
                "(code, name, dimension, base_conversion_factor) VALUES "
                "('g', 'Gramos', 'MASS', 1.0), "
                "('kg', 'Kilogramos', 'MASS', 1000.0), "
                "('ml', 'Mililitros', 'VOLUME', 1.0), "
                "('l', 'Litros', 'VOLUME', 1000.0), "
                "('pza', 'Piezas', 'COUNT', 1.0) "
                "ON CONFLICT (code) DO NOTHING;",
            ),
        )
        await conn.execute(
            text(
                "INSERT INTO categories (id, name, icon, created_at) VALUES "
                "('a0000000-0000-0000-0000-000000000001', 'Lácteos y Huevos', 'dairy', NOW()), "
                "('a0000000-0000-0000-0000-000000000002', 'Proteínas y Carnes', 'meat', NOW()) "
                "ON CONFLICT DO NOTHING;",
            ),
        )

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def db_session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Fábrica de sesiones para el motor de pruebas."""
    return create_session_factory(db_engine)


@pytest.fixture
def test_app(
    test_settings: Settings,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> FastAPI:
    """Instancia de FastAPI con estado y configuración apuntando a despensa_test."""
    app = create_app()
    app.dependency_overrides[settings_dependency] = lambda: test_settings
    app.state.db_engine = db_engine
    app.state.db_session_factory = db_session_factory
    # Las pruebas de integración usan el backend real (PostgreSQL) del rate limiter.
    app.state.rate_limiter = PostgresRateLimiter(db_session_factory)
    return app


@pytest.fixture
async def api_client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Cliente HTTP asíncrono contra la app FastAPI."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
