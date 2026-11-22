"""Dependencias FastAPI para inyectar UserService, rate limiter y usuario actual."""

from typing import Annotated, cast

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.security import InMemoryRateLimiter, decode_token
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


def enforce_auth_rate_limit(request: Request) -> None:
    """Aplica rate limiting por IP en endpoints sensibles de autenticación."""
    limiter = cast(InMemoryRateLimiter, request.app.state.rate_limiter)
    client_host = request.client.host if request.client is not None else "unknown"
    limiter.check(f"{request.url.path}:{client_host}")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[UserService, Depends(get_user_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Valida el JWT Bearer de acceso y retorna el usuario autenticado."""
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

    return await service.get_active_user(claims.user_id)
