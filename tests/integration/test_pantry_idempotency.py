"""Pruebas de integración del issue #11: Idempotency-Key en las mutaciones de pantry."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_db_session
from app.core.idempotency import IdempotencyKey
from app.modules.pantry.dependencies import get_pantry_service
from app.modules.pantry.models import FoodBatch, StockMovement
from app.modules.pantry.service import PantryService

PASSWORD = "PasswordSeguro123!"
REUSED = "https://despensa.api/errors/idempotency-key-reused"


@dataclass
class _Kitchen:
    headers: dict[str, str]
    pantry_id: str
    location_id: str
    product_id: str

    def with_key(self, key: str) -> dict[str, str]:
        return {**self.headers, "Idempotency-Key": key}


async def _kitchen(client: AsyncClient, *, stock: float | None = 5.0) -> _Kitchen:
    email = f"idem_{uuid4().hex[:8]}@example.com"
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Chef Idempotente"},
    )
    assert reg.status_code == 201, reg.text
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    pantry = await client.post("/api/v1/pantries", json={"name": "Cocina"}, headers=headers)
    pantry_id = pantry.json()["id"]
    locations = await client.get(f"/api/v1/pantries/{pantry_id}/locations", headers=headers)
    categories = await client.get("/api/v1/categories", headers=headers)
    product = await client.post(
        "/api/v1/products",
        json={
            "category_id": categories.json()[0]["id"],
            "name": f"Leche {uuid4().hex[:6]}",
            "base_unit_code": "l",
        },
        headers=headers,
    )
    kitchen = _Kitchen(
        headers=headers,
        pantry_id=pantry_id,
        location_id=locations.json()[0]["id"],
        product_id=product.json()["id"],
    )
    if stock is not None:
        res = await client.post(
            f"/api/v1/pantries/{pantry_id}/batches",
            json=_batch_body(kitchen, quantity=stock),
            headers=headers,
        )
        assert res.status_code == 201, res.text
    return kitchen


def _batch_body(kitchen: _Kitchen, *, quantity: float = 2.0) -> dict[str, Any]:
    return {
        "location_id": kitchen.location_id,
        "product_id": kitchen.product_id,
        "unit_code": "l",
        "quantity": quantity,
        "expiration_date": str(date.today() + timedelta(days=5)),
    }


async def _consume_movements(
    factory: async_sessionmaker[AsyncSession],
    product_id: str,
) -> int:
    async with factory() as session:
        stmt = (
            select(func.count())
            .select_from(StockMovement)
            .join(FoodBatch, FoodBatch.id == StockMovement.batch_id)
            .where(
                FoodBatch.product_id == UUID(product_id),
                StockMovement.movement_type == "consume",
            )
        )
        return int((await session.execute(stmt)).scalar_one())


async def _stock(client: AsyncClient, kitchen: _Kitchen) -> Decimal:
    res = await client.get(f"/api/v1/pantries/{kitchen.pantry_id}/batches", headers=kitchen.headers)
    return sum(
        (Decimal(str(b["current_quantity"])) for b in res.json()),
        Decimal("0"),
    )


async def test_consume_with_same_key_discounts_stock_once(
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    kitchen = await _kitchen(api_client)
    url = f"/api/v1/pantries/{kitchen.pantry_id}/consume"
    body = {"product_id": kitchen.product_id, "quantity": 1.5}

    first = await api_client.post(url, json=body, headers=kitchen.with_key("consume-key-0001"))
    retry = await api_client.post(url, json=body, headers=kitchen.with_key("consume-key-0001"))

    assert first.status_code == retry.status_code == 200
    assert retry.json() == first.json()
    assert retry.headers["Idempotent-Replayed"] == "true"
    assert "Idempotent-Replayed" not in first.headers
    assert await _stock(api_client, kitchen) == Decimal("3.5")
    assert await _consume_movements(db_session_factory, kitchen.product_id) == 1


async def test_batches_with_same_key_create_a_single_batch(api_client: AsyncClient) -> None:
    kitchen = await _kitchen(api_client, stock=None)
    url = f"/api/v1/pantries/{kitchen.pantry_id}/batches"
    headers = kitchen.with_key("batch-key-0001")

    first = await api_client.post(url, json=_batch_body(kitchen), headers=headers)
    retry = await api_client.post(url, json=_batch_body(kitchen), headers=headers)

    assert first.status_code == retry.status_code == 201
    assert retry.json()["id"] == first.json()["id"]
    listed = await api_client.get(url, headers=kitchen.headers)
    assert len(listed.json()) == 1


async def test_concurrent_requests_with_same_key_execute_once(
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """20 reintentos en paralelo: uno ejecuta; el resto repite su respuesta o recibe 409."""
    kitchen = await _kitchen(api_client)
    url = f"/api/v1/pantries/{kitchen.pantry_id}/consume"
    body = {"product_id": kitchen.product_id, "quantity": 1}
    headers = kitchen.with_key("parallel-key-0001")

    responses = await asyncio.gather(
        *(api_client.post(url, json=body, headers=headers) for _ in range(20)),
    )

    statuses = [r.status_code for r in responses]
    assert set(statuses) <= {200, 409}, statuses
    executed = [
        r for r in responses if r.status_code == 200 and "Idempotent-Replayed" not in r.headers
    ]
    assert len(executed) == 1
    for res in responses:
        if res.status_code == 409:
            assert res.headers["Retry-After"] == "1"
    assert await _stock(api_client, kitchen) == Decimal("4")
    assert await _consume_movements(db_session_factory, kitchen.product_id) == 1


async def test_same_key_with_different_request_returns_422(api_client: AsyncClient) -> None:
    kitchen = await _kitchen(api_client)
    url = f"/api/v1/pantries/{kitchen.pantry_id}/consume"
    headers = kitchen.with_key("reused-key-0001")

    ok = await api_client.post(
        url, json={"product_id": kitchen.product_id, "quantity": 1}, headers=headers
    )
    assert ok.status_code == 200

    other_body = await api_client.post(
        url,
        json={"product_id": kitchen.product_id, "quantity": 2},
        headers=headers,
    )
    assert other_body.status_code == 422
    assert other_body.json()["type"] == REUSED

    other_path = await api_client.post(
        f"/api/v1/pantries/{kitchen.pantry_id}/batches",
        json=_batch_body(kitchen),
        headers=headers,
    )
    assert other_path.status_code == 422
    assert other_path.json()["type"] == REUSED
    assert await _stock(api_client, kitchen) == Decimal("4")


async def test_keys_are_scoped_per_user(api_client: AsyncClient) -> None:
    """La misma clave en otro usuario se ejecuta aparte y no revela la respuesta ajena."""
    alice = await _kitchen(api_client)
    bob = await _kitchen(api_client)
    key = "shared-key-0001"

    res_alice = await api_client.post(
        f"/api/v1/pantries/{alice.pantry_id}/consume",
        json={"product_id": alice.product_id, "quantity": 1},
        headers=alice.with_key(key),
    )
    res_bob = await api_client.post(
        f"/api/v1/pantries/{bob.pantry_id}/consume",
        json={"product_id": bob.product_id, "quantity": 2},
        headers=bob.with_key(key),
    )

    assert res_alice.status_code == res_bob.status_code == 200
    assert "Idempotent-Replayed" not in res_bob.headers
    assert res_bob.json()["product_id"] == bob.product_id
    assert await _stock(api_client, alice) == Decimal("4")
    assert await _stock(api_client, bob) == Decimal("3")

    # Bob reutilizando la clave contra la despensa de Alice: 403, sin ver su respuesta.
    idor = await api_client.post(
        f"/api/v1/pantries/{alice.pantry_id}/consume",
        json={"product_id": alice.product_id, "quantity": 1},
        headers=bob.with_key("bob-probe-0001"),
    )
    assert idor.status_code == 403


async def test_business_error_is_replayed_even_if_state_changes(api_client: AsyncClient) -> None:
    """Un 400 insufficient-stock se repite igual, aunque luego entre stock."""
    kitchen = await _kitchen(api_client, stock=1.0)
    url = f"/api/v1/pantries/{kitchen.pantry_id}/consume"
    body = {"product_id": kitchen.product_id, "quantity": 3}
    headers = kitchen.with_key("insufficient-0001")

    first = await api_client.post(url, json=body, headers=headers)
    assert first.status_code == 400
    assert first.json()["type"] == "https://despensa.api/errors/insufficient-stock"

    await api_client.post(
        f"/api/v1/pantries/{kitchen.pantry_id}/batches",
        json=_batch_body(kitchen, quantity=5),
        headers=kitchen.headers,
    )
    retry = await api_client.post(url, json=body, headers=headers)

    assert retry.status_code == 400
    assert retry.headers["content-type"].startswith("application/problem+json")
    assert retry.headers["Idempotent-Replayed"] == "true"
    assert retry.json() == first.json()
    assert await _stock(api_client, kitchen) == Decimal("6")


async def test_server_error_releases_the_key(
    test_app: FastAPI,
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Un 5xx no se guarda: el reintento con la misma clave vuelve a ejecutarse."""
    kitchen = await _kitchen(api_client)
    url = f"/api/v1/pantries/{kitchen.pantry_id}/consume"
    body = {"product_id": kitchen.product_id, "quantity": 1}
    headers = kitchen.with_key("server-error-0001")

    class _Broken(PantryService):
        async def consume_product_fefo(self, *args: Any, **kwargs: Any) -> Any:
            await super().consume_product_fefo(*args, **kwargs)
            raise RuntimeError("fallo después del efecto")

    async def broken_service(
        session: Annotated[AsyncSession, Depends(get_db_session)],
    ) -> PantryService:
        return _Broken(session)

    test_app.dependency_overrides[get_pantry_service] = broken_service
    transport = ASGITransport(app=test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        failed = await client.post(url, json=body, headers=headers)
    assert failed.status_code == 500
    del test_app.dependency_overrides[get_pantry_service]

    assert await _stock(api_client, kitchen) == Decimal("5")  # el efecto se revirtió
    retry = await api_client.post(url, json=body, headers=headers)
    assert retry.status_code == 200
    assert "Idempotent-Replayed" not in retry.headers
    assert await _consume_movements(db_session_factory, kitchen.product_id) == 1


async def test_expired_key_is_executed_again(
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    kitchen = await _kitchen(api_client)
    url = f"/api/v1/pantries/{kitchen.pantry_id}/consume"
    body = {"product_id": kitchen.product_id, "quantity": 1}
    headers = kitchen.with_key("expired-key-0001")

    assert (await api_client.post(url, json=body, headers=headers)).status_code == 200
    async with db_session_factory() as session:
        await session.execute(
            update(IdempotencyKey)
            .where(IdempotencyKey.key == "expired-key-0001")
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
        )
        await session.commit()

    again = await api_client.post(url, json=body, headers=headers)
    assert again.status_code == 200
    assert "Idempotent-Replayed" not in again.headers
    assert await _stock(api_client, kitchen) == Decimal("3")


@pytest.mark.parametrize("key", ["short", "con espacios 123", "x" * 129, "clave.con.puntos"])
async def test_invalid_key_format_returns_400(api_client: AsyncClient, key: str) -> None:
    kitchen = await _kitchen(api_client, stock=None)
    res = await api_client.post(
        f"/api/v1/pantries/{kitchen.pantry_id}/batches",
        json=_batch_body(kitchen),
        headers=kitchen.with_key(key),
    )
    assert res.status_code == 400
    assert res.json()["type"] == "https://despensa.api/errors/invalid-idempotency-key"
    listed = await api_client.get(
        f"/api/v1/pantries/{kitchen.pantry_id}/batches",
        headers=kitchen.headers,
    )
    assert listed.json() == []


async def test_other_mutations_accept_the_key(api_client: AsyncClient) -> None:
    """POST /pantries, /pantries/join, /locations y /products también repiten la respuesta."""
    kitchen = await _kitchen(api_client, stock=None)
    pantry_a = await api_client.post(
        "/api/v1/pantries", json={"name": "Casa"}, headers=kitchen.with_key("pantry-key-0001")
    )
    pantry_b = await api_client.post(
        "/api/v1/pantries", json={"name": "Casa"}, headers=kitchen.with_key("pantry-key-0001")
    )
    assert pantry_a.status_code == pantry_b.status_code == 201
    assert pantry_a.json()["id"] == pantry_b.json()["id"]

    loc_url = f"/api/v1/pantries/{kitchen.pantry_id}/locations"
    for _ in range(2):
        res = await api_client.post(
            loc_url, json={"name": "Alacena"}, headers=kitchen.with_key("location-key-0001")
        )
        assert res.status_code == 201
    names = [loc["name"] for loc in (await api_client.get(loc_url, headers=kitchen.headers)).json()]
    assert names.count("Alacena") == 1

    friend = await _kitchen(api_client, stock=None)
    joins = [
        await api_client.post(
            "/api/v1/pantries/join",
            json={"invite_code": pantry_a.json()["invite_code"]},
            headers=friend.with_key("join-key-0001"),
        )
        for _ in range(2)
    ]
    # Sin idempotencia el segundo intento daría 409 already-pantry-member.
    assert [j.status_code for j in joins] == [200, 200]
    assert joins[1].headers["Idempotent-Replayed"] == "true"
