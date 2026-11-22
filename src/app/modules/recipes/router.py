"""Rutas de API REST para el módulo de recetas y recomendaciones anti-desperdicio."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.modules.recipes.dependencies import RecipeServiceDep
from app.modules.recipes.schemas import (
    RecipeListResponse,
    RecipeRead,
    RecommendationResponse,
)
from app.modules.users.dependencies import get_current_user
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/recipes", tags=["recipes"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get(
    "",
    response_model=RecipeListResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar catálogo maestro de recetas",
)
async def list_recipes(
    service: RecipeServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecipeListResponse:
    """Retorna las recetas disponibles en el catálogo."""
    return await service.list_recipes(limit=limit, offset=offset)


@router.get(
    "/recommended",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener recetas recomendadas según despensa y caducidad",
)
async def get_recommended_recipes(
    current_user: CurrentUserDep,
    service: RecipeServiceDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> RecommendationResponse:
    """Calcula y devuelve las recetas recomendadas priorizando ingredientes por caducar."""
    return await service.get_recommended_recipes(user=current_user, limit=limit)


@router.get(
    "/{recipe_id}",
    response_model=RecipeRead,
    status_code=status.HTTP_200_OK,
    summary="Consultar detalle de una receta",
)
async def get_recipe_by_id(
    recipe_id: UUID,
    service: RecipeServiceDep,
) -> RecipeRead:
    """Retorna la información completa de una receta y sus ingredientes requeridos."""
    return await service.get_recipe_by_id(recipe_id)
