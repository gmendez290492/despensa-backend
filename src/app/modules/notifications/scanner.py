"""Servicio de escaneo de caducidad de lotes con alertas e idempotencia estricta."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import ExpirationScanResponse
from app.modules.pantry.models import FoodBatch, Location, Pantry, PantryMember
from app.modules.users.models import User
from app.shared.outbox import ProcessedEventRepository
from app.shared.ports import EmailSender

logger = structlog.get_logger(__name__)


class ExpirationScanner:
    """Motor de detección de caducidad y emisión de alertas in-app y por email."""

    def __init__(
        self,
        session: AsyncSession,
        email_sender: EmailSender | None = None,
    ) -> None:
        self.session = session
        self.email_sender = email_sender
        self.processed_repo = ProcessedEventRepository(session)

    async def scan_expirations(
        self,
        *,
        reference_date: date | None = None,
    ) -> ExpirationScanResponse:
        """Escanea todos los lotes activos en todas las despensas y genera alertas sin duplicar."""
        # 1. Obtener todas las despensas con sus miembros y usuarios asociados
        pantries_stmt = select(Pantry).options(
            selectinload(Pantry.members).selectinload(PantryMember.user),
        )
        pantries = list((await self.session.execute(pantries_stmt)).scalars().all())

        scanned_pantries = len(pantries)
        evaluated_batches = 0
        alerts_generated = 0
        emails_sent = 0

        for pantry in pantries:
            # 2. Obtener lotes activos de la despensa
            batches_stmt = (
                select(FoodBatch)
                .join(Location, FoodBatch.location_id == Location.id)
                .where(
                    Location.pantry_id == pantry.id,
                    FoodBatch.current_quantity > 0,
                )
                .options(
                    selectinload(FoodBatch.product),
                    selectinload(FoodBatch.location),
                )
            )
            batches = list((await self.session.execute(batches_stmt)).scalars().all())

            for batch in batches:
                evaluated_batches += 1
                product_name = batch.product.name if batch.product else "Alimento"
                location_name = batch.location.name if batch.location else "Despensa"

                for member in pantry.members:
                    user: User = member.user

                    # Determinar la fecha actual local del usuario según su zona horaria
                    if reference_date is not None:
                        user_today = reference_date
                    else:
                        try:
                            user_tz = ZoneInfo(user.timezone)
                            user_today = datetime.now(user_tz).date()
                        except Exception:
                            user_today = datetime.now(UTC).date()

                    days_remaining = (batch.expiration_date - user_today).days
                    alert_days_threshold = user.alert_days_before

                    # Solo alertar si está vencido o dentro del umbral de alerta configurado
                    if days_remaining > alert_days_threshold:
                        continue

                    # Determinar tipo y texto de alerta
                    batch_info = f"'{product_name}' ({batch.current_quantity} {batch.unit_code})"
                    if days_remaining < 0:
                        notification_type = "EXPIRATION_SPOILED"
                        title = f"⚠️ Alimento vencido: {product_name}"
                        message = (
                            f"El lote de {batch_info} en {location_name} "
                            f"venció el {batch.expiration_date}."
                        )
                    elif days_remaining <= 2:
                        notification_type = "EXPIRATION_CRITICAL"
                        title = f"🚨 Caducidad crítica: {product_name}"
                        message = (
                            f"El lote de {batch_info} en {location_name} "
                            f"caduca en {days_remaining} día(s) ({batch.expiration_date}). "
                            "¡Consúmelo pronto!"
                        )
                    else:
                        notification_type = "EXPIRATION_ALERT"
                        title = f"⏳ Próximo a caducar: {product_name}"
                        message = (
                            f"El lote de {batch_info} en {location_name} "
                            f"vencerá en {days_remaining} días ({batch.expiration_date})."
                        )

                    # IDEMPOTENCIA: No notificar el mismo lote al mismo usuario el mismo día
                    claim_key = f"exp_alert:{user.id}:{user_today.isoformat()}"
                    claimed = await self.processed_repo.try_claim(
                        event_id=batch.id,
                        consumer_name=claim_key,
                    )
                    if not claimed:
                        # Ya fue notificado hoy para este lote
                        continue

                    # Crear notificación in-app
                    notification = Notification(
                        user_id=user.id,
                        pantry_id=pantry.id,
                        batch_id=batch.id,
                        title=title,
                        message=message,
                        notification_type=notification_type,
                    )
                    self.session.add(notification)
                    alerts_generated += 1

                    # Despachar correo electrónico si hay sender configurado
                    if self.email_sender:
                        try:
                            await self.email_sender.send_email(
                                to=user.email,
                                subject=title,
                                text_body=message,
                                html_body=f"<h3>{title}</h3><p>{message}</p>",
                            )
                            emails_sent += 1
                        except Exception as exc:
                            logger.error(
                                "expiration_email_failed",
                                user_id=str(user.id),
                                batch_id=str(batch.id),
                                error=str(exc),
                            )

        await self.session.commit()

        logger.info(
            "expiration_scan_completed",
            pantries=scanned_pantries,
            batches=evaluated_batches,
            alerts=alerts_generated,
            emails=emails_sent,
        )

        return ExpirationScanResponse(
            scanned_pantries=scanned_pantries,
            evaluated_batches=evaluated_batches,
            alerts_generated=alerts_generated,
            emails_sent=emails_sent,
        )
