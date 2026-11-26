"""Utilidades de seguridad: hashing Argon2id y emisión/validación de JWT."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

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
    session_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """Token firmado junto con los metadatos necesarios para persistirlo o re-firmarlo."""

    token: str
    jti: UUID
    issued_at: datetime
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


def _encode_token(
    *,
    user_id: UUID,
    email: str,
    kind: Literal["access", "refresh"],
    session_id: UUID,
    jti: UUID,
    issued_at: datetime,
    expires_at: datetime,
    secret_key: str,
    algorithm: str,
) -> str:
    """Firma un JWT. Con los mismos argumentos produce exactamente el mismo token (HS256)."""
    _require_valid_secret(secret_key)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": kind,
        "jti": str(jti),
        "sid": str(session_id),
        "iat": issued_at,
        "exp": expires_at,
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def _create_token(
    *,
    user_id: UUID,
    email: str,
    kind: Literal["access", "refresh"],
    session_id: UUID,
    secret_key: str,
    algorithm: str,
    expires_delta: timedelta,
) -> IssuedToken:
    # JWT serializa iat/exp en segundos enteros: truncar evita desajustes con lo persistido.
    issued_at = datetime.now(UTC).replace(microsecond=0)
    expires_at = issued_at + expires_delta
    jti = uuid4()
    token = _encode_token(
        user_id=user_id,
        email=email,
        kind=kind,
        session_id=session_id,
        jti=jti,
        issued_at=issued_at,
        expires_at=expires_at,
        secret_key=secret_key,
        algorithm=algorithm,
    )
    return IssuedToken(token=token, jti=jti, issued_at=issued_at, expires_at=expires_at)


def create_access_token(
    *,
    user_id: UUID,
    email: str,
    session_id: UUID,
    secret_key: str,
    algorithm: str,
    expire_minutes: int,
) -> str:
    """Crea un JWT de acceso de corta duración ligado a una sesión (claim sid)."""
    return _create_token(
        user_id=user_id,
        email=email,
        kind="access",
        session_id=session_id,
        secret_key=secret_key,
        algorithm=algorithm,
        expires_delta=timedelta(minutes=expire_minutes),
    ).token


def create_refresh_token(
    *,
    user_id: UUID,
    email: str,
    session_id: UUID,
    secret_key: str,
    algorithm: str,
    expire_days: int,
) -> IssuedToken:
    """Crea un JWT de refresco retornando token, jti y marcas de tiempo."""
    return _create_token(
        user_id=user_id,
        email=email,
        kind="refresh",
        session_id=session_id,
        secret_key=secret_key,
        algorithm=algorithm,
        expires_delta=timedelta(days=expire_days),
    )


def reissue_refresh_token(
    *,
    user_id: UUID,
    email: str,
    session_id: UUID,
    jti: UUID,
    issued_at: datetime,
    expires_at: datetime,
    secret_key: str,
    algorithm: str,
) -> str:
    """Re-firma un refresh token ya emitido (mismo jti/iat/exp) para devolver el mismo par."""
    return _encode_token(
        user_id=user_id,
        email=email,
        kind="refresh",
        session_id=session_id,
        jti=jti,
        issued_at=issued_at,
        expires_at=expires_at,
        secret_key=secret_key,
        algorithm=algorithm,
    )


def decode_token(
    *,
    token: str,
    secret_key: str,
    algorithm: str,
    expected_type: Literal["access", "refresh"],
) -> TokenClaims:
    """Decodifica y valida firma, expiración y tipo esperado de un JWT.

    Los access tokens deben incluir el claim ``sid`` (sesión) para poder revocarse en logout.
    Los refresh tokens anteriores a las sesiones no lo traen: su sesión sale de la BD.
    """
    _require_valid_secret(secret_key)
    required = ["sub", "email", "type", "jti", "exp"]
    if expected_type == "access":
        required.append("sid")
    raw = jwt.decode(
        token,
        secret_key,
        algorithms=[algorithm],
        options={"require": required},
    )
    token_type = raw.get("type")
    if token_type != expected_type:
        raise jwt.InvalidTokenError("Tipo de token inválido.")

    raw_sid = raw.get("sid")
    return TokenClaims(
        user_id=UUID(str(raw["sub"])),
        email=str(raw["email"]),
        token_type=expected_type,
        jti=UUID(str(raw["jti"])),
        expires_at=datetime.fromtimestamp(float(raw["exp"]), tz=UTC),
        session_id=UUID(str(raw_sid)) if raw_sid is not None else None,
    )
