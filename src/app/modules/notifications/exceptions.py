"""Excepciones de dominio para el módulo de notificaciones mapeadas a RFC 7807."""

from fastapi import status

from app.core.exceptions import DomainError


class NotificationNotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "notification-not-found"
    title = "Notificación no encontrada"

    def __init__(self, notification_id: str) -> None:
        super().__init__(
            detail=(
                f"La notificación con ID '{notification_id}' no existe o pertenece a otro usuario."
            ),
        )
