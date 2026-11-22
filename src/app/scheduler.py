"""Proceso Scheduler: ejecuta periódicamente escaneos de caducidad en segundo plano."""

import asyncio
import signal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.database import create_db_engine, create_session_factory
from app.core.logging import configure_logging
from app.modules.notifications.scanner import ExpirationScanner
from app.shared.adapters.smtp_email import SMTPEmailSender
from app.shared.ports import EmailSender

logger = structlog.get_logger(__name__)


async def run_expiration_scan_cycle(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    email_sender: EmailSender,
) -> None:
    """Ejecuta un ciclo completo de escaneo de caducidad."""
    async with session_factory() as session:
        scanner = ExpirationScanner(session=session, email_sender=email_sender)
        result = await scanner.scan_expirations()
        logger.info(
            "scheduler_cycle_completed",
            pantries=result.scanned_pantries,
            batches=result.evaluated_batches,
            alerts=result.alerts_generated,
            emails=result.emails_sent,
        )


async def run_scheduler() -> None:
    """Loop principal del planificador asíncrono con control de señales."""
    settings = get_settings()
    configure_logging(environment=settings.environment, log_level=settings.log_level)

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    email_sender = SMTPEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        from_email=settings.smtp_from_email,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    logger.info("scheduler_started", interval=settings.expiration_scan_interval_seconds)

    try:
        while not stop_event.is_set():
            try:
                await run_expiration_scan_cycle(
                    session_factory=session_factory,
                    email_sender=email_sender,
                )
            except Exception as exc:
                logger.error("scheduler_cycle_failed", error=str(exc))

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=settings.expiration_scan_interval_seconds,
                )
            except TimeoutError:
                continue
    finally:
        await engine.dispose()
        logger.info("scheduler_stopped")


if __name__ == "__main__":
    asyncio.run(run_scheduler())
