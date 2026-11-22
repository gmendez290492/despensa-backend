"""Inyección de dependencias para el módulo de notificaciones y escaneo."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.modules.notifications.scanner import ExpirationScanner
from app.modules.notifications.service import NotificationService
from app.shared.adapters.smtp_email import SMTPEmailSender
from app.shared.ports import EmailSender


def get_email_sender(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmailSender:
    """Inyecta el emisor de correos SMTP configurado."""
    return SMTPEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        from_email=settings.smtp_from_email,
    )


async def get_notification_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NotificationService:
    """Inyecta la instancia de NotificationService con la sesión de BD activa."""
    return NotificationService(session)


async def get_expiration_scanner(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> ExpirationScanner:
    """Inyecta el motor de escaneo de caducidades."""
    return ExpirationScanner(session=session, email_sender=email_sender)


NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]
ExpirationScannerDep = Annotated[ExpirationScanner, Depends(get_expiration_scanner)]
