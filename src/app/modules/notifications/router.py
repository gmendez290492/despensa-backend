"""Rutas de API REST para el módulo de notificaciones y alertas de caducidad."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.modules.notifications.dependencies import (
    ExpirationScannerDep,
    NotificationServiceDep,
)
from app.modules.notifications.schemas import (
    ExpirationScanResponse,
    NotificationListResponse,
    NotificationMarkReadResponse,
)
from app.modules.users.dependencies import get_current_user
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get(
    "",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar notificaciones del usuario",
)
async def list_notifications(
    current_user: CurrentUserDep,
    service: NotificationServiceDep,
    unread_only: Annotated[
        bool,
        Query(description="Filtrar solo notificaciones no leídas"),
    ] = False,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Límite de elementos"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Desplazamiento para paginación"),
    ] = 0,
) -> NotificationListResponse:
    """Retorna las notificaciones in-app del usuario autenticado."""
    return await service.list_notifications(
        user_id=current_user.id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationMarkReadResponse,
    status_code=status.HTTP_200_OK,
    summary="Marcar notificación como leída",
)
async def mark_notification_as_read(
    notification_id: UUID,
    current_user: CurrentUserDep,
    service: NotificationServiceDep,
) -> NotificationMarkReadResponse:
    """Marca una notificación específica como leída."""
    return await service.mark_as_read(
        notification_id=notification_id,
        user_id=current_user.id,
    )


@router.patch(
    "/read-all",
    response_model=NotificationMarkReadResponse,
    status_code=status.HTTP_200_OK,
    summary="Marcar todas las notificaciones como leídas",
)
async def mark_all_notifications_as_read(
    current_user: CurrentUserDep,
    service: NotificationServiceDep,
) -> NotificationMarkReadResponse:
    """Marca todas las notificaciones pendientes del usuario como leídas."""
    return await service.mark_all_as_read(user_id=current_user.id)


@router.post(
    "/scan",
    response_model=ExpirationScanResponse,
    status_code=status.HTTP_200_OK,
    summary="Disparar escaneo de caducidad",
)
async def trigger_expiration_scan(
    _current_user: CurrentUserDep,
    scanner: ExpirationScannerDep,
) -> ExpirationScanResponse:
    """Ejecuta el escaneo de lotes por caducar y emite alertas idempotentes in-app y por email."""
    return await scanner.scan_expirations()
