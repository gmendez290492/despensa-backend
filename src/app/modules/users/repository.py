"""Repositorio de acceso a datos para usuarios y refresh tokens."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import RefreshToken, User


class UserRepository:
    """Encapsula consultas SQLAlchemy para User y RefreshToken."""

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

    def add_refresh_token(
        self,
        *,
        user_id: UUID,
        token_jti: UUID,
        expires_at: datetime,
    ) -> RefreshToken:
        """Registra un nuevo refresh token activo."""
        record = RefreshToken(
            user_id=user_id,
            token_jti=token_jti,
            expires_at=expires_at,
        )
        self.session.add(record)
        return record

    async def get_refresh_token_by_jti(self, token_jti: UUID) -> RefreshToken | None:
        """Busca un refresh token por su identificador JTI."""
        stmt = select(RefreshToken).where(RefreshToken.token_jti == token_jti)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_all_user_refresh_tokens(self, user_id: UUID) -> None:
        """Revoca todos los refresh tokens activos de un usuario (defensa ante reuso)."""
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
