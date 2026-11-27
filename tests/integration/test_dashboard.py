"""Endpoint agregado del dashboard (issue #16): mismo contenido que las 4 lecturas sueltas."""

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.notifications.models import Notification
from tests.integration.test_pantry_and_fefo import get_auth_token_for_user


async def _setup(client: AsyncClient) -> tuple[dict[str, str], str]:
    token = await get_auth_token_for_user(client, f"dash_{uuid4().hex[:8]}@example.com", "Dash")
    headers = {"Authorization": f"Bearer {token}"}
    pantry_id = (
        await client.post("/api/v1/pantries", json={"name": "Panel"}, headers=headers)
    ).json()["id"]
    await client.post("/api/v1/pantries", json={"name": "Otra"}, headers=headers)
    location_id = (
        await client.get(f"/api/v1/pantries/{pantry_id}/locations", headers=headers)
    ).json()[0]["id"]
    category_id = (await client.get("/api/v1/categories", headers=headers)).json()[0]["id"]
    product_id = (
        await client.post(
            "/api/v1/products",
            json={
                "category_id": category_id,
                "name": f"Arroz {uuid4().hex[:6]}",
                "base_unit_code": "g",
            },
            headers=headers,
        )
    ).json()["id"]
    for days in (10, 2):
        res = await client.post(
            f"/api/v1/pantries/{pantry_id}/batches",
            json={
                "location_id": location_id,
                "product_id": product_id,
                "unit_code": "g",
                "quantity": 500,
                "expiration_date": str(date.today() + timedelta(days=days)),
            },
            headers=headers,
        )
        assert res.status_code == 201, res.text
    return headers, pantry_id


@pytest.mark.asyncio
async def test_dashboard_matches_the_individual_endpoints(api_client: AsyncClient) -> None:
    headers, pantry_id = await _setup(api_client)

    res = await api_client.get(f"/api/v1/pantries/{pantry_id}/dashboard", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()

    pantries = await api_client.get("/api/v1/pantries", headers=headers)
    locations = await api_client.get(f"/api/v1/pantries/{pantry_id}/locations", headers=headers)
    batches = await api_client.get(f"/api/v1/pantries/{pantry_id}/batches", headers=headers)
    notifications = await api_client.get("/api/v1/notifications", headers=headers)

    assert body["pantries"] == pantries.json()
    assert body["locations"] == locations.json()
    assert body["batches"] == batches.json()
    assert [b["dias_para_vencer"] for b in body["batches"]] == [2, 10]  # orden FEFO
    assert body["unread_notifications"] == notifications.json()["unread_count"]


@pytest.mark.asyncio
async def test_dashboard_counts_unread_notifications(
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers, pantry_id = await _setup(api_client)
    me = (await api_client.get("/api/v1/users/me", headers=headers)).json()
    async with db_session_factory() as session:
        for is_read in (False, False, True):
            session.add(
                Notification(
                    user_id=UUID(me["id"]),
                    pantry_id=UUID(pantry_id),
                    title="Caduca pronto",
                    message="Arroz vence en 2 días",
                    is_read=is_read,
                )
            )
        await session.commit()

    res = await api_client.get(f"/api/v1/pantries/{pantry_id}/dashboard", headers=headers)
    assert res.json()["unread_notifications"] == 2


@pytest.mark.asyncio
async def test_dashboard_denies_non_members(api_client: AsyncClient) -> None:
    _, pantry_id = await _setup(api_client)
    intruder = await get_auth_token_for_user(
        api_client, f"intruso_{uuid4().hex[:8]}@example.com", "Intruso"
    )

    res = await api_client.get(
        f"/api/v1/pantries/{pantry_id}/dashboard",
        headers={"Authorization": f"Bearer {intruder}"},
    )
    assert res.status_code == 403
    assert res.json()["type"].endswith("/pantry-access-denied")

    unknown = await api_client.get(
        f"/api/v1/pantries/{uuid4()}/dashboard",
        headers={"Authorization": f"Bearer {intruder}"},
    )
    assert unknown.status_code == 403  # no revela si la despensa existe


@pytest.mark.asyncio
async def test_dashboard_requires_auth(api_client: AsyncClient) -> None:
    res = await api_client.get(f"/api/v1/pantries/{uuid4()}/dashboard")
    assert res.status_code == 401
