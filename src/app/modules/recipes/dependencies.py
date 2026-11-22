"""Inyección de dependencias para el módulo de recetas."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.modules.recipes.service import RecipeService


async def get_recipe_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RecipeService:
    """Inyecta la instancia activa de RecipeService."""
    return RecipeService(session)


RecipeServiceDep = Annotated[RecipeService, Depends(get_recipe_service)]
