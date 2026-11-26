"""Adaptador RabbitMQ para publicación y topología de eventos + DLQ."""

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractRobustConnection

from app.shared.events import EventEnvelope

EVENTS_EXCHANGE = "despensa.events"
DLX_EXCHANGE = "despensa.events.dlx"
WELCOME_EMAIL_QUEUE = "notifications.user_registered"
WELCOME_EMAIL_DLQ = "notifications.user_registered.dlq"
PASSWORD_RESET_QUEUE = "users.password_reset_requested"  # noqa: S105  # nosec B105


async def setup_rabbitmq_topology(channel: AbstractChannel) -> AbstractExchange:
    """Declara exchanges, colas durables y Dead Letter Queue (DLQ)."""
    events_exchange = await channel.declare_exchange(
        EVENTS_EXCHANGE,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )
    dlx_exchange = await channel.declare_exchange(
        DLX_EXCHANGE,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    dlq = await channel.declare_queue(WELCOME_EMAIL_DLQ, durable=True)
    await dlq.bind(dlx_exchange, routing_key="#")

    queue = await channel.declare_queue(
        WELCOME_EMAIL_QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": DLX_EXCHANGE},
    )
    await queue.bind(events_exchange, routing_key="user.registered.#")

    # Los mensajes rechazados terminan en la DLQ compartida (ligada con "#" al DLX).
    reset_queue = await channel.declare_queue(
        PASSWORD_RESET_QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": DLX_EXCHANGE},
    )
    await reset_queue.bind(events_exchange, routing_key="user.password_reset_requested.#")

    return events_exchange


class RabbitMQEventPublisher:
    """Implementación del puerto EventPublisher sobre RabbitMQ."""

    def __init__(self, rabbitmq_url: str) -> None:
        self.rabbitmq_url = rabbitmq_url
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None

    async def connect(self) -> None:
        """Inicializa conexión robusta y declara la topología."""
        self._connection = await aio_pika.connect_robust(self.rabbitmq_url)
        self._channel = await self._connection.channel()
        self._exchange = await setup_rabbitmq_topology(self._channel)

    async def close(self) -> None:
        """Cierra canal y conexión de forma ordenada."""
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()

    async def publish(self, event: EventEnvelope) -> None:
        """Publica un evento persistente usando event_type como routing key."""
        if self._exchange is None:
            await self.connect()
        if self._exchange is None:
            raise RuntimeError("RabbitMQ exchange no inicializado.")

        message = aio_pika.Message(
            body=event.model_dump_json().encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=str(event.event_id),
            correlation_id=event.correlation_id,
        )
        await self._exchange.publish(message, routing_key=event.event_type)
