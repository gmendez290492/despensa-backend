"""Esquemas del endpoint agregado del dashboard."""

from pydantic import BaseModel, Field

from app.modules.pantry.schemas import FoodBatchResponse, LocationResponse, PantryResponse


class PantryDashboardResponse(BaseModel):
    """Todo lo que el panel necesita para pintar una despensa en una sola llamada."""

    pantries: list[PantryResponse] = Field(
        description="Despensas del usuario (igual que GET /pantries), para el selector.",
    )
    locations: list[LocationResponse] = Field(
        description="Zonas de la despensa (igual que GET /pantries/{id}/locations).",
    )
    batches: list[FoodBatchResponse] = Field(
        description="Lotes disponibles en orden FEFO (igual que GET /pantries/{id}/batches).",
    )
    unread_notifications: int = Field(
        ge=0,
        description="Notificaciones sin leer del usuario (unread_count de GET /notifications).",
    )
