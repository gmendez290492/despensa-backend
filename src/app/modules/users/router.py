"""Rutas HTTP (/api/v1/auth y /api/v1/users) del módulo users."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.core.config import Settings, settings_dependency
from app.core.openapi import problem_responses
from app.core.rate_limit import RateLimiter
from app.modules.users.dependencies import (
    enforce_auth_rate_limit,
    enforce_email_rate_limit,
    enforce_refresh_rate_limit,
    enforce_register_rate_limit,
    get_current_user,
    get_rate_limiter,
    get_user_service,
)
from app.modules.users.exceptions import InvalidCredentialsError, InvalidTokenError
from app.modules.users.models import User
from app.modules.users.schemas import (
    MessageResponse,
    PasswordForgotRequest,
    PasswordResetRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.modules.users.service import UserService

router = APIRouter(prefix="/api/v1", tags=["users"])

ClientBinding = Annotated[
    str | None,
    Header(
        alias="X-Client-Binding",
        max_length=256,
        description=(
            "Valor opaco por sesión generado por el cliente (BFF). Si se envía en el login, "
            "se exige en cada refresh y habilita la ventana de gracia del refresh."
        ),
    ),
]

_GENERIC_FORGOT_REPLY = (
    "Si existe una cuenta con ese correo, recibirás un enlace para restablecer la contraseña."
)


@router.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_register_rate_limit)],
)
async def register(
    request: Request,
    payload: UserRegisterRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> UserResponse:
    """Registra una cuenta nueva y emite el evento user.registered.v1."""
    await enforce_email_rate_limit(
        limiter=limiter,
        settings=settings,
        scope="register",
        email=payload.email,
    )
    correlation_id = getattr(request.state, "correlation_id", "")
    user = await service.register_user(payload, correlation_id=correlation_id)
    return UserResponse.model_validate(user)


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_auth_rate_limit)],
    responses=problem_responses(InvalidCredentialsError),
)
async def login(
    payload: UserLoginRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    settings: Annotated[Settings, Depends(settings_dependency)],
    client_binding: ClientBinding = None,
) -> TokenResponse:
    """Autentica al usuario, abre una sesión y devuelve access y refresh tokens."""
    await enforce_email_rate_limit(
        limiter=limiter,
        settings=settings,
        scope="login",
        email=payload.email,
    )
    return await service.authenticate_user(payload, client_binding=client_binding)


@router.post(
    "/auth/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_refresh_rate_limit)],
    responses=problem_responses(InvalidTokenError),
)
async def refresh(
    payload: RefreshTokenRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    client_binding: ClientBinding = None,
) -> TokenResponse:
    """Rota el par de tokens usando un refresh token vigente."""
    return await service.refresh_tokens(payload.refresh_token, client_binding=client_binding)


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_refresh_rate_limit)],
    responses=problem_responses(InvalidTokenError),
)
async def logout(
    payload: RefreshTokenRequest,
    service: Annotated[UserService, Depends(get_user_service)],
) -> Response:
    """Cierra la sesión: revoca el refresh token y los access tokens de esa sesión."""
    await service.logout(payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/auth/password/forgot",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def forgot_password(
    request: Request,
    payload: PasswordForgotRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> MessageResponse:
    """Solicita el correo de recuperación. Responde igual exista o no la cuenta."""
    await enforce_email_rate_limit(
        limiter=limiter,
        settings=settings,
        scope="forgot",
        email=payload.email,
    )
    correlation_id = getattr(request.state, "correlation_id", "")
    await service.request_password_reset(payload.email, correlation_id=correlation_id)
    return MessageResponse(detail=_GENERIC_FORGOT_REPLY)


@router.post(
    "/auth/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def reset_password(
    payload: PasswordResetRequest,
    service: Annotated[UserService, Depends(get_user_service)],
) -> Response:
    """Restablece la contraseña con el token del correo y cierra todas las sesiones."""
    await service.reset_password(payload.token, payload.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/users/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Retorna el perfil del usuario autenticado."""
    return UserResponse.model_validate(current_user)
