"""Endpoint agregado del dashboard: 1 llamada en lugar de 4 por carga del panel (issue #16)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.openapi import problem_responses
from app.modules.dashboard.schemas import PantryDashboardResponse
from app.modules.notifications.dependencies import NotificationServiceDep
from app.modules.pantry.dependencies import PantryServiceDep
from app.modules.pantry.exceptions import PantryAccessDeniedError
from app.modules.pantry.schemas import LocationResponse, PantryResponse
from app.modules.users.dependencies import get_current_user
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1", tags=["dashboard"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get(
    "/pantries/{pantry_id}/dashboard",
    response_model=PantryDashboardResponse,
    summary="Datos del panel de una despensa en una sola llamada",
    responses=problem_responses(PantryAccessDeniedError),
)
async def get_pantry_dashboard(
    pantry_id: UUID,
    current_user: CurrentUserDep,
    pantry_service: PantryServiceDep,
    notification_service: NotificationServiceDep,
) -> PantryDashboardResponse:
    """Equivale a GET /pantries + /pantries/{id}/locations + /pantries/{id}/batches +
    el `unread_count` de GET /notifications, con una sola autenticación y una sola
    comprobación de membresía. Responde 403 si el usuario no es miembro."""
    pantries, locations, batches = await pantry_service.pantry_overview(
        pantry_id,
        user_id=current_user.id,
    )
    unread = await notification_service.unread_count(user_id=current_user.id)
    return PantryDashboardResponse(
        pantries=[PantryResponse.model_validate(p) for p in pantries],
        locations=[LocationResponse.model_validate(loc) for loc in locations],
        batches=batches,
        unread_notifications=unread,
    )
