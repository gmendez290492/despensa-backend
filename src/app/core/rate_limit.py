"""Rate limiting por ventana deslizante con backends en memoria y PostgreSQL.

El backend PostgreSQL comparte los contadores entre réplicas y sobrevive a reinicios,
por lo que es el recomendado fuera de las pruebas unitarias.
"""

import hashlib
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import BigInteger, Integer, String, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.exceptions import RateLimitExceededError

_RATE_LIMIT_DETAIL = "Demasiados intentos en poco tiempo. Intenta nuevamente más tarde."


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """Límite de intentos permitidos dentro de una ventana de tiempo."""

    name: str
    max_attempts: int
    window_seconds: int


def hash_identifier(value: str) -> str:
    """Seudonimiza identificadores (p. ej. emails) para no guardar PII en las claves."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


class RateLimiter(Protocol):
    """Puerto de rate limiting usado por los endpoints de autenticación."""

    async def check(self, key: str, policy: RateLimitPolicy) -> None:
        """Registra un intento y lanza RateLimitExceededError si supera la política."""
        ...


class InMemoryRateLimiter:
    """Ventana deslizante exacta en memoria. No se comparte entre procesos."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def check(self, key: str, policy: RateLimitPolicy) -> None:
        """Registra un intento y lanza RateLimitExceededError si supera el umbral."""
        now = time.monotonic()
        cutoff = now - policy.window_seconds
        bucket = self._hits[f"{policy.name}:{key}"]

        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= policy.max_attempts:
            retry_after = math.ceil(bucket[0] + policy.window_seconds - now)
            raise RateLimitExceededError(_RATE_LIMIT_DETAIL, retry_after_seconds=retry_after)

        bucket.append(now)

    def reset(self) -> None:
        """Limpia el estado (útil en pruebas automatizadas)."""
        self._hits.clear()


class RateLimitBucket(Base):
    """Contador de intentos por clave y ventana fija (epoch alineado a la ventana)."""

    __tablename__ = "rate_limit_buckets"

    bucket_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    window_start: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# Incremento atómico (UPSERT) del bucket actual y lectura del anterior en un solo viaje.
# Se usa el reloj de PostgreSQL para que todas las réplicas compartan la misma referencia.
_HIT_SQL = text(
    """
    WITH clock AS (
        SELECT EXTRACT(EPOCH FROM clock_timestamp())::double precision AS now_s
    ),
    current_bucket AS (
        INSERT INTO rate_limit_buckets (bucket_key, window_start, hits)
        SELECT CAST(:bucket_key AS varchar),
               (floor(clock.now_s / CAST(:window_seconds AS double precision))
                * CAST(:window_seconds AS bigint))::bigint,
               1
        FROM clock
        ON CONFLICT (bucket_key, window_start)
        DO UPDATE SET hits = rate_limit_buckets.hits + 1
        RETURNING hits, window_start
    )
    SELECT current_bucket.hits,
           current_bucket.window_start,
           clock.now_s,
           COALESCE(
               (
                   SELECT previous.hits
                   FROM rate_limit_buckets AS previous
                   WHERE previous.bucket_key = CAST(:bucket_key AS varchar)
                     AND previous.window_start
                         = current_bucket.window_start - CAST(:window_seconds AS bigint)
               ),
               0
           ) AS previous_hits
    FROM current_bucket, clock
    """,
)

_PURGE_SQL = text(
    """
    DELETE FROM rate_limit_buckets
    WHERE window_start < EXTRACT(EPOCH FROM clock_timestamp())::bigint
                         - CAST(:max_age_seconds AS bigint)
    """,
)


class PostgresRateLimiter:
    """Ventana deslizante aproximada (dos ventanas fijas ponderadas) en PostgreSQL.

    Cada intento hace un UPSERT atómico, así que es seguro con varias réplicas.
    Los intentos rechazados también cuentan: un atacante insistente sigue bloqueado.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_window_seconds: int = 3600,
        purge_every: int = 500,
    ) -> None:
        self._session_factory = session_factory
        self._max_window_seconds = max_window_seconds
        self._purge_every = purge_every
        self._calls = 0

    async def check(self, key: str, policy: RateLimitPolicy) -> None:
        """Registra un intento y lanza RateLimitExceededError si supera el umbral."""
        async with self._session_factory() as session:
            result = await session.execute(
                _HIT_SQL,
                {
                    "bucket_key": f"{policy.name}:{key}"[:160],
                    "window_seconds": policy.window_seconds,
                },
            )
            hits, window_start, now_s, previous_hits = result.one()
            await session.commit()

        # Limpieza autocontenida: no depende de que haya un scheduler desplegado.
        self._calls += 1
        if self._purge_every > 0 and self._calls % self._purge_every == 0:
            await self.purge_expired(max_window_seconds=self._max_window_seconds)

        elapsed = float(now_s) - float(window_start)
        previous_weight = max(0.0, 1.0 - elapsed / policy.window_seconds)
        estimated = previous_hits * previous_weight + hits
        if estimated > policy.max_attempts:
            retry_after = math.ceil(float(window_start) + policy.window_seconds - float(now_s))
            raise RateLimitExceededError(_RATE_LIMIT_DETAIL, retry_after_seconds=retry_after)

    async def purge_expired(self, *, max_window_seconds: int) -> int:
        """Elimina buckets que ya no influyen en ninguna ventana (2x la ventana máxima)."""
        async with self._session_factory() as session:
            result = await session.execute(
                _PURGE_SQL,
                {"max_age_seconds": max_window_seconds * 2},
            )
            await session.commit()
            return int(getattr(result, "rowcount", 0) or 0)
