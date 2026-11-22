"""Puertos (interfaces Protocol) para desacoplar adaptadores externos."""

from typing import Protocol

from app.shared.events import EventEnvelope


class EventPublisher(Protocol):
    """Puerto para publicar eventos hacia un broker (RabbitMQ local o SNS en AWS)."""

    async def publish(self, event: EventEnvelope) -> None:
        """Publica un evento al broker."""
        ...


class EmailSender(Protocol):
    """Puerto para envío de correos (Mailpit local o Amazon SES en AWS)."""

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        """Envía un correo electrónico."""
        ...
