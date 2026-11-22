"""Pruebas de integración de Etapa 4: Catálogo de recetas y motor de scoring anti-desperdicio."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.recipes.models import Recipe, RecipeIngredient


async def _register_and_login(
    client: AsyncClient,
    email: str,
    name: str,
    alert_days: int = 5,
) -> tuple[str, str]:
    password = "SuperPassword123!"
    reg_res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": name,
            "timezone": "America/Mexico_City",
            "alert_days_before": alert_days,
        },
    )
    assert reg_res.status_code == 201
    user_id = reg_res.json()["id"]

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    return user_id, token


@pytest.mark.asyncio
async def test_recipes_catalog_and_detail(
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica consulta de catálogo maestro y detalle de una receta."""
    _, token = await _register_and_login(
        api_client, f"chef_{uuid4().hex[:6]}@example.com", "Chef Catalog"
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Crear categoría y productos en BD
    cat_res = await api_client.get("/api/v1/categories", headers=headers)
    cat_id = cat_res.json()[0]["id"]

    prod_res = await api_client.post(
        "/api/v1/products",
        json={"category_id": cat_id, "name": f"Huevo {uuid4().hex[:4]}", "base_unit_code": "pza"},
        headers=headers,
    )
    product_id = prod_res.json()["id"]

    # 2. Insertar una receta con ingrediente directamente
    recipe_id = uuid4()
    async with db_session_factory() as session:
        recipe = Recipe(
            id=recipe_id,
            title="Huevos Revueltos Tradicionales",
            description="Desayuno rápido rico en proteína.",
            instructions="Batir los huevos y cocinar a fuego medio durante 3 minutos.",
            prep_time_minutes=5,
            cook_time_minutes=3,
            servings=1,
        )
        ingredient = RecipeIngredient(
            recipe_id=recipe_id,
            product_id=product_id,
            quantity=Decimal("2.0"),
            unit_code="pza",
            is_optional=False,
        )
        session.add(recipe)
        session.add(ingredient)
        await session.commit()

    # 3. Listar recetas públicas
    list_res = await api_client.get("/api/v1/recipes")
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] >= 1
    found = next((r for r in data["items"] if r["id"] == str(recipe_id)), None)
    assert found is not None
    assert found["title"] == "Huevos Revueltos Tradicionales"
    assert len(found["ingredients"]) == 1
    assert found["ingredients"][0]["quantity"] == "2.0000"

    # 4. Consultar detalle de la receta
    detail_res = await api_client.get(f"/api/v1/recipes/{recipe_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["title"] == "Huevos Revueltos Tradicionales"
    assert detail["servings"] == 1

    # 5. Receta inexistente -> 404 RFC 7807
    fake_id = str(uuid4())
    err_res = await api_client.get(f"/api/v1/recipes/{fake_id}")
    assert err_res.status_code == 404
    assert err_res.json()["type"] == "https://despensa.api/errors/recipe-not-found"


@pytest.mark.asyncio
async def test_recipe_recommendations_scoring_and_anti_waste(
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que el algoritmo prioriza recetas con ingredientes por caducar."""
    _, token = await _register_and_login(
        api_client, f"food_saver_{uuid4().hex[:6]}@example.com", "Food Saver", alert_days=5
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Crear despensa y ubicación
    p_res = await api_client.post(
        "/api/v1/pantries",
        json={"name": "Cocina Saver"},
        headers=headers,
    )
    pantry_id = p_res.json()["id"]

    loc_res = await api_client.get(f"/api/v1/pantries/{pantry_id}/locations", headers=headers)
    location_id = loc_res.json()[0]["id"]

    cat_res = await api_client.get("/api/v1/categories", headers=headers)
    cat_id = cat_res.json()[0]["id"]

    # 2. Crear 3 productos distintos
    prod1 = (
        await api_client.post(
            "/api/v1/products",
            json={
                "category_id": cat_id,
                "name": f"Pollo Fresco {uuid4().hex[:4]}",
                "base_unit_code": "kg",
            },
            headers=headers,
        )
    ).json()

    prod2 = (
        await api_client.post(
            "/api/v1/products",
            json={
                "category_id": cat_id,
                "name": f"Leche Fresca {uuid4().hex[:4]}",
                "base_unit_code": "l",
            },
            headers=headers,
        )
    ).json()

    prod3 = (
        await api_client.post(
            "/api/v1/products",
            json={
                "category_id": cat_id,
                "name": f"Arroz Grano {uuid4().hex[:4]}",
                "base_unit_code": "kg",
            },
            headers=headers,
        )
    ).json()

    # 3. Crear 2 recetas en base de datos:
    # Receta 1: "Pollo a la Plancha" -> usa Pollo Fresco (0.5 kg)
    recipe1_id = uuid4()
    # Receta 2: "Arroz con Leche" -> usa Leche (1.0 l) y Arroz (0.5 kg)
    recipe2_id = uuid4()

    async with db_session_factory() as session:
        r1 = Recipe(
            id=recipe1_id,
            title="Pollo a la Plancha Express",
            description="Pollo dorado con especias.",
            instructions="Sazonar y dorar a fuego alto.",
            prep_time_minutes=5,
            cook_time_minutes=10,
            servings=1,
        )
        ing1 = RecipeIngredient(
            recipe_id=recipe1_id,
            product_id=prod1["id"],
            quantity=Decimal("0.5"),
            unit_code="kg",
        )

        r2 = Recipe(
            id=recipe2_id,
            title="Arroz con Leche Cremoso",
            description="Postre tradicional.",
            instructions="Hervir arroz con leche.",
            prep_time_minutes=10,
            cook_time_minutes=25,
            servings=4,
        )
        ing2_a = RecipeIngredient(
            recipe_id=recipe2_id,
            product_id=prod2["id"],
            quantity=Decimal("1.0"),
            unit_code="l",
        )
        ing2_b = RecipeIngredient(
            recipe_id=recipe2_id,
            product_id=prod3["id"],
            quantity=Decimal("0.5"),
            unit_code="kg",
        )
        session.add_all([r1, ing1, r2, ing2_a, ing2_b])
        await session.commit()

    # 4. Agregar lotes a la despensa:
    # Pollo vence MAÑANA (CRÍTICO: 1 día restante) -> Cantidad: 1.0 kg (suficiente)
    await api_client.post(
        f"/api/v1/pantries/{pantry_id}/batches",
        json={
            "location_id": location_id,
            "product_id": prod1["id"],
            "unit_code": "kg",
            "quantity": 1.0,
            "expiration_date": str(date.today() + timedelta(days=1)),
        },
        headers=headers,
    )

    # Leche vence en 20 días (Sin urgencia) -> Cantidad: 1.0 l (suficiente)
    await api_client.post(
        f"/api/v1/pantries/{pantry_id}/batches",
        json={
            "location_id": location_id,
            "product_id": prod2["id"],
            "unit_code": "l",
            "quantity": 1.0,
            "expiration_date": str(date.today() + timedelta(days=20)),
        },
        headers=headers,
    )
    # Usuario NO tiene Arroz (Arroz con Leche le falta 1 ingrediente)

    # 5. Solicitar recomendaciones
    rec_res = await api_client.get("/api/v1/recipes/recommended", headers=headers)
    assert rec_res.status_code == 200
    recommendations = rec_res.json()["items"]
    assert len(recommendations) >= 2

    # Top 1 debe ser "Pollo a la Plancha Express" porque:
    # - Tiene 100% de ingredientes disponibles
    # - Salva el pollo crítico que vence mañana (urgency_score = 50.0)
    top1 = recommendations[0]
    assert top1["recipe"]["id"] == str(recipe1_id)
    assert top1["match_percentage"] == 100.0
    assert top1["urgency_score"] == 50.0
    assert top1["can_cook_now"] is True
    assert len(top1["expiring_ingredients"]) == 1
    assert top1["missing_ingredients"] == []

    # La segunda recomendación es Arroz con Leche:
    top2 = recommendations[1]
    assert top2["recipe"]["id"] == str(recipe2_id)
    assert top2["match_percentage"] == 50.0  # Solo tiene leche, le falta arroz
    assert top2["urgency_score"] == 0.0
    assert top2["can_cook_now"] is False
    assert len(top2["missing_ingredients"]) == 1


@pytest.mark.asyncio
async def test_recipes_recommended_requires_auth(api_client: AsyncClient) -> None:
    """Verifica que solicitar recetas recomendadas sin token retorne 401 Unauthorized."""
    unauth_res = await api_client.get("/api/v1/recipes/recommended")
    assert unauth_res.status_code == 401
