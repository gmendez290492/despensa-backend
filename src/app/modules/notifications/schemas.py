"""Esquemas Pydantic v2 para el módulo de notificaciones."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationRead(BaseModel):
    """Representación de lectura de una notificación in-app."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    pantry_id: UUID
    batch_id: UUID | None = None
    title: str = Field(..., max_length=128)
    message: str
    notification_type: str = Field(..., max_length=32)
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Respuesta paginada del listado de notificaciones."""

    items: list[NotificationRead]
    total: int = Field(..., ge=0)
    unread_count: int = Field(..., ge=0)


class NotificationMarkReadResponse(BaseModel):
    """Respuesta tras marcar una o múltiples notificaciones como leídas."""

    marked_count: int = Field(..., ge=0)
    success: bool = True


class ExpirationScanResponse(BaseModel):
    """Resultado de la ejecución de un escaneo de caducidad."""

    scanned_pantries: int = Field(..., ge=0)
    evaluated_batches: int = Field(..., ge=0)
    alerts_generated: int = Field(..., ge=0)
    emails_sent: int = Field(..., ge=0)
