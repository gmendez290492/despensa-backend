"""Pruebas de integración de Etapa 3: Notificaciones in-app, escáner de caducidad e idempotencia."""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient


async def _register_and_login(
    client: AsyncClient,
    email: str,
    name: str,
    alert_days: int = 5,
) -> tuple[str, str]:
    """Helper para registrar un usuario y obtener su user_id y access_token."""
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
async def test_notifications_lifecycle_and_mark_read(api_client: AsyncClient) -> None:
    """Verifica consulta de notificaciones, filtrado y marcado como leída."""
    _, token = await _register_and_login(
        api_client,
        f"notif_user_{uuid4().hex[:6]}@example.com",
        "Notif User",
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Inicialmente no tiene notificaciones
    list_res = await api_client.get("/api/v1/notifications", headers=headers)
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] == 0
    assert data["unread_count"] == 0
    assert data["items"] == []

    # 1. Crear despensa, producto y lote crítico para generar notificación
    p_res = await api_client.post(
        "/api/v1/pantries",
        json={"name": "Hogar Notif"},
        headers=headers,
    )
    pantry_id = p_res.json()["id"]

    loc_res = await api_client.get(f"/api/v1/pantries/{pantry_id}/locations", headers=headers)
    location_id = loc_res.json()[0]["id"]

    cat_res = await api_client.get("/api/v1/categories", headers=headers)
    category_id = cat_res.json()[0]["id"]

    prod_res = await api_client.post(
        "/api/v1/products",
        json={
            "category_id": category_id,
            "name": f"Yogurt {uuid4().hex[:4]}",
            "base_unit_code": "pza",
        },
        headers=headers,
    )
    product_id = prod_res.json()["id"]

    # Lote que vence mañana (dentro del umbral)
    await api_client.post(
        f"/api/v1/pantries/{pantry_id}/batches",
        json={
            "location_id": location_id,
            "product_id": product_id,
            "unit_code": "pza",
            "quantity": 3.0,
            "expiration_date": str(date.today() + timedelta(days=1)),
        },
        headers=headers,
    )

    # 2. Ejecutar escaneo de caducidad
    scan_res = await api_client.post("/api/v1/notifications/scan", headers=headers)
    assert scan_res.status_code == 200
    scan_data = scan_res.json()
    assert scan_data["alerts_generated"] >= 1

    # 3. Consultar listado de notificaciones
    list_res = await api_client.get("/api/v1/notifications", headers=headers)
    assert list_res.status_code == 200
    notifs = list_res.json()
    assert notifs["total"] >= 1
    assert notifs["unread_count"] >= 1

    first_notif = notifs["items"][0]
    notif_id = first_notif["id"]
    assert first_notif["is_read"] is False
    assert first_notif["notification_type"] == "EXPIRATION_CRITICAL"

    # 4. Marcar como leída
    read_res = await api_client.patch(
        f"/api/v1/notifications/{notif_id}/read",
        headers=headers,
    )
    assert read_res.status_code == 200
    assert read_res.json()["marked_count"] == 1

    # Verificar que ahora no hay no leídas
    unread_res = await api_client.get(
        "/api/v1/notifications?unread_only=true",
        headers=headers,
    )
    assert unread_res.status_code == 200
    assert unread_res.json()["unread_count"] == 0
    assert len(unread_res.json()["items"]) == 0

    # 5. Marcar notificación inexistente -> 404 Not Found (RFC 7807)
    fake_id = str(uuid4())
    err_res = await api_client.patch(
        f"/api/v1/notifications/{fake_id}/read",
        headers=headers,
    )
    assert err_res.status_code == 404
    assert err_res.json()["type"] == "https://despensa.api/errors/notification-not-found"


