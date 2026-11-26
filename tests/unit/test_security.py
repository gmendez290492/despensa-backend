"""Pruebas unitarias de seguridad (Argon2id, JWT y rate limiting)."""

from uuid import uuid4

import jwt
import pytest

from app.core.exceptions import RateLimitExceededError
from app.core.rate_limit import InMemoryRateLimiter, RateLimitPolicy, hash_identifier
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    reissue_refresh_token,
    verify_password,
)

TEST_SECRET = "test-secret-key-with-more-than-32-characters"


def test_argon2_hash_and_verify() -> None:
    """Verifica hashing Argon2id y validación correcta/incorrecta."""
    hashed = hash_password("MiClaveSegura123!")
    assert hashed != "MiClaveSegura123!"
    assert hashed.startswith("$argon2")
    assert verify_password("MiClaveSegura123!", hashed) is True
    assert verify_password("ClaveIncorrecta", hashed) is False


def test_access_token_roundtrip_and_type_enforcement() -> None:
    """Verifica creación, decodificación y rechazo de tipo incorrecto."""
    user_id = uuid4()
    session_id = uuid4()
    token = create_access_token(
        user_id=user_id,
        email="ana@despensa.test",
        session_id=session_id,
        secret_key=TEST_SECRET,
        algorithm="HS256",
        expire_minutes=15,
    )

    claims = decode_token(
        token=token,
        secret_key=TEST_SECRET,
        algorithm="HS256",
        expected_type="access",
    )
    assert claims.user_id == user_id
    assert claims.email == "ana@despensa.test"
    assert claims.token_type == "access"
    assert claims.session_id == session_id

    with pytest.raises(jwt.InvalidTokenError):
        decode_token(
            token=token,
            secret_key=TEST_SECRET,
            algorithm="HS256",
            expected_type="refresh",
        )


def test_refresh_token_rejects_expired_or_tampered() -> None:
    """Verifica rechazo de tokens expirados o manipulados."""
    user_id = uuid4()
    expired_token = create_refresh_token(
        user_id=user_id,
        email="ana@despensa.test",
        session_id=uuid4(),
        secret_key=TEST_SECRET,
        algorithm="HS256",
        expire_days=-1,
    ).token

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(
            token=expired_token,
            secret_key=TEST_SECRET,
            algorithm="HS256",
            expected_type="refresh",
        )

    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(
            token=expired_token,
            secret_key="otra-llave-completamente-diferente-32chars",
            algorithm="HS256",
            expected_type="refresh",
        )


def test_access_token_without_sid_is_rejected() -> None:
    """Un access token sin claim sid (emitido antes de las sesiones) ya no se acepta."""
    legacy = jwt.encode(
        {
            "sub": str(uuid4()),
            "email": "ana@despensa.test",
            "type": "access",
            "jti": str(uuid4()),
            "exp": 4102444800,
        },
        TEST_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_token(
            token=legacy,
            secret_key=TEST_SECRET,
            algorithm="HS256",
            expected_type="access",
        )


def test_reissue_refresh_token_is_byte_identical() -> None:
    """Re-firmar con los metadatos persistidos produce exactamente el mismo token."""
    user_id = uuid4()
    session_id = uuid4()
    issued = create_refresh_token(
        user_id=user_id,
        email="ana@despensa.test",
        session_id=session_id,
        secret_key=TEST_SECRET,
        algorithm="HS256",
        expire_days=7,
    )
    assert issued.issued_at.microsecond == 0

    again = reissue_refresh_token(
        user_id=user_id,
        email="ana@despensa.test",
        session_id=session_id,
        jti=issued.jti,
        issued_at=issued.issued_at,
        expires_at=issued.expires_at,
        secret_key=TEST_SECRET,
        algorithm="HS256",
    )
    assert again == issued.token


async def test_rate_limiter_blocks_after_max_attempts() -> None:
    """Verifica que el rate limiter bloquea al exceder el límite e informa Retry-After."""
    limiter = InMemoryRateLimiter()
    policy = RateLimitPolicy(name="login", max_attempts=3, window_seconds=60)
    for _ in range(3):
        await limiter.check("127.0.0.1", policy)

    with pytest.raises(RateLimitExceededError) as exc_info:
        await limiter.check("127.0.0.1", policy)
    assert 1 <= int(exc_info.value.headers["Retry-After"]) <= 60

    # Otra clave u otra política no comparten contador
    await limiter.check("10.0.0.2", policy)
    other = RateLimitPolicy(name="register", max_attempts=3, window_seconds=60)
    await limiter.check("127.0.0.1", other)


def test_hash_identifier_normalizes_and_hides_email() -> None:
    """Las claves por email no guardan el correo en claro y no distinguen mayúsculas."""
    hashed = hash_identifier(" Ana@Despensa.test ")
    assert hashed == hash_identifier("ana@despensa.test")
    assert "ana" not in hashed
    assert len(hashed) == 64
