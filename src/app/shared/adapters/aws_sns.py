"""Adaptador AWS SNS para publicación de eventos asíncronos en la nube y emulador."""

import asyncio
from typing import Any

import boto3  # type: ignore[import-untyped]
import structlog

from app.shared.events import EventEnvelope

logger = structlog.get_logger(__name__)


class AWSSNSEventPublisher:
    """Implementación del puerto EventPublisher sobre Amazon SNS."""

    def __init__(
        self,
        *,
        topic_arn: str,
        region_name: str = "us-east-1",
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        self.topic_arn = topic_arn
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = boto3.client(
                "sns",
                region_name=self.region_name,
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
            )
        return self._client

    def _publish_sync(self, event: EventEnvelope) -> dict[str, Any]:
        client = self._get_client()
        message_body = event.model_dump_json()
        attributes: dict[str, dict[str, str]] = {
            "event_type": {
                "DataType": "String",
                "StringValue": event.event_type,
            },
        }
        if event.correlation_id:
            attributes["correlation_id"] = {
                "DataType": "String",
                "StringValue": event.correlation_id,
            }

        response: dict[str, Any] = client.publish(
            TopicArn=self.topic_arn,
            Message=message_body,
            Subject=event.event_type,
            MessageAttributes=attributes,
        )
        return response

    async def publish(self, event: EventEnvelope) -> None:
        """Publica el evento en Amazon SNS usando un hilo de fondo no bloqueante."""
        try:
            response = await asyncio.to_thread(self._publish_sync, event)
            message_id = response.get("MessageId", "unknown")
            logger.info(
                "sns_event_published",
                event_id=str(event.event_id),
                event_type=event.event_type,
                sns_message_id=message_id,
                topic_arn=self.topic_arn,
            )
        except Exception as exc:
            logger.error(
                "sns_event_publish_failed",
                event_id=str(event.event_id),
                event_type=event.event_type,
                error=str(exc),
            )
            raise
