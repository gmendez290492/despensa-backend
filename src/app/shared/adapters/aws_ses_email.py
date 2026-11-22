"""Adaptador Amazon SES para envío de correos transaccionales en la nube."""

import asyncio
from typing import Any

import boto3  # type: ignore[import-untyped]
import structlog

logger = structlog.get_logger(__name__)


class AWSSESEmailSender:
    """Implementación del puerto EmailSender sobre Amazon Simple Email Service (SES)."""

    def __init__(
        self,
        *,
        from_email: str,
        region_name: str = "us-east-1",
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        self.from_email = from_email
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = boto3.client(
                "ses",
                region_name=self.region_name,
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
            )
        return self._client

    def _send_sync(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> dict[str, Any]:
        client = self._get_client()
        response: dict[str, Any] = client.send_email(
            Source=self.from_email,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": text_body, "Charset": "UTF-8"},
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                },
            },
        )
        return response

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        """Despacha el correo hacia Amazon SES asíncronamente."""
        try:
            response = await asyncio.to_thread(
                self._send_sync,
                to=to,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )
            message_id = response.get("MessageId", "unknown")
            logger.info("ses_email_sent", to=to, ses_message_id=message_id)
        except Exception as exc:
            logger.error("ses_email_failed", to=to, error=str(exc))
            raise
