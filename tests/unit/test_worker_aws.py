"""Pruebas unitarias del worker sobre AWS: adaptador SQS, enrutado y configuración."""

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.shared.adapters.aws_ses_email import AWSSESEmailSender
from app.shared.adapters.aws_sqs import AWSSQSConsumer, SQSMessage, unwrap_sns_body
from app.shared.adapters.smtp_email import SMTPEmailSender
from app.shared.events import EventEnvelope
from app.worker import build_email_sender, handle_sqs_message

QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/despensa-notifications-queue-dev"


def _envelope(event_type: str) -> str:
    return EventEnvelope(event_type=event_type, payload={"user_id": "u-1"}).model_dump_json()


def _message(body: str, message_id: str = "m-1") -> SQSMessage:
    return SQSMessage(
        message_id=message_id,
        receipt_handle=f"rh-{message_id}",
        body=unwrap_sns_body(body),
        receive_count=1,
    )


class _FakeConsumer:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, message: SQSMessage) -> None:
        self.deleted.append(message.message_id)


# --- Adaptador SQS ------------------------------------------------------------------


def test_unwrap_sns_body_accepts_raw_and_wrapped_notifications() -> None:
    """Con raw delivery el cuerpo ya es el evento; sin él viene dentro de `Message`."""
    raw = _envelope("user.registered.v1")
    wrapped = json.dumps({"Type": "Notification", "Message": raw, "TopicArn": "arn:x"})

    assert unwrap_sns_body(raw) == raw.encode()
    assert unwrap_sns_body(wrapped) == raw.encode()
    assert unwrap_sns_body("no es json") == b"no es json"


async def test_sqs_consumer_long_polls_and_deletes_by_receipt_handle() -> None:
    """receive usa long polling y devuelve los cuerpos desenvueltos; delete usa el handle."""
    raw = _envelope("user.registered.v1")
    client = MagicMock()
    client.receive_message.return_value = {
        "Messages": [
            {
                "MessageId": "m-1",
                "ReceiptHandle": "rh-1",
                "Body": json.dumps({"Type": "Notification", "Message": raw}),
                "Attributes": {"ApproximateReceiveCount": "2"},
            },
        ],
    }

    with patch("boto3.client", return_value=client):
        consumer = AWSSQSConsumer(queue_url=QUEUE_URL)
        messages = await consumer.receive(max_messages=10, wait_time_seconds=20)
        await consumer.delete(messages[0])

    kwargs = client.receive_message.call_args.kwargs
    assert kwargs["QueueUrl"] == QUEUE_URL
    assert kwargs["WaitTimeSeconds"] == 20
    assert messages == [
        SQSMessage(message_id="m-1", receipt_handle="rh-1", body=raw.encode(), receive_count=2),
    ]
    client.delete_message.assert_called_once_with(QueueUrl=QUEUE_URL, ReceiptHandle="rh-1")


# --- Enrutado de mensajes ------------------------------------------------------------


async def test_handled_message_is_deleted_after_processing() -> None:
    consumer = _FakeConsumer()
    seen: list[bytes] = []

    async def process(body: bytes) -> bool:
        seen.append(body)
        return True

    message = _message(_envelope("user.registered.v1"))
    await handle_sqs_message(
        message=message,
        consumer=consumer,  # type: ignore[arg-type]
        processors={"user.registered.v1": process},
    )

    assert seen == [message.body]
    assert consumer.deleted == ["m-1"]


async def test_failed_message_is_kept_for_retry_and_dlq() -> None:
    """Si el handler falla no se borra: SQS lo reentrega y luego lo manda a la DLQ."""
    consumer = _FakeConsumer()

    async def process(body: bytes) -> bool:
        raise RuntimeError("SES caído")

    await handle_sqs_message(
        message=_message(_envelope("user.registered.v1")),
        consumer=consumer,  # type: ignore[arg-type]
        processors={"user.registered.v1": process},
    )

    assert consumer.deleted == []


async def test_event_without_handler_is_acknowledged() -> None:
    """La cola recibe eventos que este worker aún no maneja: se confirman y se ignoran."""
    consumer = _FakeConsumer()

    await handle_sqs_message(
        message=_message(_envelope("pantry.item_expiring_soon.v1")),
        consumer=consumer,  # type: ignore[arg-type]
        processors={},
    )

    assert consumer.deleted == ["m-1"]


async def test_unparseable_message_is_left_for_the_dlq() -> None:
    consumer = _FakeConsumer()

    await handle_sqs_message(
        message=_message("{roto"),
        consumer=consumer,  # type: ignore[arg-type]
        processors={},
    )

    assert consumer.deleted == []


# --- Configuración -------------------------------------------------------------------


def test_aws_messaging_backend_requires_topic_and_queue() -> None:
    with pytest.raises(ValidationError, match="SNS_TOPIC_ARN"):
        Settings(messaging_backend="aws", sns_topic_arn="arn:aws:sns:us-east-1:1:t")


def test_static_aws_credentials_only_against_an_emulator() -> None:
    """En ECS no se pasan las credenciales mock: boto3 usa las del rol de la tarea."""
    assert Settings(aws_endpoint_url=None).aws_static_credentials() == (None, None)
    emulated = Settings(aws_endpoint_url="http://localhost:9297")
    assert emulated.aws_static_credentials() == ("mock_key", "mock_secret")


def test_email_sender_follows_email_backend() -> None:
    assert isinstance(build_email_sender(Settings(email_backend="smtp")), SMTPEmailSender)
    ses = build_email_sender(Settings(email_backend="ses", aws_endpoint_url=None))
    assert isinstance(ses, AWSSESEmailSender)
    assert ses.aws_access_key_id is None
