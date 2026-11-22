"""Modelos y repositorios para Patrón Outbox Transaccional e Idempotencia."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.events import EventEnvelope


class OutboxEvent(Base):
    """Tabla Outbox: almacena eventos dentro de la misma transacción de negocio."""

    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_envelope(self) -> EventEnvelope:
        """Convierte la fila Outbox al contrato EventEnvelope estándar."""
        return EventEnvelope(
            event_id=self.id,
            event_type=self.event_type,
            occurred_at=self.created_at,
            correlation_id=self.correlation_id,
            payload=self.payload,
        )


class ProcessedEvent(Base):
    """Registro de eventos procesados por consumidor (Idempotent Consumer)."""

    __tablename__ = "processed_events"

    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    consumer_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class OutboxRepository:
    """Acceso a datos para encolar y despachar eventos del Outbox."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def enqueue(
        self,
        *,
        event: EventEnvelope,
        aggregate_type: str,
        aggregate_id: str,
    ) -> OutboxEvent:
        """Agrega un evento a la sesión actual (se confirma con el commit del negocio)."""
        row = OutboxEvent(
            id=event.event_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event.event_type,
            payload=event.payload,
            correlation_id=event.correlation_id,
            status="pending",
            created_at=event.occurred_at,
        )
        self.session.add(row)
        return row

    async def fetch_pending_batch(self, limit: int = 50) -> Sequence[OutboxEvent]:
        """Obtiene eventos pendientes bloqueando filas para evitar doble publicación."""
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == "pending")
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def mark_published(self, event_id: UUID) -> None:
        """Marca un evento como publicado exitosamente."""
        stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(status="published", published_at=datetime.now(UTC), last_error=None)
        )
        await self.session.execute(stmt)

    async def mark_attempt_failed(
        self,
        *,
        event_id: UUID,
        error: str,
        max_attempts: int,
    ) -> None:
        """Incrementa intentos y marca como 'failed' si supera el máximo permitido."""
        row = await self.session.get(OutboxEvent, event_id)
        if row is None:
            return
        row.attempts += 1
        row.last_error = error[:1000]
        if row.attempts >= max_attempts:
            row.status = "failed"


class ProcessedEventRepository:
    """Control atómico de idempotencia en consumidores de eventos."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def try_claim(self, *, event_id: UUID, consumer_name: str) -> bool:
        """Intenta registrar el evento; retorna False si ya fue procesado antes."""
        stmt = (
            pg_insert(ProcessedEvent)
            .values(
                event_id=event_id,
                consumer_name=consumer_name,
                processed_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["event_id", "consumer_name"])
            .returning(ProcessedEvent.event_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
