"""Pruebas unitarias del handler de correo de bienvenida e idempotencia."""

from unittest.mock import AsyncMock
from uuid import uuid4

from app.modules.notifications.handlers import WelcomeEmailHandler
from app.shared.events import EventEnvelope, UserRegisteredPayload


class _FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        self.sent.append(
            {
                "to": to,
                "subject": subject,
                "html_body": html_body,
                "text_body": text_body,
            },
        )


async def test_welcome_handler_sends_escaped_email_once() -> None:
    """Verifica envío HTML escapado y omisión de eventos duplicados."""
    fake_session = AsyncMock()
    fake_sender = _FakeEmailSender()
    handler = WelcomeEmailHandler(session=fake_session, email_sender=fake_sender)

    # Primera vez: claim True -> envía; segunda vez: claim False -> omite
    handler.processed_events.try_claim = AsyncMock(side_effect=[True, False])  # type: ignore[method-assign]

    payload = UserRegisteredPayload(
        user_id=uuid4(),
        email="ana@example.com",
        full_name="Ana <script>alert(1)</script>",
        timezone="UTC",
    )
    event = EventEnvelope(
        event_type="user.registered.v1",
        correlation_id="corr-123",
        payload=payload.model_dump(mode="json"),
    )

    first_result = await handler.handle(event)
    second_result = await handler.handle(event)

    assert first_result is True
    assert second_result is False
    assert len(fake_sender.sent) == 1
    assert fake_sender.sent[0]["to"] == "ana@example.com"
    assert "<script>" not in fake_sender.sent[0]["html_body"]
    assert "&lt;script&gt;" in fake_sender.sent[0]["html_body"]
