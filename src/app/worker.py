"""Proceso Worker: ejecuta el Outbox Relay y los consumidores de eventos."""

import asyncio
import signal

import aio_pika
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.database import create_db_engine, create_session_factory
from app.core.logging import configure_logging
from app.modules.notifications.handlers import WelcomeEmailHandler
from app.shared.adapters.rabbitmq import (
    WELCOME_EMAIL_QUEUE,
    RabbitMQEventPublisher,
    setup_rabbitmq_topology,
)
from app.shared.adapters.smtp_email import SMTPEmailSender
from app.shared.events import EventEnvelope
from app.shared.outbox import OutboxRepository
from app.shared.ports import EmailSender, EventPublisher

logger = structlog.get_logger(__name__)


async def relay_outbox_once(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: EventPublisher,
    batch_size: int = 50,
    max_attempts: int = 5,
) -> int:
    """Despacha un lote de eventos pendientes desde la tabla Outbox hacia el broker."""
    published_count = 0

    async with session_factory() as session:
        repo = OutboxRepository(session)
        pending = await repo.fetch_pending_batch(limit=batch_size)
        if not pending:
            return 0

        for row in pending:
            envelope = row.to_envelope()
            try:
                await publisher.publish(envelope)
                await repo.mark_published(row.id)
                published_count += 1
                logger.info(
                    "outbox_event_published",
                    event_id=str(row.id),
                    event_type=row.event_type,
                    correlation_id=row.correlation_id,
                )
            except Exception as exc:
                logger.warning(
                    "outbox_event_publish_failed",
                    event_id=str(row.id),
                    event_type=row.event_type,
                    error=str(exc),
                )
                await repo.mark_attempt_failed(
                    event_id=row.id,
                    error=str(exc),
                    max_attempts=max_attempts,
                )

        await session.commit()

    return published_count


async def process_welcome_message(
    *,
    raw_body: bytes,
    session_factory: async_sessionmaker[AsyncSession],
    email_sender: EmailSender,
) -> bool:
    """Parsea un EventEnvelope y ejecuta el handler idempotente de bienvenida."""
    event = EventEnvelope.model_validate_json(raw_body)
    async with session_factory() as session:
        try:
            handler = WelcomeEmailHandler(session=session, email_sender=email_sender)
            return await handler.handle(event)
        except Exception:
            await session.rollback()
            raise


async def _outbox_relay_loop(
    *,
    stop_event: asyncio.Event,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: RabbitMQEventPublisher,
    settings: Settings,
) -> None:
    while not stop_event.is_set():
        try:
            processed = await relay_outbox_once(
                session_factory=session_factory,
                publisher=publisher,
                batch_size=settings.outbox_batch_size,
                max_attempts=settings.outbox_max_attempts,
            )
            if processed > 0:
                continue
        except Exception as exc:
            logger.error("outbox_relay_loop_error", error=str(exc))

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.outbox_poll_interval_seconds,
            )
        except TimeoutError:
            continue


async def _welcome_consumer_loop(
    *,
    stop_event: asyncio.Event,
    session_factory: async_sessionmaker[AsyncSession],
    email_sender: EmailSender,
    rabbitmq_url: str,
) -> None:
    connection = await aio_pika.connect_robust(rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)
        await setup_rabbitmq_topology(channel)
        queue = await channel.get_queue(WELCOME_EMAIL_QUEUE)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                if stop_event.is_set():
                    break
                try:
                    await process_welcome_message(
                        raw_body=message.body,
                        session_factory=session_factory,
                        email_sender=email_sender,
                    )
                    await message.ack()
                except Exception as exc:
                    logger.error(
                        "welcome_consumer_message_failed",
                        message_id=message.message_id,
                        error=str(exc),
                    )
                    # requeue=False envía el mensaje a la Dead Letter Queue (DLQ)
                    await message.nack(requeue=False)


async def run_worker() -> None:
    """Inicia el Relay del Outbox y los consumidores RabbitMQ hasta recibir señal de salida."""
    settings = get_settings()
    configure_logging(environment=settings.environment, log_level=settings.log_level)

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    publisher = RabbitMQEventPublisher(settings.rabbitmq_url)
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

    logger.info("worker_started", environment=settings.environment)
    try:
        await publisher.connect()
        await asyncio.gather(
            _outbox_relay_loop(
                stop_event=stop_event,
                session_factory=session_factory,
                publisher=publisher,
                settings=settings,
            ),
            _welcome_consumer_loop(
                stop_event=stop_event,
                session_factory=session_factory,
                email_sender=email_sender,
                rabbitmq_url=settings.rabbitmq_url,
            ),
        )
    finally:
        await publisher.close()
        await engine.dispose()
        logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
