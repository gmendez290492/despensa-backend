"""Lógica de negocio del módulo users (registro con Outbox y ciclo JWT)."""

from datetime import UTC, datetime
from uuid import UUID

import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.modules.users.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserNotFoundError,
)
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import TokenResponse, UserLoginRequest, UserRegisterRequest
from app.shared.events import EventEnvelope, UserRegisteredPayload
from app.shared.outbox import OutboxRepository


class UserService:
    """Casos de uso de registro, autenticación y perfil de usuarios."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.users = UserRepository(session)
        self.outbox = OutboxRepository(session)

    async def register_user(
        self,
        data: UserRegisterRequest,
        *,
        correlation_id: str = "",
    ) -> User:
        """Registra un usuario y encola user.registered.v1 en la misma transacción."""
        existing = await self.users.get_by_email(data.email)
        if existing is not None:
            raise EmailAlreadyExistsError("Ya existe una cuenta registrada con ese correo.")

        user = self.users.create(
            email=data.email,
            full_name=data.full_name,
            password_hash=hash_password(data.password),
            timezone=data.timezone,
            alert_days_before=data.alert_days_before,
        )

        try:
            await self.session.flush()
            payload = UserRegisteredPayload(
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                timezone=user.timezone,
            )
            event = EventEnvelope(
                event_type="user.registered.v1",
                correlation_id=correlation_id,
                payload=payload.model_dump(mode="json"),
            )
            self.outbox.enqueue(
                event=event,
                aggregate_type="user",
                aggregate_id=str(user.id),
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise EmailAlreadyExistsError(
                "Ya existe una cuenta registrada con ese correo.",
            ) from exc

        await self.session.refresh(user)
        return user

    async def authenticate_user(self, data: UserLoginRequest) -> TokenResponse:
        """Valida credenciales y emite par de tokens (Access + Refresh)."""
        user = await self.users.get_by_email(data.email)
        if (
            user is None
            or not verify_password(data.password, user.password_hash)
            or not user.is_active
        ):
            raise InvalidCredentialsError("Correo o contraseña incorrectos.")

        return await self._issue_tokens(user)

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        """Rota un refresh token válido y detecta reuso de tokens revocados."""
        try:
            claims = decode_token(
                token=refresh_token,
                secret_key=self.settings.jwt_secret_key,
                algorithm=self.settings.jwt_algorithm,
                expected_type="refresh",
            )
        except (jwt.PyJWTError, ValueError) as exc:
            raise InvalidTokenError("Refresh token inválido o expirado.") from exc

        record = await self.users.get_refresh_token_by_jti(claims.jti)
        if record is None:
            raise InvalidTokenError("Refresh token no reconocido.")

        if record.revoked_at is not None:
            await self.users.revoke_all_user_refresh_tokens(record.user_id)
            await self.session.commit()
            raise InvalidTokenError("Refresh token ya fue utilizado o revocado.")

        now = datetime.now(UTC)
        if record.expires_at <= now:
            raise InvalidTokenError("Refresh token expirado.")

        user = await self.users.get_by_id(claims.user_id)
        if user is None or not user.is_active:
            raise InvalidTokenError("Usuario inactivo o inexistente.")

        record.revoked_at = now
        return await self._issue_tokens(user)

    async def logout(self, refresh_token: str) -> None:
        """Revoca un refresh token activo (idempotente)."""
        try:
            claims = decode_token(
                token=refresh_token,
                secret_key=self.settings.jwt_secret_key,
                algorithm=self.settings.jwt_algorithm,
                expected_type="refresh",
            )
        except (jwt.PyJWTError, ValueError) as exc:
            raise InvalidTokenError("Refresh token inválido o expirado.") from exc

        record = await self.users.get_refresh_token_by_jti(claims.jti)
        if record is not None and record.revoked_at is None:
            record.revoked_at = datetime.now(UTC)
            await self.session.commit()

    async def get_active_user(self, user_id: UUID) -> User:
        """Obtiene un usuario activo por ID o lanza excepción de dominio."""
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("Usuario no encontrado.")
        if not user.is_active:
            raise InvalidCredentialsError("La cuenta de usuario está desactivada.")
        return user

    async def _issue_tokens(self, user: User) -> TokenResponse:
        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            secret_key=self.settings.jwt_secret_key,
            algorithm=self.settings.jwt_algorithm,
            expire_minutes=self.settings.access_token_expire_minutes,
        )
        refresh_token, jti, expires_at = create_refresh_token(
            user_id=user.id,
            email=user.email,
            secret_key=self.settings.jwt_secret_key,
            algorithm=self.settings.jwt_algorithm,
            expire_days=self.settings.refresh_token_expire_days,
        )
        self.users.add_refresh_token(
            user_id=user.id,
            token_jti=jti,
            expires_at=expires_at,
        )
        await self.session.commit()
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.settings.access_token_expire_minutes * 60,
        )
