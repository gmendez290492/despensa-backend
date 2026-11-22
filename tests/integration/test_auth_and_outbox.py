"""Pruebas de integración de Etapa 1: usuarios, JWT, RFC 7807, Outbox y RabbitMQ."""

import aio_pika
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.modules.users.models import User
from app.shared.adapters.rabbitmq import EVENTS_EXCHANGE, RabbitMQEventPublisher
from app.shared.outbox import OutboxEvent
from app.worker import process_welcome_message, relay_outbox_once


class _CapturingEmailSender:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        self.messages.append(
            {
                "to": to,
                "subject": subject,
                "html_body": html_body,
                "text_body": text_body,
            },
        )


async def test_register_persists_user_and_outbox_atomically(
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Registrar un usuario guarda User y OutboxEvent en la misma transacción."""
    response = await api_client.post(
        "/api/v1/auth/register",
        headers={"X-Correlation-ID": "req-etapa1-001"},
        json={
            "email": "Maria@Example.com",
            "password": "SuperPassword123!",
            "full_name": "Maria Perez",
            "timezone": "America/Mexico_City",
            "alert_days_before": 4,
        },
    )

    assert response.status_code == 201
    assert response.headers["X-Correlation-ID"] == "req-etapa1-001"
    body = response.json()
    assert body["email"] == "maria@example.com"
    assert "password_hash" not in body
    assert body["timezone"] == "America/Mexico_City"

    async with db_session_factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        outbox = (await session.execute(select(OutboxEvent))).scalar_one()

    assert user.email == "maria@example.com"
    assert outbox.event_type == "user.registered.v1"
    assert outbox.status == "pending"
    assert outbox.correlation_id == "req-etapa1-001"
    assert outbox.payload["email"] == "maria@example.com"


async def test_duplicate_email_returns_rfc7807_conflict(api_client: AsyncClient) -> None:
    """Un correo duplicado responde 409 en formato RFC 7807."""
    payload = {
        "email": "dup@example.com",
        "password": "SuperPassword123!",
        "full_name": "Usuario Uno",
    }
    first = await api_client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = await api_client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409
    assert second.headers["content-type"].startswith("application/problem+json")
    problem = second.json()
    assert problem["status"] == 409
    assert problem["type"].endswith("email-already-exists")


async def test_login_me_refresh_rotation_and_logout(api_client: AsyncClient) -> None:
    """Valida flujo completo JWT, rotación de refresh token y defensa ante reuso."""
    await api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "carlos@example.com",
            "password": "SuperPassword123!",
            "full_name": "Carlos Ruiz",
        },
    )

    bad_login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "carlos@example.com", "password": "wrong"},
    )
    assert bad_login.status_code == 401

    login_res = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "carlos@example.com", "password": "SuperPassword123!"},
    )
    assert login_res.status_code == 200
    tokens = login_res.json()
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]

    # /users/me sin token -> 401; con refresh token -> 401; con access token -> 200
    assert (await api_client.get("/api/v1/users/me")).status_code == 401
    assert (
        await api_client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {refresh}"},
        )
    ).status_code == 401

    me_res = await api_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "carlos@example.com"

    # Rotar refresh token
    rot_res = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert rot_res.status_code == 200
    new_refresh = rot_res.json()["refresh_token"]
    assert new_refresh != refresh

    # Reutilizar el refresh token antiguo falla y revoca la familia de tokens
    reuse_res = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert reuse_res.status_code == 401

    revoked_new = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh},
    )
    assert revoked_new.status_code == 401

    # Nuevo login y logout explícito
    login2 = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "carlos@example.com", "password": "SuperPassword123!"},
    )
    refresh2 = login2.json()["refresh_token"]
    logout_res = await api_client.post("/api/v1/auth/logout", json={"refresh_token": refresh2})
    assert logout_res.status_code == 204

    after_logout = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh2},
    )
    assert after_logout.status_code == 401


async def test_login_rate_limit_enforced(
    api_client: AsyncClient,
    test_settings: Settings,
) -> None:
    """Superar el límite de intentos por IP retorna 429 Too Many Requests."""
    for _ in range(test_settings.auth_rate_limit_max_attempts):
        res = await api_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong"},
        )
        assert res.status_code == 401

    blocked = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong"},
    )
    assert blocked.status_code == 429
    assert blocked.headers["content-type"].startswith("application/problem+json")


async def test_outbox_relay_rabbitmq_and_idempotent_welcome_email(
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    """Valida el flujo completo: API -> Outbox -> RabbitMQ -> Consumer idempotente."""
    # Prepara una cola temporal exclusiva ligada al exchange para capturar el evento sin competir
    conn = await aio_pika.connect_robust(test_settings.rabbitmq_url)
    publisher = RabbitMQEventPublisher(test_settings.rabbitmq_url)
    capturing_sender = _CapturingEmailSender()

    try:
        await publisher.connect()
        channel = await conn.channel()
        exchange = await channel.get_exchange(EVENTS_EXCHANGE)
        temp_queue = await channel.declare_queue(exclusive=True)
        await temp_queue.bind(exchange, routing_key="user.registered.#")

        reg = await api_client.post(
            "/api/v1/auth/register",
            json={
                "email": "evento@example.com",
                "password": "SuperPassword123!",
                "full_name": "Elena Evento",
            },
        )
        assert reg.status_code == 201

        published = await relay_outbox_once(
            session_factory=db_session_factory,
            publisher=publisher,
        )
        assert published == 1

        async with db_session_factory() as session:
            outbox_row = (await session.execute(select(OutboxEvent))).scalar_one()
            assert outbox_row.status == "published"
            assert outbox_row.published_at is not None

        message = await temp_queue.get(timeout=5)
        async with message.process():
            first = await process_welcome_message(
                raw_body=message.body,
                session_factory=db_session_factory,
                email_sender=capturing_sender,
            )
            second = await process_welcome_message(
                raw_body=message.body,
                session_factory=db_session_factory,
                email_sender=capturing_sender,
            )

        assert first is True
        assert second is False
        assert len(capturing_sender.messages) == 1
        assert capturing_sender.messages[0]["to"] == "evento@example.com"
    finally:
        await publisher.close()
        await conn.close()
