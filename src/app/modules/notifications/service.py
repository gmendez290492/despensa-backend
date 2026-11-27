"""Servicio de lógica de negocio para la gestión de notificaciones in-app."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.exceptions import NotificationNotFoundError
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import (
    NotificationListResponse,
    NotificationMarkReadResponse,
    NotificationRead,
)


class NotificationService:
    """Casos de uso para consulta y actualización de notificaciones de un usuario."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = NotificationRepository(session)

    async def list_notifications(
        self,
        *,
        user_id: UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> NotificationListResponse:
        """Retorna las notificaciones del usuario y el conteo de no leídas."""
        items = await self.repo.list_for_user(
            user_id=user_id,
            unread_only=unread_only,
            limit=limit,
            offset=offset,
        )
        total = await self.repo.count_for_user(user_id=user_id, unread_only=unread_only)
        unread_count = await self.repo.count_for_user(user_id=user_id, unread_only=True)

        return NotificationListResponse(
            items=[NotificationRead.model_validate(item) for item in items],
            total=total,
            unread_count=unread_count,
        )

    async def unread_count(self, *, user_id: UUID) -> int:
        """Número de notificaciones sin leer del usuario."""
        return await self.repo.count_for_user(user_id=user_id, unread_only=True)

    async def mark_as_read(
        self,
        *,
        notification_id: UUID,
        user_id: UUID,
    ) -> NotificationMarkReadResponse:
        """Marca una notificación específica como leída si pertenece al usuario."""
        existing = await self.repo.get_by_id_and_user(
            notification_id=notification_id,
            user_id=user_id,
        )
        if not existing:
            raise NotificationNotFoundError(str(notification_id))

        updated = await self.repo.mark_as_read(
            notification_id=notification_id,
            user_id=user_id,
        )
        await self.session.commit()
        return NotificationMarkReadResponse(marked_count=1 if updated else 0)

    async def mark_all_as_read(self, *, user_id: UUID) -> NotificationMarkReadResponse:
        """Marca todas las notificaciones no leídas del usuario como leídas."""
        count = await self.repo.mark_all_as_read(user_id=user_id)
        await self.session.commit()
        return NotificationMarkReadResponse(marked_count=count)
