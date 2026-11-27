"""Adaptador Amazon SQS para consumir los eventos que SNS reparte a las colas."""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import boto3  # type: ignore[import-untyped]


@dataclass(frozen=True, slots=True)
class SQSMessage:
    """Mensaje recibido de SQS, con el cuerpo ya desenvuelto del sobre de SNS."""

    message_id: str
    receipt_handle: str
    body: bytes
    receive_count: int


def unwrap_sns_body(raw_body: str) -> bytes:
    """Devuelve el EventEnvelope en JSON.

    Con `raw_message_delivery` el cuerpo ya es el evento. Sin él, SNS lo envuelve en una
    notificación (`{"Type": "Notification", "Message": "..."}`) y hay que extraerlo.
    """
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body.encode("utf-8")
    if isinstance(parsed, dict) and parsed.get("Type") == "Notification" and "Message" in parsed:
        return str(parsed["Message"]).encode("utf-8")
    return raw_body.encode("utf-8")


class AWSSQSConsumer:
    """Recibe y confirma mensajes de una cola SQS con long polling."""

    def __init__(
        self,
        *,
        queue_url: str,
        region_name: str = "us-east-1",
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        self.queue_url = queue_url
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = boto3.client(
                "sqs",
                region_name=self.region_name,
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
            )
        return self._client

    def _receive_sync(self, max_messages: int, wait_time_seconds: int) -> list[SQSMessage]:
        response: dict[str, Any] = self._get_client().receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_time_seconds,
            MessageSystemAttributeNames=["ApproximateReceiveCount"],
        )
        return [
            SQSMessage(
                message_id=item["MessageId"],
                receipt_handle=item["ReceiptHandle"],
                body=unwrap_sns_body(item["Body"]),
                receive_count=int(item.get("Attributes", {}).get("ApproximateReceiveCount", 1)),
            )
            for item in response.get("Messages", [])
        ]

    async def receive(self, *, max_messages: int, wait_time_seconds: int) -> list[SQSMessage]:
        """Long polling no bloqueante (en un hilo) de hasta `max_messages` mensajes."""
        return await asyncio.to_thread(self._receive_sync, max_messages, wait_time_seconds)

    async def delete(self, message: SQSMessage) -> None:
        """Confirma el mensaje. Si no se borra, reaparece tras el visibility timeout y,
        superado `maxReceiveCount`, SQS lo mueve a la DLQ."""
        await asyncio.to_thread(
            self._get_client().delete_message,
            QueueUrl=self.queue_url,
            ReceiptHandle=message.receipt_handle,
        )
