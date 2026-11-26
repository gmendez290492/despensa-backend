"""Repositorio de acceso a datos para usuarios, sesiones, refresh tokens y resets."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import AuthSession, PasswordResetToken, RefreshToken, User


class UserRepository:
    """Encapsula consultas SQLAlchemy para User, AuthSession, RefreshToken y resets."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        """Busca un usuario por email normalizado."""
        stmt = select(User).where(User.email == email.lower())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Busca un usuario por su UUID."""
        return await self.session.get(User, user_id)

    def create(
        self,
        *,
        email: str,
        full_name: str,
        password_hash: str,
        timezone: str,
        alert_days_before: int,
    ) -> User:
        """Agrega un nuevo usuario a la sesión actual."""
        user = User(
            email=email.lower(),
            full_name=full_name,
            password_hash=password_hash,
            timezone=timezone,
            alert_days_before=alert_days_before,
        )
        self.session.add(user)
        return user

    # --- Sesiones de autenticación -------------------------------------------------------

    def create_auth_session(
        self,
        *,
        user_id: UUID,
        client_binding_hash: str | None,
    ) -> AuthSession:
        """Abre una sesión nueva (familia de refresh tokens) para el usuario."""
        auth_session = AuthSession(user_id=user_id, client_binding_hash=client_binding_hash)
        self.session.add(auth_session)
        return auth_session

    async def get_auth_session(self, session_id: UUID) -> AuthSession | None:
        """Busca una sesión por su UUID."""
        return await self.session.get(AuthSession, session_id)

    async def revoke_auth_session(self, session_id: UUID, *, reason: str) -> None:
        """Revoca una sesión y todos sus refresh tokens activos."""
        now = datetime.now(UTC)
        await self.session.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason=reason),
        )
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.session_id == session_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now),
        )

    async def revoke_all_user_sessions(self, user_id: UUID, *, reason: str) -> None:
        """Revoca todas las sesiones y refresh tokens activos de un usuario."""
        now = datetime.now(UTC)
        await self.session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason=reason),
        )
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now),
        )

    # --- Refresh tokens ------------------------------------------------------------------

    def add_refresh_token(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        token_jti: UUID,
        issued_at: datetime,
        expires_at: datetime,
    ) -> RefreshToken:
        """Registra un nuevo refresh token activo dentro de una sesión."""
        record = RefreshToken(
            user_id=user_id,
            session_id=session_id,
            token_jti=token_jti,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        self.session.add(record)
        return record

    async def get_refresh_token_by_jti(
        self,
        token_jti: UUID,
        *,
        for_update: bool = False,
    ) -> RefreshToken | None:
        """Busca un refresh token por JTI; con for_update bloquea la fila (rotación segura)."""
        stmt = select(RefreshToken).where(RefreshToken.token_jti == token_jti)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # --- Recuperación de contraseña ------------------------------------------------------

    def add_password_reset_token(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetToken:
        """Registra un token de reset (solo su hash)."""
        record = PasswordResetToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.session.add(record)
        return record

    async def get_password_reset_token_for_update(
        self,
        token_hash: str,
    ) -> PasswordResetToken | None:
        """Busca un token de reset por hash bloqueando la fila (evita doble uso concurrente)."""
        stmt = (
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == token_hash)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def invalidate_password_reset_tokens(self, user_id: UUID) -> None:
        """Marca como usados los tokens de reset pendientes del usuario."""
        await self.session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
            .values(used_at=datetime.now(UTC)),
        )

    async def delete_stale_password_reset_tokens(self, user_id: UUID) -> None:
        """Elimina los tokens de reset usados o expirados del usuario (tabla acotada)."""
        await self.session.execute(
            delete(PasswordResetToken).where(
                PasswordResetToken.user_id == user_id,
                or_(
                    PasswordResetToken.used_at.is_not(None),
                    PasswordResetToken.expires_at <= datetime.now(UTC),
                ),
            ),
        )
