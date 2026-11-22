"""Repositorio de acceso a datos para recetas con SQLAlchemy async."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.recipes.models import Recipe, RecipeIngredient


class RecipeRepository:
    """Consultas de persistencia para el catálogo de recetas e ingredientes."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_recipes(self, *, limit: int = 50, offset: int = 0) -> Sequence[Recipe]:
        query = (
            select(Recipe)
            .options(
                selectinload(Recipe.ingredients).selectinload(RecipeIngredient.product),
            )
            .order_by(Recipe.title.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_recipes(self) -> int:
        query = select(func.count(Recipe.id))
        result = await self.session.execute(query)
        return int(result.scalar_one() or 0)

    async def get_by_id(self, recipe_id: UUID) -> Recipe | None:
        query = (
            select(Recipe)
            .where(Recipe.id == recipe_id)
            .options(
                selectinload(Recipe.ingredients).selectinload(RecipeIngredient.product),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_all_for_scoring(self) -> Sequence[Recipe]:
        """Obtiene todas las recetas con sus ingredientes para el motor de scoring."""
        query = (
            select(Recipe)
            .options(
                selectinload(Recipe.ingredients).selectinload(RecipeIngredient.product),
            )
            .order_by(Recipe.title.asc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()
