"""Proceso Worker: ejecuta el Outbox Relay y los consumidores de eventos.

Local usa RabbitMQ + SMTP (Mailpit). En AWS (MESSAGING_BACKEND=aws, EMAIL_BACKEND=ses)
publica el Outbox en SNS, consume la cola SQS de notificaciones y envía con SES.
"""

import asyncio
import signal
from collections.abc import Awaitable, Callable

import aio_pika
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.database import create_db_engine, create_session_factory
from app.core.logging import configure_logging
from app.modules.notifications.handlers import WelcomeEmailHandler
from app.modules.users.handlers import PasswordResetEmailHandler
from app.modules.users.service import PASSWORD_RESET_REQUESTED_EVENT
from app.shared.adapters.aws_ses_email import AWSSESEmailSender
from app.shared.adapters.aws_sns import AWSSNSEventPublisher
from app.shared.adapters.aws_sqs import AWSSQSConsumer, SQSMessage
from app.shared.adapters.rabbitmq import (
    PASSWORD_RESET_QUEUE,
    WELCOME_EMAIL_QUEUE,
    RabbitMQEventPublisher,
    setup_rabbitmq_topology,
)
from app.shared.adapters.smtp_email import SMTPEmailSender
from app.shared.events import EventEnvelope
from app.shared.outbox import OutboxRepository
from app.shared.ports import EmailSender, EventPublisher

logger = structlog.get_logger(__name__)

USER_REGISTERED_EVENT = "user.registered.v1"

MessageProcessor = Callable[[bytes], Awaitable[bool]]


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


async def process_password_reset_message(
    *,
    raw_body: bytes,
    session_factory: async_sessionmaker[AsyncSession],
    email_sender: EmailSender,
    settings: Settings,
) -> bool:
    """Parsea un EventEnvelope y ejecuta el handler idempotente de recuperación."""
    event = EventEnvelope.model_validate_json(raw_body)
    async with session_factory() as session:
        try:
            handler = PasswordResetEmailHandler(
                session=session,
                email_sender=email_sender,
                settings=settings,
            )
            return await handler.handle(event)
        except Exception:
            await session.rollback()
            raise


async def _outbox_relay_loop(
    *,
    stop_event: asyncio.Event,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: EventPublisher,
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


async def _consumer_loop(
    *,
    stop_event: asyncio.Event,
    rabbitmq_url: str,
    queue_name: str,
    process: MessageProcessor,
) -> None:
    connection = await aio_pika.connect_robust(rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)
        await setup_rabbitmq_topology(channel)
        queue = await channel.get_queue(queue_name)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                if stop_event.is_set():
                    break
                try:
                    await process(message.body)
                    await message.ack()
                except Exception as exc:
                    logger.error(
                        "consumer_message_failed",
                        queue=queue_name,
                        message_id=message.message_id,
                        error=str(exc),
                    )
                    # requeue=False envía el mensaje a la Dead Letter Queue (DLQ)
                    await message.nack(requeue=False)


async def handle_sqs_message(
    *,
    message: SQSMessage,
    consumer: AWSSQSConsumer,
    processors: dict[str, MessageProcessor],
) -> None:
    """Enruta un mensaje SQS por su event_type y lo borra solo si se procesó bien.

    Un fallo deja el mensaje en la cola: SQS lo reentrega tras el visibility timeout y,
    superado `maxReceiveCount`, lo mueve a la DLQ. Los handlers son idempotentes.
    """
    try:
        event = EventEnvelope.model_validate_json(message.body)
    except ValueError as exc:
        # Un cuerpo ilegible nunca se podrá procesar: se deja que acabe en la DLQ.
        logger.error("sqs_message_invalid", message_id=message.message_id, error=str(exc))
        return

    process = processors.get(event.event_type)
    if process is None:
        logger.info(
            "sqs_event_ignored",
            message_id=message.message_id,
            event_type=event.event_type,
        )
        await consumer.delete(message)
        return

    try:
        await process(message.body)
    except Exception as exc:
        logger.error(
            "consumer_message_failed",
            message_id=message.message_id,
            event_type=event.event_type,
            receive_count=message.receive_count,
            error=str(exc),
        )
        return
    await consumer.delete(message)


async def _sqs_consumer_loop(
    *,
    stop_event: asyncio.Event,
    consumer: AWSSQSConsumer,
    processors: dict[str, MessageProcessor],
    settings: Settings,
) -> None:
    while not stop_event.is_set():
        try:
            messages = await consumer.receive(
                max_messages=settings.sqs_max_messages,
                wait_time_seconds=settings.sqs_wait_time_seconds,
            )
        except Exception as exc:
            logger.error("sqs_receive_failed", error=str(exc))
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5)
            except TimeoutError:
                pass
            continue

        for message in messages:
            await handle_sqs_message(message=message, consumer=consumer, processors=processors)


