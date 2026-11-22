"""Pruebas de integración de la Etapa 2: Despensas, Lotes FEFO y Seguridad IDOR."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient


async def get_auth_token_for_user(client: AsyncClient, email: str, name: str) -> str:
    """Helper para registrar un usuario y obtener su JWT de acceso."""
    password = "PasswordSeguro123!"
    reg_res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": name,
            "timezone": "America/Mexico_City",
        },
    )
    assert reg_res.status_code == 201

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    return login_res.json()["access_token"]


@pytest.mark.asyncio
async def test_pantry_lifecycle_and_multitenancy(api_client: AsyncClient) -> None:
    """Verifica creación de despensa, código de invitación y unión de miembros."""
    # 1. Registrar usuario 1 (Owner)
    token1 = await get_auth_token_for_user(
        api_client, f"owner_{uuid4().hex[:6]}@example.com", "Owner User"
    )
    headers1 = {"Authorization": f"Bearer {token1}"}

    # 2. Crear despensa "Casa Campestre"
    pantry_res = await api_client.post(
        "/api/v1/pantries",
        json={"name": "Casa Campestre"},
        headers=headers1,
    )
    assert pantry_res.status_code == 201
    pantry_data = pantry_res.json()
    pantry_id = pantry_data["id"]
    invite_code = pantry_data["invite_code"]
    assert invite_code.startswith("DESP-")

    # 3. Verificar que se creó la ubicación por defecto "Refrigerador"
    locs_res = await api_client.get(f"/api/v1/pantries/{pantry_id}/locations", headers=headers1)
    assert locs_res.status_code == 200
    locations = locs_res.json()
    assert len(locations) == 1
    assert locations[0]["name"] == "Refrigerador"

    # 4. Registrar usuario 2 (Roomie) y unirse con el código de invitación
    token2 = await get_auth_token_for_user(
        api_client, f"roomie_{uuid4().hex[:6]}@example.com", "Roomie User"
    )
    headers2 = {"Authorization": f"Bearer {token2}"}

    join_res = await api_client.post(
        "/api/v1/pantries/join",
        json={"invite_code": invite_code},
        headers=headers2,
    )
    assert join_res.status_code == 200
    assert join_res.json()["id"] == pantry_id

    # 5. El usuario 2 ahora ve "Casa Campestre" en sus despensas
    list_res = await api_client.get("/api/v1/pantries", headers=headers2)
    assert list_res.status_code == 200
    assert any(p["id"] == pantry_id for p in list_res.json())


@pytest.mark.asyncio
async def test_idor_security_shield_blocks_non_members(api_client: AsyncClient) -> None:
    """Escudo de seguridad IDOR: un usuario ajeno NUNCA puede consultar ni alterar la despensa."""
    # Usuario legítimo crea despensa A
    token_a = await get_auth_token_for_user(
        api_client, f"user_a_{uuid4().hex[:6]}@example.com", "User A"
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    pantry_res = await api_client.post(
        "/api/v1/pantries", json={"name": "Despensa Privada A"}, headers=headers_a
    )
    pantry_id = pantry_res.json()["id"]

    # Atacante o usuario ajeno B intenta acceder a la despensa A
    token_b = await get_auth_token_for_user(
        api_client, f"attacker_{uuid4().hex[:6]}@example.com", "Attacker B"
    )
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. Intento de listar ubicaciones -> 403 Forbidden
    idor_loc = await api_client.get(f"/api/v1/pantries/{pantry_id}/locations", headers=headers_b)
    assert idor_loc.status_code == 403
    assert idor_loc.json()["type"] == "https://despensa.api/errors/pantry-access-denied"

    # 2. Intento de listar lotes -> 403 Forbidden
    idor_batches = await api_client.get(f"/api/v1/pantries/{pantry_id}/batches", headers=headers_b)
    assert idor_batches.status_code == 403
    assert idor_batches.json()["type"] == "https://despensa.api/errors/pantry-access-denied"

    # 3. Intento de consumir inventario ajeno -> 403 Forbidden
    idor_consume = await api_client.post(
        f"/api/v1/pantries/{pantry_id}/consume",
        json={"product_id": str(uuid4()), "quantity": 1.0},
        headers=headers_b,
    )
    assert idor_consume.status_code == 403
    assert idor_consume.json()["type"] == "https://despensa.api/errors/pantry-access-denied"


@pytest.mark.asyncio
async def test_fefo_consumption_engine(api_client: AsyncClient) -> None:
    """Valida que el algoritmo FEFO descuenta primero de los lotes más próximos a caducar."""
    token = await get_auth_token_for_user(
        api_client, f"fefo_{uuid4().hex[:6]}@example.com", "Chef FEFO"
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Crear despensa
    pantry_res = await api_client.post(
        "/api/v1/pantries", json={"name": "Cocina FEFO"}, headers=headers
    )
    pantry_id = pantry_res.json()["id"]

    # Obtener ubicación "Refrigerador"
    loc_res = await api_client.get(f"/api/v1/pantries/{pantry_id}/locations", headers=headers)
    location_id = loc_res.json()[0]["id"]

    # Obtener categorías existentes de la semilla
    cat_res = await api_client.get("/api/v1/categories", headers=headers)
    category_id = cat_res.json()[0]["id"]

    # 2. Registrar producto "Leche Entera FEFO"
    prod_res = await api_client.post(
        "/api/v1/products",
        json={
            "category_id": category_id,
            "name": f"Leche Entera {uuid4().hex[:4]}",
            "base_unit_code": "l",
            "estimated_shelf_life_days": 7,
        },
        headers=headers,
    )
    assert prod_res.status_code == 201
    product_id = prod_res.json()["id"]

    today = date.today()

    # 3. Agregar 3 Lotes con diferentes fechas de vencimiento:
    # Lote 1: Vence en 2 días (CRÍTICO) -> Cantidad: 2.0 L
    batch1_res = await api_client.post(
        f"/api/v1/pantries/{pantry_id}/batches",
        json={
            "location_id": location_id,
            "product_id": product_id,
            "unit_code": "l",
            "quantity": 2.0,
            "expiration_date": str(today + timedelta(days=2)),
        },
        headers=headers,
    )
    assert batch1_res.status_code == 201
    batch1_id = batch1_res.json()["id"]
    assert batch1_res.json()["semaforo"] == "CRÍTICO"

    # Lote 2: Vence en 6 días (PRECAUCIÓN) -> Cantidad: 3.0 L
    batch2_res = await api_client.post(
        f"/api/v1/pantries/{pantry_id}/batches",
        json={
            "location_id": location_id,
            "product_id": product_id,
            "unit_code": "l",
            "quantity": 3.0,
            "expiration_date": str(today + timedelta(days=6)),
        },
        headers=headers,
    )
    assert batch2_res.status_code == 201
    batch2_id = batch2_res.json()["id"]
    assert batch2_res.json()["semaforo"] == "PRECAUCIÓN"

    # Lote 3: Vence en 15 días (ÓPTIMO) -> Cantidad: 1.0 L
    batch3_res = await api_client.post(
        f"/api/v1/pantries/{pantry_id}/batches",
        json={
            "location_id": location_id,
            "product_id": product_id,
            "unit_code": "l",
            "quantity": 1.0,
            "expiration_date": str(today + timedelta(days=15)),
        },
        headers=headers,
    )
    assert batch3_res.status_code == 201
    batch3_id = batch3_res.json()["id"]
    assert batch3_res.json()["semaforo"] == "ÓPTIMO"

    # Total en inventario = 2.0 + 3.0 + 1.0 = 6.0 L

    # 4. Consumir 3.5 Litros con algoritmo FEFO:
    # Debe agotar Lote 1 (2.0 L) y descontar 1.5 L de Lote 2 (quedándole 1.5 L)
    consume_res = await api_client.post(
        f"/api/v1/pantries/{pantry_id}/consume",
        json={"product_id": product_id, "quantity": 3.5, "notes": "Cocinando pastel"},
        headers=headers,
    )
    assert consume_res.status_code == 200
    consume_data = consume_res.json()
    assert Decimal(str(consume_data["consumed_quantity"])) == Decimal("3.5")
    assert Decimal(str(consume_data["remaining_stock"])) == Decimal("2.5")

    # Verificar qué lotes fueron afectados
    affected = {d["batch_id"]: d for d in consume_data["batches_affected"]}
    assert len(affected) == 2

    # Lote 1 se agotó completamente
    assert batch1_id in affected
    assert Decimal(str(affected[batch1_id]["quantity_deducted"])) == Decimal("2.0")
    assert affected[batch1_id]["batch_exhausted"] is True

    # Lote 2 se descontó parcialmente
    assert batch2_id in affected
    assert Decimal(str(affected[batch2_id]["quantity_deducted"])) == Decimal("1.5")
    assert affected[batch2_id]["batch_exhausted"] is False

    # Lote 3 quedó intacto
    assert batch3_id not in affected

    # 5. Intentar consumir más de lo que queda (pedir 10.0 L cuando solo quedan 2.5 L)
    over_res = await api_client.post(
        f"/api/v1/pantries/{pantry_id}/consume",
        json={"product_id": product_id, "quantity": 10.0},
        headers=headers,
    )
    assert over_res.status_code == 400
    assert over_res.json()["type"] == "https://despensa.api/errors/insufficient-stock"
