"""Consumidores idempotentes de eventos del módulo users."""

import html
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.users.repository import UserRepository
from app.modules.users.service import generate_password_reset_token
from app.shared.events import EventEnvelope, PasswordResetRequestedPayload
from app.shared.outbox import ProcessedEventRepository
from app.shared.ports import EmailSender

logger = structlog.get_logger(__name__)

PASSWORD_RESET_EMAIL_CONSUMER = "users.password_reset_email"  # noqa: S105  # nosec B105


class PasswordResetEmailHandler:
    """Procesa user.password_reset_requested.v1: genera el token y envía el enlace."""

    def __init__(
        self,
        session: AsyncSession,
        email_sender: EmailSender,
        settings: Settings,
    ) -> None:
        self.session = session
        self.email_sender = email_sender
        self.settings = settings
        self.users = UserRepository(session)
        self.processed_events = ProcessedEventRepository(session)

    async def handle(self, event: EventEnvelope) -> bool:
        """Emite un token de un solo uso y envía el correo. Retorna True si se envió."""
        claimed = await self.processed_events.try_claim(
            event_id=event.event_id,
            consumer_name=PASSWORD_RESET_EMAIL_CONSUMER,
        )
        if not claimed:
            logger.info(
                "duplicate_event_skipped",
                event_id=str(event.event_id),
                event_type=event.event_type,
                consumer=PASSWORD_RESET_EMAIL_CONSUMER,
            )
            return False

        payload = PasswordResetRequestedPayload.model_validate(event.payload)
        user = await self.users.get_by_id(payload.user_id)
        if user is None or not user.is_active:
            await self.session.commit()
            logger.info("password_reset_skipped_inactive_user", event_id=str(event.event_id))
            return False

        # Solo el último enlace solicitado es válido; se purgan los anteriores.
        await self.users.invalidate_password_reset_tokens(user.id)
        await self.users.delete_stale_password_reset_tokens(user.id)
        raw_token, token_hash = generate_password_reset_token()
        ttl_minutes = self.settings.password_reset_token_expire_minutes
        self.users.add_password_reset_token(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
        )
        await self.session.flush()

        base_url = self.settings.frontend_base_url.rstrip("/")
        reset_url = f"{base_url}/reset-password?token={raw_token}"
        safe_name = html.escape(user.full_name)
        safe_url = html.escape(reset_url, quote=True)
        subject = "Restablece tu contraseña de Despensa"
        text_body = (
            f"Hola {user.full_name},\n\n"
            "Recibimos una solicitud para restablecer tu contraseña. "
            f"Abre este enlace (válido por {ttl_minutes} minutos y de un solo uso):\n\n"
            f"{reset_url}\n\n"
            "Si no fuiste tú, ignora este correo: tu contraseña no cambiará.\n"
        )
        html_body = (
            f"<h2>Hola {safe_name}</h2>"
            "<p>Recibimos una solicitud para restablecer tu contraseña.</p>"
            f'<p><a href="{safe_url}">Restablecer contraseña</a></p>'
            f"<p>El enlace es válido por {ttl_minutes} minutos y solo puede usarse una vez.</p>"
            "<p>Si no fuiste tú, ignora este correo: tu contraseña no cambiará.</p>"
        )

        await self.email_sender.send_email(
            to=user.email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
        await self.session.commit()
        logger.info(
            "password_reset_email_sent",
            event_id=str(event.event_id),
            user_id=str(user.id),
            correlation_id=event.correlation_id,
        )
        return True
