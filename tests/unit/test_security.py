"""Pruebas unitarias de seguridad (Argon2id, JWT y rate limiting)."""

from uuid import uuid4

import jwt
import pytest

from app.core.exceptions import RateLimitExceededError
from app.core.security import (
    InMemoryRateLimiter,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
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
    token = create_access_token(
        user_id=user_id,
        email="ana@despensa.test",
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
    expired_token, _, _ = create_refresh_token(
        user_id=user_id,
        email="ana@despensa.test",
        secret_key=TEST_SECRET,
        algorithm="HS256",
        expire_days=-1,
    )

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


def test_rate_limiter_blocks_after_max_attempts() -> None:
    """Verifica que el rate limiter bloquea al exceder el límite."""
    limiter = InMemoryRateLimiter(max_attempts=3, window_seconds=60)
    limiter.check("login:127.0.0.1")
    limiter.check("login:127.0.0.1")
    limiter.check("login:127.0.0.1")

    with pytest.raises(RateLimitExceededError):
        limiter.check("login:127.0.0.1")
