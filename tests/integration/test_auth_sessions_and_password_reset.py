"""Pruebas de integración del issue #9: sesiones, logout, gracia de refresh,
rate limit compartido en PostgreSQL y recuperación de contraseña."""

import re
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.exceptions import RateLimitExceededError
from app.core.rate_limit import PostgresRateLimiter, RateLimitBucket, RateLimitPolicy
from app.modules.users.models import AuthSession, PasswordResetToken, RefreshToken
from app.modules.users.service import PASSWORD_RESET_REQUESTED_EVENT
from app.shared.outbox import OutboxEvent
from app.worker import process_password_reset_message

PASSWORD = "SuperPassword123!"


class _CapturingEmailSender:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def send_email(self, *, to: str, subject: str, html_body: str, text_body: str) -> None:
        self.messages.append({"to": to, "subject": subject, "text_body": text_body})


async def _register(client: AsyncClient, email: str) -> None:
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Usuario Prueba"},
    )
    assert res.status_code == 201, res.text


async def _login(
    client: AsyncClient,
    email: str,
    password: str = PASSWORD,
    binding: str | None = None,
) -> dict[str, str]:
    headers = {"X-Client-Binding": binding} if binding else {}
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body: dict[str, str] = res.json()
    return body


async def _me_status(client: AsyncClient, access: str) -> int:
    res = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access}"})
    return res.status_code


# --- S8: logout invalida el access token -----------------------------------------------


async def test_logout_invalidates_access_token_of_that_session_only(
    api_client: AsyncClient,
) -> None:
    """Tras logout, el access de esa sesión da 401; otra sesión del usuario sigue activa."""
    await _register(api_client, "logout@example.com")
    laptop = await _login(api_client, "logout@example.com")
    phone = await _login(api_client, "logout@example.com")
    assert await _me_status(api_client, laptop["access_token"]) == 200

    res = await api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": laptop["refresh_token"]},
    )
    assert res.status_code == 204

    assert await _me_status(api_client, laptop["access_token"]) == 401
    assert await _me_status(api_client, phone["access_token"]) == 200

    # Logout idempotente
    again = await api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": laptop["refresh_token"]},
    )
    assert again.status_code == 204


async def test_refresh_reuse_revokes_only_the_compromised_session(
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """El reuso de un refresh (sin binding) revoca su sesión, no las demás del usuario."""
    await _register(api_client, "reuse@example.com")
    victim = await _login(api_client, "reuse@example.com")
    other = await _login(api_client, "reuse@example.com")

    rotated = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": victim["refresh_token"]},
    )
    assert rotated.status_code == 200
    new_pair = rotated.json()

    reuse = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": victim["refresh_token"]},
    )
    assert reuse.status_code == 401

    # La sesión comprometida cae completa (refresh nuevo y access nuevo)
    assert (
        await api_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": new_pair["refresh_token"]},
        )
    ).status_code == 401
    assert await _me_status(api_client, new_pair["access_token"]) == 401

    # La otra sesión no se ve afectada
    assert await _me_status(api_client, other["access_token"]) == 200

    async with db_session_factory() as session:
        reasons = (await session.execute(select(AuthSession.revoked_reason))).scalars().all()
    assert sorted(r or "" for r in reasons) == ["", "refresh_reuse"]


# --- Ventana de gracia del refresh con X-Client-Binding --------------------------------


async def test_refresh_grace_window_returns_same_successor_with_binding(
    api_client: AsyncClient,
) -> None:
    """Con binding, el refresh anterior dentro de la gracia devuelve el mismo sucesor."""
    await _register(api_client, "grace@example.com")
    binding = "bff-session-binding-1234567890"
    tokens = await _login(api_client, "grace@example.com", binding=binding)
    headers = {"X-Client-Binding": binding}

    first = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
        headers=headers,
    )
    second = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
        headers=headers,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["refresh_token"] == first.json()["refresh_token"]
    assert await _me_status(api_client, second.json()["access_token"]) == 200

    # El sucesor sigue siendo válido y rota con normalidad
    third = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first.json()["refresh_token"]},
        headers=headers,
    )
    assert third.status_code == 200


