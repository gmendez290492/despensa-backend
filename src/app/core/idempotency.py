"""Idempotencia de mutaciones HTTP con la cabecera `Idempotency-Key`.

Sigue el borrador IETF `draft-ietf-httpapi-idempotency-key-header`:

- La clave pertenece al usuario autenticado: `(user_id, key)` es único.
- Se inserta al **principio** de la transacción de la petición. Una petición concurrente con
  la misma clave queda esperando en el índice único hasta que la primera confirma (y entonces
  repite su respuesta) o revierte (y entonces se ejecuta ella). Si espera más de
  `IDEMPOTENCY_LOCK_TIMEOUT_MS`, recibe `409 idempotency-request-in-progress`.
- El efecto y la respuesta guardada se confirman en el **mismo commit**: no hay hueco en el
  que el efecto exista sin su respuesta.
- Los errores de negocio 4xx se guardan y se repiten. Los 5xx no: la clave se libera.
"""

import hashlib
import json
import re
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Protocol, TypeVar
from uuid import UUID

import structlog
from fastapi import Depends, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import Settings, get_settings
from app.core.database import Base, get_db_session
from app.core.exceptions import DomainError, RateLimitExceededError, problem_details

logger = structlog.get_logger(__name__)

ResponseT = TypeVar("ResponseT", bound=BaseModel)

IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9_-]{8,128}$"
_KEY_RE = re.compile(IDEMPOTENCY_KEY_PATTERN)
REPLAYED_HEADER = "Idempotent-Replayed"
_LOCK_NOT_AVAILABLE = "55P03"
_PURGE_ONE_IN = 100  # purga oportunista de claves caducadas en ~1 % de las claves nuevas


class IdempotencyKey(Base):
    """Respuesta registrada para una clave de idempotencia de un usuario."""

    __tablename__ = "idempotency_keys"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(512))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class InvalidIdempotencyKeyError(DomainError):
    """La cabecera Idempotency-Key no cumple el formato permitido."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "invalid-idempotency-key"
    title = "Invalid Idempotency Key"


class IdempotencyKeyReusedError(DomainError):
    """La clave ya se usó con otra petición (otro cuerpo, ruta o método)."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_type = "idempotency-key-reused"
    title = "Idempotency Key Reused"


class IdempotencyRequestInProgressError(DomainError):
    """Otra petición con la misma clave sigue en curso."""

    status_code = status.HTTP_409_CONFLICT
    error_type = "idempotency-request-in-progress"
    title = "Idempotency Request In Progress"

    def __init__(self, detail: str, *, retry_after_seconds: int = 1) -> None:
        super().__init__(detail)
        self.headers["Retry-After"] = str(retry_after_seconds)


# Errores que nunca se guardan: son del propio mecanismo o transitorios para el cliente.
_NOT_REPLAYABLE: tuple[type[DomainError], ...] = (
    InvalidIdempotencyKeyError,
    IdempotencyKeyReusedError,
    IdempotencyRequestInProgressError,
    RateLimitExceededError,
)


class DeferrableCommit(Protocol):
    """Servicio capaz de aplazar su commit para que lo haga el guardián de idempotencia."""

    defer_commit: bool


_CLAIM_SQL = text(
    """
    INSERT INTO idempotency_keys
        (user_id, key, method, path, request_hash, status, response_status, response_body,
         created_at, expires_at)
    VALUES
        (:user_id, :key, :method, :path, :request_hash, :status, :response_status,
         CAST(:response_body AS JSONB), :now, :expires_at)
    ON CONFLICT (user_id, key) DO UPDATE SET
        method = EXCLUDED.method,
        path = EXCLUDED.path,
        request_hash = EXCLUDED.request_hash,
        status = EXCLUDED.status,
        response_status = EXCLUDED.response_status,
        response_body = EXCLUDED.response_body,
        created_at = EXCLUDED.created_at,
        expires_at = EXCLUDED.expires_at
    WHERE idempotency_keys.expires_at <= EXCLUDED.created_at
    RETURNING key
    """,
)

_SELECT_SQL = text(
    """
    SELECT request_hash, status, response_status, response_body
    FROM idempotency_keys
    WHERE user_id = :user_id AND key = :key
    """,
)

_COMPLETE_SQL = text(
    """
    UPDATE idempotency_keys
    SET status = 'completed', response_status = :response_status,
        response_body = CAST(:response_body AS JSONB)
    WHERE user_id = :user_id AND key = :key
    """,
)