def build_email_sender(settings: Settings) -> EmailSender:
    """SMTP (Mailpit) en local, Amazon SES en AWS."""
    if settings.email_backend == "ses":
        key_id, secret = settings.aws_static_credentials()
        return AWSSESEmailSender(
            from_email=settings.smtp_from_email,
            region_name=settings.aws_default_region,
            endpoint_url=settings.aws_endpoint_url,
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
        )
    return SMTPEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        from_email=settings.smtp_from_email,
    )


def build_processors(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    email_sender: EmailSender,
) -> dict[str, MessageProcessor]:
    """Handler de cada tipo de evento que consume el worker."""

    async def welcome(body: bytes) -> bool:
        return await process_welcome_message(
            raw_body=body,
            session_factory=session_factory,
            email_sender=email_sender,
        )

    async def password_reset(body: bytes) -> bool:
        return await process_password_reset_message(
            raw_body=body,
            session_factory=session_factory,
            email_sender=email_sender,
            settings=settings,
        )

    return {USER_REGISTERED_EVENT: welcome, PASSWORD_RESET_REQUESTED_EVENT: password_reset}


async def _run_rabbitmq(
    *,
    stop_event: asyncio.Event,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    processors: dict[str, MessageProcessor],
) -> None:
    publisher = RabbitMQEventPublisher(settings.rabbitmq_url)
    queues = {
        WELCOME_EMAIL_QUEUE: processors[USER_REGISTERED_EVENT],
        PASSWORD_RESET_QUEUE: processors[PASSWORD_RESET_REQUESTED_EVENT],
    }
    try:
        await publisher.connect()
        await asyncio.gather(
            _outbox_relay_loop(
                stop_event=stop_event,
                session_factory=session_factory,
                publisher=publisher,
                settings=settings,
            ),
            *(
                _consumer_loop(
                    stop_event=stop_event,
                    rabbitmq_url=settings.rabbitmq_url,
                    queue_name=queue_name,
                    process=process,
                )
                for queue_name, process in queues.items()
            ),
        )
    finally:
        await publisher.close()


async def _run_aws(
    *,
    stop_event: asyncio.Event,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    processors: dict[str, MessageProcessor],
) -> None:
    if not (settings.sns_topic_arn and settings.sqs_notifications_queue_url):
        raise RuntimeError("Faltan SNS_TOPIC_ARN o SQS_NOTIFICATIONS_QUEUE_URL.")
    key_id, secret = settings.aws_static_credentials()
    publisher = AWSSNSEventPublisher(
        topic_arn=settings.sns_topic_arn,
        region_name=settings.aws_default_region,
        endpoint_url=settings.aws_endpoint_url,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
    )
    consumer = AWSSQSConsumer(
        queue_url=settings.sqs_notifications_queue_url,
        region_name=settings.aws_default_region,
        endpoint_url=settings.aws_endpoint_url,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
    )
    await asyncio.gather(
        _outbox_relay_loop(
            stop_event=stop_event,
            session_factory=session_factory,
            publisher=publisher,
            settings=settings,
        ),
        _sqs_consumer_loop(
            stop_event=stop_event,
            consumer=consumer,
            processors=processors,
            settings=settings,
        ),
    )


async def run_worker() -> None:
    """Inicia el Relay del Outbox y los consumidores hasta recibir señal de salida."""
    settings = get_settings()
    configure_logging(environment=settings.environment, log_level=settings.log_level)

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    email_sender = build_email_sender(settings)
    processors = build_processors(
        settings=settings,
        session_factory=session_factory,
        email_sender=email_sender,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    logger.info(
        "worker_started",
        environment=settings.environment,
        messaging_backend=settings.messaging_backend,
        email_backend=settings.email_backend,
    )
    run = _run_aws if settings.messaging_backend == "aws" else _run_rabbitmq
    try:
        await run(
            stop_event=stop_event,
            settings=settings,
            session_factory=session_factory,
            processors=processors,
        )
    finally:
        await engine.dispose()
        logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