async def test_refresh_binding_mismatch_is_rejected_without_revoking(
    api_client: AsyncClient,
) -> None:
    """Sin el binding correcto el refresh falla, pero la sesión legítima sigue viva."""
    await _register(api_client, "binding@example.com")
    binding = "bff-session-binding-abcdefghij"
    tokens = await _login(api_client, "binding@example.com", binding=binding)

    for headers in ({}, {"X-Client-Binding": "otro-valor-robado-0000000000"}):
        res = await api_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
            headers=headers,
        )
        assert res.status_code == 401

    ok = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"X-Client-Binding": binding},
    )
    assert ok.status_code == 200


async def test_refresh_reuse_after_grace_window_revokes_session(
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Pasada la ventana de gracia, el reuso (aun con binding) revoca la sesión."""
    await _register(api_client, "late@example.com")
    binding = "bff-session-binding-late-0000000"
    headers = {"X-Client-Binding": binding}
    tokens = await _login(api_client, "late@example.com", binding=binding)

    rotated = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
        headers=headers,
    )
    assert rotated.status_code == 200

    async with db_session_factory() as session:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.replaced_by_jti.is_not(None))
            .values(revoked_at=datetime.now(UTC) - timedelta(minutes=5)),
        )
        await session.commit()

    late = await api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
        headers=headers,
    )
    assert late.status_code == 401
    assert await _me_status(api_client, rotated.json()["access_token"]) == 401


# --- Rate limit compartido en PostgreSQL -----------------------------------------------


async def test_postgres_rate_limiter_is_shared_between_replicas(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Dos instancias (réplicas) comparten el contador; la purga borra buckets viejos."""
    replica_a = PostgresRateLimiter(db_session_factory)
    replica_b = PostgresRateLimiter(db_session_factory)
    policy = RateLimitPolicy(name="shared", max_attempts=3, window_seconds=60)

    await replica_a.check("10.0.0.1", policy)
    await replica_b.check("10.0.0.1", policy)
    await replica_a.check("10.0.0.1", policy)
    try:
        await replica_b.check("10.0.0.1", policy)
    except RateLimitExceededError as exc:
        assert 1 <= int(exc.headers["Retry-After"]) <= 60
    else:  # pragma: no cover - debe bloquear
        raise AssertionError("El cuarto intento debía bloquearse")

    async with db_session_factory() as session:
        session.add(RateLimitBucket(bucket_key="old:key", window_start=0, hits=9))
        await session.commit()

    purged = await replica_a.purge_expired(max_window_seconds=60)
    assert purged == 1


async def test_register_rate_limit_by_ip_returns_429_with_retry_after(
    api_client: AsyncClient,
    test_settings: Settings,
) -> None:
    """El registro tiene un límite por IP más estricto que login (mitiga enumeración)."""
    test_settings.register_rate_limit_max_attempts = 2
    await _register(api_client, "r1@example.com")
    await _register(api_client, "r2@example.com")

    blocked = await api_client.post(
        "/api/v1/auth/register",
        json={"email": "r3@example.com", "password": PASSWORD, "full_name": "Tercero"},
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


async def test_login_rate_limit_by_email_across_ips(
    test_app: FastAPI,
    test_settings: Settings,
) -> None:
    """El límite por email aplica aunque los intentos lleguen desde IPs distintas."""
    test_settings.auth_email_rate_limit_max_attempts = 3
    for ip in ("203.0.113.1", "203.0.113.2", "203.0.113.3", "203.0.113.4"):
        transport = ASGITransport(app=test_app, client=(ip, 5000))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/v1/auth/login",
                json={"email": "target@example.com", "password": "wrong-password"},
            )
            expected = 429 if ip.endswith(".4") else 401
            assert res.status_code == expected


async def test_client_ip_comes_from_forwarded_header_only_via_uvicorn(
    test_app: FastAPI,
    test_settings: Settings,
) -> None:
    """La app no confía en X-Forwarded-For por sí misma (lo resuelve uvicorn en el borde)."""
    test_settings.register_rate_limit_max_attempts = 1
    transport = ASGITransport(app=test_app, client=("198.51.100.7", 5000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _register(client, "fwd1@example.com")
        spoofed = await client.post(
            "/api/v1/auth/register",
            headers={"X-Forwarded-For": "1.2.3.4"},
            json={"email": "fwd2@example.com", "password": PASSWORD, "full_name": "Spoof"},
        )
    assert spoofed.status_code == 429


# --- Recuperación de contraseña --------------------------------------------------------


async def test_password_reset_full_flow(
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    """forgot -> worker genera token y envía correo -> reset -> sesiones revocadas."""
    await _register(api_client, "olvido@example.com")
    old_tokens = await _login(api_client, "olvido@example.com")

    unknown = await api_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "nadie@example.com"},
    )
    known = await api_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": "olvido@example.com"},
    )
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()

    async with db_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(OutboxEvent).where(
                        OutboxEvent.event_type == PASSWORD_RESET_REQUESTED_EVENT,
                    ),
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert "token" not in str(rows[0].payload).lower()  # el secreto no viaja por el Outbox

    sender = _CapturingEmailSender()
    raw_body = rows[0].to_envelope().model_dump_json().encode("utf-8")
    assert await process_password_reset_message(
        raw_body=raw_body,
        session_factory=db_session_factory,
        email_sender=sender,
        settings=test_settings,
    )
    # Reentrega del mismo evento: idempotente
    assert not await process_password_reset_message(
        raw_body=raw_body,
        session_factory=db_session_factory,
        email_sender=sender,
        settings=test_settings,
    )
    assert len(sender.messages) == 1
    assert sender.messages[0]["to"] == "olvido@example.com"
    match = re.search(r"/reset-password\?token=([\w-]+)", sender.messages[0]["text_body"])
    assert match is not None
    raw_token = match.group(1)

    async with db_session_factory() as session:
        stored = (await session.execute(select(PasswordResetToken))).scalar_one()
    assert stored.token_hash != raw_token

    reset = await api_client.post(
        "/api/v1/auth/password/reset",
        json={"token": raw_token, "new_password": "OtraClaveSegura456!"},
    )
    assert reset.status_code == 204

    # Un solo uso
    reused = await api_client.post(
        "/api/v1/auth/password/reset",
        json={"token": raw_token, "new_password": "TerceraClave789!"},
    )
    assert reused.status_code == 400
    assert reused.json()["type"].endswith("invalid-reset-token")

    # Todas las sesiones previas quedan revocadas
    assert await _me_status(api_client, old_tokens["access_token"]) == 401
    assert (
        await api_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_tokens["refresh_token"]},
        )
    ).status_code == 401

    bad = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "olvido@example.com", "password": PASSWORD},
    )
    assert bad.status_code == 401
    await _login(api_client, "olvido@example.com", password="OtraClaveSegura456!")


async def test_password_reset_rejects_expired_token(
    api_client: AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> None:
    """Un token expirado no permite cambiar la contraseña."""
    await _register(api_client, "expira@example.com")
    await api_client.post("/api/v1/auth/password/forgot", json={"email": "expira@example.com"})

    async with db_session_factory() as session:
        row = (
            await session.execute(
                select(OutboxEvent).where(OutboxEvent.event_type == PASSWORD_RESET_REQUESTED_EVENT),
            )
        ).scalar_one()
    sender = _CapturingEmailSender()
    await process_password_reset_message(
        raw_body=row.to_envelope().model_dump_json().encode("utf-8"),
        session_factory=db_session_factory,
        email_sender=sender,
        settings=test_settings,
    )
    match = re.search(r"token=([\w-]+)", sender.messages[0]["text_body"])
    assert match is not None

    async with db_session_factory() as session:
        await session.execute(
            update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)),
        )
        await session.commit()

    res = await api_client.post(
        "/api/v1/auth/password/reset",
        json={"token": match.group(1), "new_password": "OtraClaveSegura456!"},
    )
    assert res.status_code == 400
