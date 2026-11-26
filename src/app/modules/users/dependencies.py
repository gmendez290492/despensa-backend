"""Dependencias FastAPI para inyectar UserService, rate limiting y usuario actual."""

from typing import Annotated, cast

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.rate_limit import RateLimiter, RateLimitPolicy, hash_identifier
from app.core.security import decode_token
from app.modules.users.exceptions import InvalidTokenError
from app.modules.users.models import User
from app.modules.users.service import UserService

bearer_scheme = HTTPBearer(auto_error=False)


def get_user_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserService:
    """Inyecta el servicio de usuarios para la petición actual."""
    return UserService(session=session, settings=settings)


def get_rate_limiter(request: Request) -> RateLimiter:
    """Retorna el rate limiter compartido configurado en el lifespan."""
    return cast(RateLimiter, request.app.state.rate_limiter)


def client_ip(request: Request) -> str:
    """IP del cliente. Detrás de un proxy, uvicorn la resuelve desde X-Forwarded-For
    únicamente si el proxy está en FORWARDED_ALLOW_IPS (ver README)."""
    return request.client.host if request.client is not None else "unknown"


async def enforce_auth_rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> None:
    """Rate limit por IP y ruta en login, forgot-password y reset-password."""
    policy = RateLimitPolicy(
        name="auth_ip",
        max_attempts=settings.auth_rate_limit_max_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    await limiter.check(f"{request.url.path}:{client_ip(request)}", policy)


async def enforce_register_rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> None:
    """Rate limit estricto por IP en el registro (mitiga la enumeración vía 409)."""
    policy = RateLimitPolicy(
        name="register_ip",
        max_attempts=settings.register_rate_limit_max_attempts,
        window_seconds=settings.register_rate_limit_window_seconds,
    )
    await limiter.check(client_ip(request), policy)


async def enforce_email_rate_limit(
    *,
    limiter: RateLimiter,
    settings: Settings,
    scope: str,
    email: str,
) -> None:
    """Rate limit por email (seudonimizado con SHA-256) para un caso de uso concreto."""
    policy = RateLimitPolicy(
        name="auth_email",
        max_attempts=settings.auth_email_rate_limit_max_attempts,
        window_seconds=settings.auth_email_rate_limit_window_seconds,
    )
    await limiter.check(f"{scope}:{hash_identifier(email)}", policy)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[UserService, Depends(get_user_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Valida el JWT Bearer de acceso, que su sesión siga activa, y retorna el usuario."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise InvalidTokenError("Se requiere token Bearer de autorización.")

    try:
        claims = decode_token(
            token=credentials.credentials,
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            expected_type="access",
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError("Access token inválido o expirado.") from exc

    if claims.session_id is None:  # decode_token ya exige sid; defensa adicional
        raise InvalidTokenError("Access token sin sesión asociada.")
    return await service.get_active_user_for_session(claims.user_id, claims.session_id)
