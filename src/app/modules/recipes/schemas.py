"""Esquemas Pydantic v2 para el catálogo y motor de recomendaciones de recetas."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RecipeIngredientRead(BaseModel):
    """Ingrediente de una receta con información de producto y unidad."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    product_name: str | None = None
    quantity: Decimal
    unit_code: str
    is_optional: bool = False


class RecipeRead(BaseModel):
    """Representación completa de una receta culinaria."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    instructions: str
    prep_time_minutes: int
    cook_time_minutes: int
    servings: int
    created_at: datetime
    ingredients: list[RecipeIngredientRead] = Field(default_factory=list)


class RecipeListResponse(BaseModel):
    """Listado paginado de recetas."""

    items: list[RecipeRead]
    total: int = Field(..., ge=0)


class RecommendedRecipeRead(BaseModel):
    """Receta con puntuación de coincidencia y rescate de alimentos por caducar."""

    recipe: RecipeRead
    match_percentage: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Porcentaje de ingredientes disponibles",
    )
    urgency_score: float = Field(
        ...,
        ge=0.0,
        description="Puntaje ponderado por caducidad inminente",
    )
    expiring_ingredients: list[str] = Field(
        default_factory=list,
        description="Ingredientes que están en estado crítico o precaución en la despensa",
    )
    missing_ingredients: list[str] = Field(
        default_factory=list,
        description="Ingredientes no disponibles que se deben comprar",
    )
    can_cook_now: bool = Field(
        ...,
        description="True si se tienen todos los ingredientes obligatorios",
    )


class RecommendationResponse(BaseModel):
    """Listado de recomendaciones ordenadas por prioridad de consumo."""

    items: list[RecommendedRecipeRead]
    total: int = Field(..., ge=0)