_PURGE_SQL = text(
    """
    DELETE FROM idempotency_keys
    WHERE ctid IN (SELECT ctid FROM idempotency_keys WHERE expires_at < :now LIMIT 1000)
    """,
)


def request_fingerprint(*, method: str, path: str, payload: BaseModel | None) -> str:
    """SHA-256 de método, ruta y cuerpo canónico (JSON con claves ordenadas)."""
    body = payload.model_dump(mode="json") if payload is not None else None
    canonical = json.dumps(
        {"method": method.upper(), "path": path, "body": body},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_lock_timeout(exc: DBAPIError) -> bool:
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate is None and orig is not None:
        cause = getattr(orig, "__cause__", None)
        sqlstate = getattr(cause, "sqlstate", None)
    return sqlstate == _LOCK_NOT_AVAILABLE


@dataclass(frozen=True, slots=True)
class _StoredResponse:
    status_code: int
    body: dict[str, Any]


class IdempotencyGuard:
    """Ejecuta una mutación como máximo una vez por `(usuario, Idempotency-Key)`."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        request: Request,
        settings: Settings,
        key: str | None,
    ) -> None:
        self.session = session
        self.request = request
        self.settings = settings
        if key is not None and not _KEY_RE.fullmatch(key):
            raise InvalidIdempotencyKeyError(
                "Idempotency-Key debe tener entre 8 y 128 caracteres [A-Za-z0-9_-].",
            )
        self.key = key

    async def run(
        self,
        *,
        user_id: UUID,
        payload: BaseModel | None,
        status_code: int,
        service: DeferrableCommit,
        action: Callable[[], Awaitable[ResponseT]],
    ) -> ResponseT | JSONResponse:
        """Ejecuta `action` o, si la clave ya tiene respuesta, la repite sin ejecutar nada.

        Sin cabecera Idempotency-Key se ejecuta tal cual (comportamiento previo).
        """
        if self.key is None:
            return await action()

        fingerprint = request_fingerprint(
            method=self.request.method,
            path=self.request.url.path,
            payload=payload,
        )
        stored = await self._claim(user_id=user_id, fingerprint=fingerprint)
        if stored is not None:
            return self._replay(stored)

        service.defer_commit = True
        try:
            result = await action()
        except DomainError as exc:
            await self.session.rollback()  # deshace el efecto parcial y libera la clave
            if not isinstance(exc, _NOT_REPLAYABLE):
                await self._store_error(user_id=user_id, fingerprint=fingerprint, exc=exc)
            raise
        except Exception:
            await self.session.rollback()  # 5xx: la clave queda libre para reintentar
            raise
        finally:
            service.defer_commit = False

        await self.session.execute(
            _COMPLETE_SQL,
            {
                "user_id": user_id,
                "key": self.key,
                "response_status": status_code,
                "response_body": result.model_dump_json(),
            },
        )
        await self.session.commit()  # efecto + respuesta guardada, en un único commit
        return result

    async def _claim(self, *, user_id: UUID, fingerprint: str) -> _StoredResponse | None:
        """Reserva la clave en la transacción actual o devuelve la respuesta ya guardada."""
        now = datetime.now(UTC)
        # lock_timeout solo para esperar a otra petición con la misma clave; luego se restaura.
        previous_timeout = (
            await self.session.execute(
                text(
                    "SELECT current_setting('lock_timeout') AS prev, "
                    "set_config('lock_timeout', :timeout, true)",
                ),
                {"timeout": f"{int(self.settings.idempotency_lock_timeout_ms)}ms"},
            )
        ).scalar_one()
        try:
            claimed = await self.session.execute(
                _CLAIM_SQL,
                self._row(
                    user_id=user_id,
                    fingerprint=fingerprint,
                    now=now,
                    status_value="in_progress",
                ),
            )
        except DBAPIError as exc:
            if not _is_lock_timeout(exc):
                raise
            await self.session.rollback()
            raise IdempotencyRequestInProgressError(
                "Hay otra petición en curso con esta Idempotency-Key. Reintenta en breve.",
                retry_after_seconds=1,
            ) from exc
        await self.session.execute(
            text("SELECT set_config('lock_timeout', :timeout, true)"),
            {"timeout": previous_timeout},
        )

        if claimed.scalar_one_or_none() is not None:
            if secrets.randbelow(_PURGE_ONE_IN) == 0:
                await self.session.execute(_PURGE_SQL, {"now": now})
            return None

        row = (await self.session.execute(_SELECT_SQL, {"user_id": user_id, "key": self.key})).one()
        await self.session.rollback()  # no se va a ejecutar nada en esta petición
        if row.request_hash != fingerprint:
            raise IdempotencyKeyReusedError(
                "Esta Idempotency-Key ya se usó con una petición distinta.",
            )
        if row.status != "completed" or row.response_status is None:
            raise IdempotencyRequestInProgressError(
                "Hay otra petición en curso con esta Idempotency-Key. Reintenta en breve.",
            )
        return _StoredResponse(status_code=row.response_status, body=row.response_body or {})

    async def _store_error(self, *, user_id: UUID, fingerprint: str, exc: DomainError) -> None:
        """Guarda un error de negocio 4xx para repetirlo ante reintentos."""
        body = problem_details(self.request, exc)
        params = self._row(
            user_id=user_id,
            fingerprint=fingerprint,
            now=datetime.now(UTC),
            status_value="completed",
        )
        params.update(response_status=exc.status_code, response_body=json.dumps(body))
        try:
            await self.session.execute(_CLAIM_SQL, params)
            await self.session.commit()
        except Exception as store_exc:
            # Si no se puede guardar, el reintento volverá a ejecutar la validación (seguro:
            # el efecto se revirtió). Nunca se oculta el error de negocio original.
            await self.session.rollback()
            logger.warning("idempotency_error_not_stored", error=str(store_exc))

    def _row(
        self,
        *,
        user_id: UUID,
        fingerprint: str,
        now: datetime,
        status_value: str,
    ) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "key": self.key,
            "method": self.request.method.upper(),
            "path": self.request.url.path,
            "request_hash": fingerprint,
            "status": status_value,
            "response_status": None,
            "response_body": None,
            "now": now,
            "expires_at": now + timedelta(hours=self.settings.idempotency_key_ttl_hours),
        }

    def _replay(self, stored: _StoredResponse) -> JSONResponse:
        is_problem = stored.status_code >= 400
        logger.info(
            "idempotent_request_replayed",
            path=self.request.url.path,
            status_code=stored.status_code,
        )
        return JSONResponse(
            status_code=stored.status_code,
            content=stored.body,
            media_type="application/problem+json" if is_problem else "application/json",
            headers={REPLAYED_HEADER: "true"},
        )


async def get_idempotency_guard(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description=(
                "Clave única por operación (p. ej. UUID v4). Reenviar la misma clave con el "
                "mismo cuerpo devuelve la respuesta original sin repetir el efecto, con la "
                f"cabecera `{REPLAYED_HEADER}: true`. Caduca a las "
                "IDEMPOTENCY_KEY_TTL_HOURS horas (168 por defecto)."
            ),
            json_schema_extra={"pattern": IDEMPOTENCY_KEY_PATTERN},
        ),
    ] = None,
) -> IdempotencyGuard:
    """Guardián de idempotencia de la petición (comparte la sesión con el servicio)."""
    return IdempotencyGuard(
        session=session, request=request, settings=settings, key=idempotency_key
    )


IdempotencyDep = Annotated[IdempotencyGuard, Depends(get_idempotency_guard)]


def _problem(error_types: str) -> dict[str, Any]:
    return {
        "application/problem+json": {
            "schema": {
                "type": "object",
                "description": f"RFC 7807. `type` termina en: {error_types}.",
                "properties": {
                    "type": {"type": "string", "format": "uri"},
                    "title": {"type": "string"},
                    "status": {"type": "integer"},
                    "detail": {"type": "string"},
                    "instance": {"type": "string"},
                    "correlation_id": {"type": ["string", "null"]},
                },
            },
        },
    }


# Respuestas de error que añade Idempotency-Key, para documentarlas en OpenAPI.
IDEMPOTENCY_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        "description": "Error de negocio o `invalid-idempotency-key` (formato de la clave).",
        "content": _problem("`invalid-idempotency-key` o el error de negocio del endpoint"),
    },
    status.HTTP_409_CONFLICT: {
        "description": (
            "`idempotency-request-in-progress`: otra petición con la misma clave sigue en "
            "curso. Incluye `Retry-After`; es transitorio y se debe reintentar con la misma clave."
        ),
        "content": _problem("`idempotency-request-in-progress`"),
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "description": (
            "Cuerpo inválido (application/json) o `idempotency-key-reused`: la clave ya se usó "
            "con otra petición (application/problem+json)."
        ),
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/HTTPValidationError"},
            },
            **_problem("`idempotency-key-reused`"),
        },
    },
}
