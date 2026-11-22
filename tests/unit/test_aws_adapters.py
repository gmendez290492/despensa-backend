"""Pruebas unitarias para los adaptadores de AWS (SNS y SES)."""

from unittest.mock import MagicMock, patch

import pytest

from app.shared.adapters.aws_ses_email import AWSSESEmailSender
from app.shared.adapters.aws_sns import AWSSNSEventPublisher
from app.shared.events import EventEnvelope


@pytest.mark.asyncio
async def test_aws_sns_publisher_publishes_event_with_attributes() -> None:
    """Verifica que el publicador SNS envía el payload JSON y los atributos requeridos."""
    mock_boto_client = MagicMock()
    mock_boto_client.publish.return_value = {"MessageId": "sns-msg-12345"}

    with patch("boto3.client", return_value=mock_boto_client):
        publisher = AWSSNSEventPublisher(
            topic_arn="arn:aws:sns:us-east-1:123456789012:despensa-events-dev",
            region_name="us-east-1",
            endpoint_url="http://localhost:9297",
        )

        event = EventEnvelope(
            event_type="pantry.item_added.v1",
            payload={"product_name": "Manzanas", "quantity": 5},
            correlation_id="req-test-sns-001",
        )

        await publisher.publish(event)

        mock_boto_client.publish.assert_called_once()
        call_kwargs = mock_boto_client.publish.call_args.kwargs
        assert call_kwargs["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:despensa-events-dev"
        assert call_kwargs["Subject"] == "pantry.item_added.v1"
        msg_attrs = call_kwargs["MessageAttributes"]
        assert "pantry.item_added.v1" in msg_attrs["event_type"]["StringValue"]
        assert msg_attrs["correlation_id"]["StringValue"] == "req-test-sns-001"


@pytest.mark.asyncio
async def test_aws_ses_sender_dispatches_email() -> None:
    """Verifica que el emisor SES envía destinatario, asunto y cuerpos html/text."""
    mock_boto_client = MagicMock()
    mock_boto_client.send_email.return_value = {"MessageId": "ses-msg-67890"}

    with patch("boto3.client", return_value=mock_boto_client):
        sender = AWSSESEmailSender(
            from_email="no-reply@despensa.app",
            region_name="us-east-1",
            endpoint_url="http://localhost:9297",
        )

        await sender.send_email(
            to="chef@example.com",
            subject="Alerta de caducidad",
            html_body="<p>Tu leche caduca mañana</p>",
            text_body="Tu leche caduca mañana",
        )

        mock_boto_client.send_email.assert_called_once()
        call_kwargs = mock_boto_client.send_email.call_args.kwargs
        assert call_kwargs["Source"] == "no-reply@despensa.app"
        assert call_kwargs["Destination"]["ToAddresses"] == ["chef@example.com"]
        assert call_kwargs["Message"]["Subject"]["Data"] == "Alerta de caducidad"
        assert call_kwargs["Message"]["Body"]["Html"]["Data"] == "<p>Tu leche caduca mañana</p>"
        assert call_kwargs["Message"]["Body"]["Text"]["Data"] == "Tu leche caduca mañana"
