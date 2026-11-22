"""Adaptador SMTP asíncrono para envío de correos (Mailpit local o SMTP)."""

from email.message import EmailMessage

import aiosmtplib


class SMTPEmailSender:
    """Implementación del puerto EmailSender usando SMTP."""

    def __init__(self, *, host: str, port: int, from_email: str) -> None:
        self.host = host
        self.port = port
        self.from_email = from_email

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        """Envía un correo multipart (texto plano + HTML)."""
        msg = EmailMessage()
        msg["From"] = self.from_email
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        await aiosmtplib.send(msg, hostname=self.host, port=self.port)
