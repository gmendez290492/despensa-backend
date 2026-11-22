"""Repositorio de acceso a datos para notificaciones con SQLAlchemy async."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification


class NotificationRepository:
    """Operaciones de persistencia para el módulo de notificaciones."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, notification: Notification) -> Notification:
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        query = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            query = query.where(Notification.is_read.is_(False))

        query = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_for_user(self, *, user_id: UUID, unread_only: bool = False) -> int:
        query = select(func.count(Notification.id)).where(Notification.user_id == user_id)
        if unread_only:
            query = query.where(Notification.is_read.is_(False))
        result = await self.session.execute(query)
        return int(result.scalar_one() or 0)

    async def get_by_id_and_user(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
    ) -> Notification | None:
        query = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def mark_as_read(self, *, notification_id: UUID, user_id: UUID) -> bool:
        stmt = (
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.now(UTC))
        )
        result = await self.session.execute(stmt)
        cursor = cast(CursorResult[Any], result)
        return int(cursor.rowcount or 0) > 0

    async def mark_all_as_read(self, *, user_id: UUID) -> int:
        stmt = (
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.now(UTC))
        )
        result = await self.session.execute(stmt)
        cursor = cast(CursorResult[Any], result)
        return int(cursor.rowcount or 0)
