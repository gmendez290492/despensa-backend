"""Contratos estándar (EventEnvelope) y eventos de dominio."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    """Sobre estándar versionado para todos los eventos del sistema."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str = ""
    payload: dict[str, Any]


class UserRegisteredPayload(BaseModel):
    """Payload del evento user.registered.v1."""

    user_id: UUID
    email: str
    full_name: str
    timezone: str
