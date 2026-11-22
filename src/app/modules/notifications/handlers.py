"""Consumidores idempotentes de eventos para el módulo de notificaciones."""

import html

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.events import EventEnvelope, UserRegisteredPayload
from app.shared.outbox import ProcessedEventRepository
from app.shared.ports import EmailSender

logger = structlog.get_logger(__name__)

WELCOME_EMAIL_CONSUMER = "notifications.welcome_email"


class WelcomeEmailHandler:
    """Procesa user.registered.v1 enviando un correo de bienvenida sin duplicados."""

    def __init__(self, session: AsyncSession, email_sender: EmailSender) -> None:
        self.session = session
        self.email_sender = email_sender
        self.processed_events = ProcessedEventRepository(session)

    async def handle(self, event: EventEnvelope) -> bool:
        """Ejecuta el envío de bienvenida de forma idempotente. Retorna True si se envió."""
        claimed = await self.processed_events.try_claim(
            event_id=event.event_id,
            consumer_name=WELCOME_EMAIL_CONSUMER,
        )
        if not claimed:
            logger.info(
                "duplicate_event_skipped",
                event_id=str(event.event_id),
                event_type=event.event_type,
                consumer=WELCOME_EMAIL_CONSUMER,
            )
            return False

        payload = UserRegisteredPayload.model_validate(event.payload)
        safe_name = html.escape(payload.full_name)

        subject = "¡Bienvenido a Despensa! Tu cuenta está lista"
        text_body = (
            f"Hola {payload.full_name},\n\n"
            "Tu cuenta en Despensa fue creada exitosamente. "
            "Pronto podrás registrar tus compras y recibir alertas antes de que caduquen.\n"
        )
        html_body = (
            f"<h2>¡Hola {safe_name}!</h2>"
            "<p>Tu cuenta en <strong>Despensa</strong> fue creada exitosamente.</p>"
            "<p>Pronto podrás registrar tus compras y recibir alertas antes de que caduquen.</p>"
        )

        await self.email_sender.send_email(
            to=payload.email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
        await self.session.commit()
        logger.info(
            "welcome_email_sent",
            event_id=str(event.event_id),
            user_id=str(payload.user_id),
            correlation_id=event.correlation_id,
        )
        return True
