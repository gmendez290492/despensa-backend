"""Servicio de catálogo de recetas y motor de recomendación inteligente anti-desperdicio."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.pantry.models import FoodBatch, Location, PantryMember
from app.modules.recipes.exceptions import RecipeNotFoundError
from app.modules.recipes.models import Recipe
from app.modules.recipes.repository import RecipeRepository
from app.modules.recipes.schemas import (
    RecipeIngredientRead,
    RecipeListResponse,
    RecipeRead,
    RecommendationResponse,
    RecommendedRecipeRead,
)
from app.modules.users.models import User


class RecipeService:
    """Lógica de negocio para consulta de recetas y recomendaciones personalizadas."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = RecipeRepository(session)

    def _to_recipe_read(self, recipe: Recipe) -> RecipeRead:
        ingredients = [
            RecipeIngredientRead(
                id=ing.id,
                product_id=ing.product_id,
                product_name=ing.product.name if ing.product else None,
                quantity=ing.quantity,
                unit_code=ing.unit_code,
                is_optional=ing.is_optional,
            )
            for ing in recipe.ingredients
        ]
        return RecipeRead(
            id=recipe.id,
            title=recipe.title,
            description=recipe.description,
            instructions=recipe.instructions,
            prep_time_minutes=recipe.prep_time_minutes,
            cook_time_minutes=recipe.cook_time_minutes,
            servings=recipe.servings,
            created_at=recipe.created_at,
            ingredients=ingredients,
        )

    async def list_recipes(self, *, limit: int = 50, offset: int = 0) -> RecipeListResponse:
        recipes = await self.repo.list_recipes(limit=limit, offset=offset)
        total = await self.repo.count_recipes()
        return RecipeListResponse(
            items=[self._to_recipe_read(r) for r in recipes],
            total=total,
        )

    async def get_recipe_by_id(self, recipe_id: UUID) -> RecipeRead:
        recipe = await self.repo.get_by_id(recipe_id)
        if not recipe:
            raise RecipeNotFoundError(str(recipe_id))
        return self._to_recipe_read(recipe)

    async def get_recommended_recipes(
        self,
        *,
        user: User,
        limit: int = 10,
    ) -> RecommendationResponse:
        """Calcula recomendaciones personalizadas priorizando rescate de caducidades."""
        # 1. Obtener zonas horarias y fecha local
        try:
            user_tz = ZoneInfo(user.timezone)
            user_today = datetime.now(user_tz).date()
        except Exception:
            user_today = datetime.now(UTC).date()

        # 2. Obtener todas las despensas donde el usuario es miembro
        pantries_stmt = select(PantryMember.pantry_id).where(PantryMember.user_id == user.id)
        pantry_ids = list((await self.session.execute(pantries_stmt)).scalars().all())

        # 3. Mapear inventario disponible y caducidades del usuario
        available_stock: dict[UUID, Decimal] = {}
        urgency_by_product: dict[UUID, float] = {}
        product_names: dict[UUID, str] = {}

        if pantry_ids:
            batches_stmt = (
                select(FoodBatch)
                .join(Location, FoodBatch.location_id == Location.id)
                .where(
                    Location.pantry_id.in_(pantry_ids),
                    FoodBatch.current_quantity > 0,
                )
                .options(selectinload(FoodBatch.product))
            )
            batches = list((await self.session.execute(batches_stmt)).scalars().all())

            for b in batches:
                pid = b.product_id
                available_stock[pid] = available_stock.get(pid, Decimal("0")) + b.current_quantity
                if b.product:
                    product_names[pid] = b.product.name

                days_left = (b.expiration_date - user_today).days
                # Ponderación de urgencia
                if days_left <= 2:
                    current_weight = 50.0  # Crítico / Muy próximo
                elif days_left <= user.alert_days_before:
                    current_weight = 25.0  # Precaución
                else:
                    current_weight = 0.0

                if current_weight > urgency_by_product.get(pid, 0.0):
                    urgency_by_product[pid] = current_weight

        # 4. Evaluar cada receta en el catálogo maestro
        recipes = await self.repo.list_all_for_scoring()
        scored_recommendations: list[tuple[float, float, RecommendedRecipeRead]] = []

        for recipe in recipes:
            total_ingredients = len(recipe.ingredients)
            if total_ingredients == 0:
                continue

            available_count = 0
            recipe_urgency = 0.0
            expiring_items: list[str] = []
            missing_items: list[str] = []

            for ing in recipe.ingredients:
                pid = ing.product_id
                pname = ing.product.name if ing.product else "Ingrediente"
                has_enough = available_stock.get(pid, Decimal("0")) >= ing.quantity

                if has_enough:
                    available_count += 1
                    urgency = urgency_by_product.get(pid, 0.0)
                    if urgency > 0.0:
                        recipe_urgency += urgency
                        expiring_items.append(pname)
                else:
                    if not ing.is_optional:
                        missing_items.append(pname)

            match_pct = round((available_count / total_ingredients) * 100.0, 1)
            can_cook = len(missing_items) == 0

            # Score total: coincidencia de ingredientes + bonus por rescate crítico
            total_score = match_pct + (recipe_urgency * 2.0)

            read_dto = RecommendedRecipeRead(
                recipe=self._to_recipe_read(recipe),
                match_percentage=match_pct,
                urgency_score=recipe_urgency,
                expiring_ingredients=expiring_items,
                missing_ingredients=missing_items,
                can_cook_now=can_cook,
            )
            scored_recommendations.append((total_score, match_pct, read_dto))

        # 5. Ordenar por score total descendente y porcentaje de coincidencia
        scored_recommendations.sort(key=lambda x: (x[0], x[1]), reverse=True)

        selected = [item[2] for item in scored_recommendations[:limit]]
        return RecommendationResponse(items=selected, total=len(selected))
