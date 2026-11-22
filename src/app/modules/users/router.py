"""Rutas HTTP (/api/v1/auth y /api/v1/users) del módulo users."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.modules.users.dependencies import (
    enforce_auth_rate_limit,
    get_current_user,
    get_user_service,
)
from app.modules.users.models import User
from app.modules.users.schemas import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.modules.users.service import UserService

router = APIRouter(prefix="/api/v1", tags=["users"])


@router.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def register(
    request: Request,
    payload: UserRegisterRequest,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Registra una cuenta nueva y emite el evento user.registered.v1."""
    correlation_id = getattr(request.state, "correlation_id", "")
    user = await service.register_user(payload, correlation_id=correlation_id)
    return UserResponse.model_validate(user)


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def login(
    payload: UserLoginRequest,
    service: Annotated[UserService, Depends(get_user_service)],
) -> TokenResponse:
    """Autentica al usuario y devuelve access y refresh tokens."""
    return await service.authenticate_user(payload)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshTokenRequest,
    service: Annotated[UserService, Depends(get_user_service)],
) -> TokenResponse:
    """Rota el par de tokens usando un refresh token vigente."""
    return await service.refresh_tokens(payload.refresh_token)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshTokenRequest,
    service: Annotated[UserService, Depends(get_user_service)],
) -> Response:
    """Revoca el refresh token indicado para cerrar sesión."""
    await service.logout(payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Retorna el perfil del usuario autenticado."""
    return UserResponse.model_validate(current_user)
