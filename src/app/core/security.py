"""Utilidades de seguridad: hashing Argon2id, JWT y rate limiting."""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.core.exceptions import RateLimitExceededError

_password_hasher = PasswordHash.recommended()
_MIN_SECRET_LENGTH = 32


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Claims decodificados y validados de un token JWT."""

    user_id: UUID
    email: str
    token_type: Literal["access", "refresh"]
    jti: UUID
    expires_at: datetime


def hash_password(plain_password: str) -> str:
    """Genera un hash seguro usando Argon2id."""
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verifica en tiempo constante si la contraseña coincide con el hash."""
    return _password_hasher.verify(plain_password, password_hash)


def _require_valid_secret(secret_key: str) -> None:
    if len(secret_key) < _MIN_SECRET_LENGTH:
        raise RuntimeError(
            "JWT_SECRET_KEY debe configurarse con al menos 32 caracteres.",
        )


def _create_token(
    *,
    user_id: UUID,
    email: str,
    kind: Literal["access", "refresh"],
    secret_key: str,
    algorithm: str,
    expires_delta: timedelta,
) -> tuple[str, UUID, datetime]:
    _require_valid_secret(secret_key)
    now = datetime.now(UTC)
    expires_at = now + expires_delta
    jti = uuid4()

    payload = {
        "sub": str(user_id),
        "email": email,
        "type": kind,
        "jti": str(jti),
        "iat": now,
        "exp": expires_at,
    }
    encoded = jwt.encode(payload, secret_key, algorithm=algorithm)
    return encoded, jti, expires_at


def create_access_token(
    *,
    user_id: UUID,
    email: str,
    secret_key: str,
    algorithm: str,
    expire_minutes: int,
) -> str:
    """Crea un JWT de acceso de corta duración."""
    token, _, _ = _create_token(
        user_id=user_id,
        email=email,
        kind="access",
        secret_key=secret_key,
        algorithm=algorithm,
        expires_delta=timedelta(minutes=expire_minutes),
    )
    return token


def create_refresh_token(
    *,
    user_id: UUID,
    email: str,
    secret_key: str,
    algorithm: str,
    expire_days: int,
) -> tuple[str, UUID, datetime]:
    """Crea un JWT de refresco retornando token, jti y fecha de expiración."""
    return _create_token(
        user_id=user_id,
        email=email,
        kind="refresh",
        secret_key=secret_key,
        algorithm=algorithm,
        expires_delta=timedelta(days=expire_days),
    )


def decode_token(
    *,
    token: str,
    secret_key: str,
    algorithm: str,
    expected_type: Literal["access", "refresh"],
) -> TokenClaims:
    """Decodifica y valida firma, expiración y tipo esperado de un JWT."""
    _require_valid_secret(secret_key)
    raw = jwt.decode(
        token,
        secret_key,
        algorithms=[algorithm],
        options={"require": ["sub", "email", "type", "jti", "exp"]},
    )
    token_type = raw.get("type")
    if token_type != expected_type:
        raise jwt.InvalidTokenError("Tipo de token inválido.")

    return TokenClaims(
        user_id=UUID(str(raw["sub"])),
        email=str(raw["email"]),
        token_type=expected_type,
        jti=UUID(str(raw["jti"])),
        expires_at=datetime.fromtimestamp(float(raw["exp"]), tz=UTC),
    )


class InMemoryRateLimiter:
    """Limitador por ventana deslizante en memoria para proteger endpoints de auth."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        """Registra un intento y lanza RateLimitExceededError si supera el umbral."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        bucket = self._hits[key]

        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= self.max_attempts:
            raise RateLimitExceededError(
                "Demasiados intentos en poco tiempo. Intenta nuevamente en un minuto.",
            )

        bucket.append(now)

    def reset(self) -> None:
        """Limpia el estado (útil en pruebas automatizadas)."""
        self._hits.clear()