@pytest.mark.asyncio
async def test_expiration_scanner_idempotency_and_thresholds(
    api_client: AsyncClient,
) -> None:
    """Valida umbrales de alerta e idempotencia estricta en el escaneo de caducidad."""
    _, token = await _register_and_login(
        api_client,
        f"scanner_user_{uuid4().hex[:6]}@example.com",
        "Scanner User",
        alert_days=5,
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Crear despensa y obtener ubicación
    p_res = await api_client.post(
        "/api/v1/pantries",
        json={"name": "Cocina Scanner"},
        headers=headers,
    )
    pantry_id = p_res.json()["id"]

    loc_res = await api_client.get(f"/api/v1/pantries/{pantry_id}/locations", headers=headers)
    location_id = loc_res.json()[0]["id"]

    cat_res = await api_client.get("/api/v1/categories", headers=headers)
    category_id = cat_res.json()[0]["id"]

    # Crear producto
    prod_res = await api_client.post(
        "/api/v1/products",
        json={
            "category_id": category_id,
            "name": f"Pechuga de Pollo {uuid4().hex[:4]}",
            "base_unit_code": "kg",
        },
        headers=headers,
    )
    product_id = prod_res.json()["id"]

    today = date.today()

    # Lote 1: Vence en 1 día (CRÍTICO) -> Debe alertar
    await api_client.post(
        f"/api/v1/pantries/{pantry_id}/batches",
        json={
            "location_id": location_id,
            "product_id": product_id,
            "unit_code": "kg",
            "quantity": 1.5,
            "expiration_date": str(today + timedelta(days=1)),
        },
        headers=headers,
    )

    # Lote 2: Vence en 4 días (ALERTA, dentro de los 5 días) -> Debe alertar
    await api_client.post(
        f"/api/v1/pantries/{pantry_id}/batches",
        json={
            "location_id": location_id,
            "product_id": product_id,
            "unit_code": "kg",
            "quantity": 2.0,
            "expiration_date": str(today + timedelta(days=4)),
        },
        headers=headers,
    )

    # Lote 3: Vence en 20 días (LEJOS, > 5 días) -> NO debe alertar
    await api_client.post(
        f"/api/v1/pantries/{pantry_id}/batches",
        json={
            "location_id": location_id,
            "product_id": product_id,
            "unit_code": "kg",
            "quantity": 5.0,
            "expiration_date": str(today + timedelta(days=20)),
        },
        headers=headers,
    )

    # Lote 4: Venció ayer (VENCIDO / SPOILED) -> Debe alertar
    await api_client.post(
        f"/api/v1/pantries/{pantry_id}/batches",
        json={
            "location_id": location_id,
            "product_id": product_id,
            "unit_code": "kg",
            "quantity": 0.5,
            "expiration_date": str(today - timedelta(days=1)),
        },
        headers=headers,
    )

    # PRIMER ESCANEO: Debe generar exactamente 3 alertas (Lote 1, Lote 2, Lote 4)
    scan_res1 = await api_client.post("/api/v1/notifications/scan", headers=headers)
    assert scan_res1.status_code == 200
    assert scan_res1.json()["alerts_generated"] == 3

    # SEGUNDO ESCANEO (Inmediato): La idempotencia debe evitar duplicar las alertas de hoy
    scan_res2 = await api_client.post("/api/v1/notifications/scan", headers=headers)
    assert scan_res2.status_code == 200
    assert scan_res2.json()["alerts_generated"] == 0

    # Marcar todas como leídas en lote
    read_all_res = await api_client.patch(
        "/api/v1/notifications/read-all",
        headers=headers,
    )
    assert read_all_res.status_code == 200
    assert read_all_res.json()["marked_count"] == 3


@pytest.mark.asyncio
async def test_notifications_isolation_between_users(api_client: AsyncClient) -> None:
    """Verifica que un usuario nunca pueda ver ni manipular las notificaciones de otro."""
    _, token_a = await _register_and_login(
        api_client, f"user_a_{uuid4().hex[:6]}@example.com", "User A"
    )
    _, token_b = await _register_and_login(
        api_client, f"user_b_{uuid4().hex[:6]}@example.com", "User B"
    )

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Usuario A crea despensa y lote por caducar
    p_res = await api_client.post("/api/v1/pantries", json={"name": "Casa A"}, headers=headers_a)
    pantry_id = p_res.json()["id"]

    loc_res = await api_client.get(f"/api/v1/pantries/{pantry_id}/locations", headers=headers_a)
    location_id = loc_res.json()[0]["id"]

    cat_res = await api_client.get("/api/v1/categories", headers=headers_a)
    category_id = cat_res.json()[0]["id"]

    prod_res = await api_client.post(
        "/api/v1/products",
        json={"category_id": category_id, "name": f"Jugo {uuid4().hex[:4]}", "base_unit_code": "l"},
        headers=headers_a,
    )
    product_id = prod_res.json()["id"]

    await api_client.post(
        f"/api/v1/pantries/{pantry_id}/batches",
        json={
            "location_id": location_id,
            "product_id": product_id,
            "unit_code": "l",
            "quantity": 1.0,
            "expiration_date": str(date.today() + timedelta(days=1)),
        },
        headers=headers_a,
    )

    # Disparar escaneo
    await api_client.post("/api/v1/notifications/scan", headers=headers_a)

    # Usuario A ve su notificación
    notifs_a = (await api_client.get("/api/v1/notifications", headers=headers_a)).json()
    assert notifs_a["total"] == 1
    notif_id_a = notifs_a["items"][0]["id"]

    # Usuario B consulta notificaciones -> debe tener 0
    notifs_b = (await api_client.get("/api/v1/notifications", headers=headers_b)).json()
    assert notifs_b["total"] == 0

    # Usuario B intenta marcar como leída la notificación de A -> 404 Not Found
    attack_res = await api_client.patch(
        f"/api/v1/notifications/{notif_id_a}/read",
        headers=headers_b,
    )
    assert attack_res.status_code == 404
