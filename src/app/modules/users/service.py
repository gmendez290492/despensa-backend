"""Lógica de negocio del módulo users (registro con Outbox, sesiones JWT y reset)."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import cache
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
    reissue_refresh_token,
    verify_password,
)
from app.modules.users.exceptions import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidPasswordResetTokenError,
    InvalidTokenError,
    UserNotFoundError,
)
from app.modules.users.models import AuthSession, RefreshToken, User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import TokenResponse, UserLoginRequest, UserRegisterRequest
from app.shared.events import EventEnvelope, PasswordResetRequestedPayload, UserRegisteredPayload
from app.shared.outbox import OutboxRepository

PASSWORD_RESET_REQUESTED_EVENT = "user.password_reset_requested.v1"  # noqa: S105  # nosec B105


@cache
def _dummy_password_hash() -> str:
    """Hash Argon2 de referencia para igualar el tiempo del login con usuario inexistente."""
    return hash_password(secrets.token_urlsafe(16))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_reset_token(raw_token: str) -> str:
    """Hash con el que se persiste y se busca un token de recuperación."""
    return _sha256(raw_token)


def generate_password_reset_token() -> tuple[str, str]:
    """Genera un token de reset aleatorio (256 bits) y su hash para persistir."""
    raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_reset_token(raw_token)


class UserService:
    """Casos de uso de registro, autenticación, sesiones y recuperación de contraseña."""

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
        """Registra un usuario y encola user.registered.v1 en la misma transacción.

        Mantiene 409 para correos duplicados (decisión del issue #9): la enumeración se
        mitiga con rate limit estricto por IP y por email en el router.
        """
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

    # --- Login, refresh y logout ---------------------------------------------------------

    async def authenticate_user(
        self,
        data: UserLoginRequest,
        *,
        client_binding: str | None = None,
    ) -> TokenResponse:
        """Valida credenciales, abre una sesión y emite el par de tokens."""
        user = await self.users.get_by_email(data.email)
        if user is None:
            # Igualar el coste de Argon2 para no revelar por tiempo si el correo existe.
            verify_password(data.password, _dummy_password_hash())
            raise InvalidCredentialsError("Correo o contraseña incorrectos.")
        if not verify_password(data.password, user.password_hash) or not user.is_active:
            raise InvalidCredentialsError("Correo o contraseña incorrectos.")

        auth_session = self.users.create_auth_session(
            user_id=user.id,
            client_binding_hash=_sha256(client_binding) if client_binding else None,
        )
        await self.session.flush()
        return await self._issue_tokens(user, auth_session.id)

    async def refresh_tokens(
        self,
        refresh_token: str,
        *,
        client_binding: str | None = None,
    ) -> TokenResponse:
        """Rota un refresh token válido, con ventana de gracia y detección de reuso.

        - La fila del refresh se bloquea (FOR UPDATE): refresh concurrentes se serializan.
        - Si la sesión tiene X-Client-Binding, la cabecera debe coincidir siempre.
        - Un refresh ya rotado, presentado dentro de la ventana de gracia y con binding
          válido, devuelve el mismo refresh sucesor (más un access token nuevo).
        - Cualquier otro reuso revoca la sesión completa (familia de tokens).
        """
        try:
            claims = decode_token(
                token=refresh_token,
                secret_key=self.settings.jwt_secret_key,
                algorithm=self.settings.jwt_algorithm,
                expected_type="refresh",
            )
        except (jwt.PyJWTError, ValueError) as exc:
            raise InvalidTokenError("Refresh token inválido o expirado.") from exc

        record = await self.users.get_refresh_token_by_jti(claims.jti, for_update=True)
        if record is None:
            raise InvalidTokenError("Refresh token no reconocido.")

        auth_session = await self.users.get_auth_session(record.session_id)
        if auth_session is None or auth_session.revoked_at is not None:
            raise InvalidTokenError("La sesión fue cerrada o revocada.")

        if not self._binding_matches(auth_session, client_binding):
            raise InvalidTokenError("Refresh token no válido para este cliente.")

        now = datetime.now(UTC)
        if record.revoked_at is not None:
            if self._within_grace_window(record, auth_session, now):
                successor = await self._grace_successor(record)
                if successor is not None:
                    user = await self._require_active_user(record.user_id)
                    tokens = self._replay_tokens(user, successor)
                    await self.session.commit()  # libera el bloqueo FOR UPDATE
                    return tokens
            await self.users.revoke_auth_session(auth_session.id, reason="refresh_reuse")
            await self.session.commit()
            raise InvalidTokenError("Refresh token ya fue utilizado o revocado.")

        if record.expires_at <= now:
            raise InvalidTokenError("Refresh token expirado.")

        user = await self._require_active_user(record.user_id)
        tokens, successor_jti = self._issue_tokens_uncommitted(user, auth_session.id)
        record.revoked_at = now
        record.replaced_by_jti = successor_jti
        await self.session.commit()
        return tokens

    async def logout(self, refresh_token: str) -> None:
        """Revoca la sesión del refresh token: invalida refresh y access tokens (idempotente)."""
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
        if record is not None:
            await self.users.revoke_auth_session(record.session_id, reason="logout")
            await self.session.commit()

    async def get_active_user(self, user_id: UUID) -> User:
        """Obtiene un usuario activo por ID o lanza excepción de dominio."""
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("Usuario no encontrado.")
        if not user.is_active:
            raise InvalidCredentialsError("La cuenta de usuario está desactivada.")
        return user

    async def get_active_user_for_session(self, user_id: UUID, session_id: UUID) -> User:
        """Valida que la sesión del access token siga activa y retorna el usuario."""
        user = await self.users.get_user_with_active_session(
            user_id=user_id,
            session_id=session_id,
        )
        if user is None:
            raise InvalidTokenError("La sesión fue cerrada o revocada.")
        if not user.is_active:
            raise InvalidCredentialsError("La cuenta de usuario está desactivada.")
        return user

    # --- Recuperación de contraseña ------------------------------------------------------

    async def request_password_reset(self, email: str, *, correlation_id: str = "") -> None:
        """Encola el envío del enlace de reset si la cuenta existe; nunca revela si existe.

        El token lo genera el worker al consumir el evento, para que el secreto no viaje
        por la tabla Outbox ni por el broker.
        """
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active:
            return

        payload = PasswordResetRequestedPayload(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
        )
        self.outbox.enqueue(
            event=EventEnvelope(
                event_type=PASSWORD_RESET_REQUESTED_EVENT,
                correlation_id=correlation_id,
                payload=payload.model_dump(mode="json"),
            ),
            aggregate_type="user",
            aggregate_id=str(user.id),
        )
        await self.session.commit()

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        """Cambia la contraseña con un token de un solo uso y cierra todas las sesiones."""
        record = await self.users.get_password_reset_token_for_update(hash_reset_token(raw_token))
        now = datetime.now(UTC)
        if record is None or record.used_at is not None or record.expires_at <= now:
            raise InvalidPasswordResetTokenError(
                "El enlace de recuperación es inválido, expiró o ya fue utilizado.",
            )

        user = await self.users.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise InvalidPasswordResetTokenError(
                "El enlace de recuperación es inválido, expiró o ya fue utilizado.",
            )

        user.password_hash = hash_password(new_password)
        record.used_at = now
        await self.users.invalidate_password_reset_tokens(user.id)
        await self.users.revoke_all_user_sessions(user.id, reason="password_reset")
        await self.session.commit()

    # --- Internos ------------------------------------------------------------------------

    @staticmethod
    def _binding_matches(auth_session: AuthSession, client_binding: str | None) -> bool:
        if auth_session.client_binding_hash is None:
            return True
        if not client_binding:
            return False
        return hmac.compare_digest(auth_session.client_binding_hash, _sha256(client_binding))

    def _within_grace_window(
        self,
        record: RefreshToken,
        auth_session: AuthSession,
        now: datetime,
    ) -> bool:
        grace = self.settings.refresh_reuse_grace_seconds
        return (
            grace > 0
            # El segundo factor es obligatorio para la gracia (ya validado por _binding_matches)
            and auth_session.client_binding_hash is not None
            and record.replaced_by_jti is not None
            and record.revoked_at is not None
            and (now - record.revoked_at) <= timedelta(seconds=grace)
        )

    async def _grace_successor(self, record: RefreshToken) -> RefreshToken | None:
        if record.replaced_by_jti is None:
            return None
        successor = await self.users.get_refresh_token_by_jti(record.replaced_by_jti)
        # Solo un salto: si el sucesor ya rotó o fue revocado, se trata como reuso.
        if successor is None or successor.revoked_at is not None:
            return None
        return successor

    async def _require_active_user(self, user_id: UUID) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidTokenError("Usuario inactivo o inexistente.")
        return user

    def _replay_tokens(self, user: User, successor: RefreshToken) -> TokenResponse:
        """Devuelve el refresh sucesor existente (re-firmado idéntico) y un access nuevo."""
        refresh = reissue_refresh_token(
            user_id=user.id,
            email=user.email,
            session_id=successor.session_id,
            jti=successor.token_jti,
            issued_at=successor.issued_at,
            expires_at=successor.expires_at,
            secret_key=self.settings.jwt_secret_key,
            algorithm=self.settings.jwt_algorithm,
        )
        return TokenResponse(
            access_token=self._new_access_token(user, successor.session_id),
            refresh_token=refresh,
            expires_in=self.settings.access_token_expire_minutes * 60,
        )

    def _new_access_token(self, user: User, session_id: UUID) -> str:
        return create_access_token(
            user_id=user.id,
            email=user.email,
            session_id=session_id,
            secret_key=self.settings.jwt_secret_key,
            algorithm=self.settings.jwt_algorithm,
            expire_minutes=self.settings.access_token_expire_minutes,
        )

    def _issue_tokens_uncommitted(
        self,
        user: User,
        session_id: UUID,
    ) -> tuple[TokenResponse, UUID]:
        issued = create_refresh_token(
            user_id=user.id,
            email=user.email,
            session_id=session_id,
            secret_key=self.settings.jwt_secret_key,
            algorithm=self.settings.jwt_algorithm,
            expire_days=self.settings.refresh_token_expire_days,
        )
        self.users.add_refresh_token(
            user_id=user.id,
            session_id=session_id,
            token_jti=issued.jti,
            issued_at=issued.issued_at,
            expires_at=issued.expires_at,
        )
        tokens = TokenResponse(
            access_token=self._new_access_token(user, session_id),
            refresh_token=issued.token,
            expires_in=self.settings.access_token_expire_minutes * 60,
        )
        return tokens, issued.jti

    async def _issue_tokens(self, user: User, session_id: UUID) -> TokenResponse:
        tokens, _ = self._issue_tokens_uncommitted(user, session_id)
        await self.session.commit()
        return tokens
