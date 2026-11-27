"""Lógica de negocio y motor FEFO del módulo pantry con protección IDOR."""

import secrets
from datetime import date
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pantry.exceptions import (
    AlreadyPantryMemberError,
    InsufficientStockError,
    InvalidInviteCodeError,
    LocationNotFoundError,
    PantryAccessDeniedError,
    ProductNotFoundError,
    UnitNotFoundError,
)
from app.modules.pantry.models import Location, Pantry, PantryMember, Product
from app.modules.pantry.repository import PantryRepository
from app.modules.pantry.schemas import (
    BatchConsumeDetail,
    ConsumeRequest,
    ConsumeResultResponse,
    FoodBatchCreateRequest,
    FoodBatchResponse,
    LocationCreateRequest,
    PantryCreateRequest,
    ProductCreateRequest,
)
from app.shared.events import EventEnvelope
from app.shared.outbox import OutboxRepository


def calcular_semaforo(dias: int) -> Literal["VENCIDO", "CRÍTICO", "PRECAUCIÓN", "ÓPTIMO"]:
    """Clasifica el estado de caducidad del alimento según los días restantes."""
    if dias <= 0:
        return "VENCIDO"
    if 1 <= dias <= 3:
        return "CRÍTICO"
    if 4 <= dias <= 7:
        return "PRECAUCIÓN"
    return "ÓPTIMO"


class PantryService:
    """Casos de uso de despensas, inventario por lotes y algoritmo FEFO."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.pantry_repo = PantryRepository(session)
        self.outbox_repo = OutboxRepository(session)
        # Con Idempotency-Key, el guardián hace el commit junto con la respuesta guardada.
        self.defer_commit = False

    async def _commit(self) -> None:
        if self.defer_commit:
            await self.session.flush()
        else:
            await self.session.commit()

    async def assert_membership(self, *, pantry_id: UUID, user_id: UUID) -> PantryMember:
        """Escudo IDOR: garantiza que el usuario pertenece a la despensa consultada."""
        member = await self.pantry_repo.get_member(pantry_id=pantry_id, user_id=user_id)
        if member is None:
            raise PantryAccessDeniedError("Acceso denegado: no eres miembro de esta despensa.")
        return member

    async def create_pantry(
        self,
        data: PantryCreateRequest,
        *,
        user_id: UUID,
        correlation_id: str = "",
    ) -> Pantry:
        """Crea una despensa nueva, asigna al creador como 'owner' y crea ubicación inicial."""
        invite_code = f"DESP-{secrets.token_hex(4).upper()}"
        pantry = await self.pantry_repo.create_pantry(name=data.name, invite_code=invite_code)

        # 1. Asignar creador como OWNER
        await self.pantry_repo.add_member(pantry_id=pantry.id, user_id=user_id, role="owner")

        # 2. Crear ubicación inicial obligatoria ("Refrigerador")
        await self.pantry_repo.create_location(
            pantry_id=pantry.id,
            name="Refrigerador",
            description="Zona refrigerada principal",
        )

        # 3. Encolar evento outbox
        event = EventEnvelope(
            event_type="pantry.created.v1",
            correlation_id=correlation_id,
            payload={"pantry_id": str(pantry.id), "name": pantry.name, "owner_id": str(user_id)},
        )
        self.outbox_repo.enqueue(
            event=event,
            aggregate_type="pantry",
            aggregate_id=str(pantry.id),
        )

        await self._commit()
        return pantry

    async def join_pantry(
        self,
        invite_code: str,
        *,
        user_id: UUID,
        correlation_id: str = "",
    ) -> Pantry:
        """Permite a un usuario unirse a una despensa compartida usando el código de invitación."""
        pantry = await self.pantry_repo.get_pantry_by_invite_code(invite_code)
        if pantry is None:
            raise InvalidInviteCodeError("El código de invitación ingresado no existe.")

        existing_member = await self.pantry_repo.get_member(pantry_id=pantry.id, user_id=user_id)
        if existing_member is not None:
            raise AlreadyPantryMemberError("Ya eres miembro de esta despensa.")

        await self.pantry_repo.add_member(pantry_id=pantry.id, user_id=user_id, role="member")

        event = EventEnvelope(
            event_type="pantry.member_joined.v1",
            correlation_id=correlation_id,
            payload={"pantry_id": str(pantry.id), "user_id": str(user_id), "role": "member"},
        )
        self.outbox_repo.enqueue(
            event=event,
            aggregate_type="pantry",
            aggregate_id=str(pantry.id),
        )

        await self._commit()
        return pantry

    async def list_my_pantries(self, user_id: UUID) -> list[Pantry]:
        """Lista todas las despensas en las que participa el usuario."""
        pantries = await self.pantry_repo.list_user_pantries(user_id)
        return list(pantries)

    async def create_location(
        self,
        pantry_id: UUID,
        data: LocationCreateRequest,
        *,
        user_id: UUID,
    ) -> Location:
        """Crea una zona física tras validar membresía (IDOR)."""
        await self.assert_membership(pantry_id=pantry_id, user_id=user_id)
        location = await self.pantry_repo.create_location(
            pantry_id=pantry_id,
            name=data.name,
            description=data.description,
        )
        await self._commit()
        return location

    async def list_locations(self, pantry_id: UUID, *, user_id: UUID) -> list[Location]:
        """Lista las zonas de una despensa tras validar membresía."""
        await self.assert_membership(pantry_id=pantry_id, user_id=user_id)
        locations = await self.pantry_repo.list_locations_by_pantry(pantry_id)
        return list(locations)

    async def create_product(self, data: ProductCreateRequest) -> Product:
        """Registra un producto maestro en el catálogo."""
        unit = await self.pantry_repo.get_unit(data.base_unit_code)
        if unit is None:
            raise UnitNotFoundError(f"La unidad '{data.base_unit_code}' no existe en el catálogo.")

        category = await self.pantry_repo.get_category(data.category_id)
        if category is None:
            raise ProductNotFoundError("La categoría seleccionada no existe.")

        product = await self.pantry_repo.create_product(
            category_id=data.category_id,
            name=data.name,
            base_unit_code=data.base_unit_code,
            barcode=data.barcode,
            estimated_shelf_life_days=data.estimated_shelf_life_days,
        )
        await self._commit()
        return product

    async def add_food_batch(
        self,
        pantry_id: UUID,
        data: FoodBatchCreateRequest,
        *,
        user_id: UUID,
        correlation_id: str = "",
    ) -> FoodBatchResponse:
        """Registra un lote físico validando pertenencia a la despensa (3NF e IDOR)."""
        await self.assert_membership(pantry_id=pantry_id, user_id=user_id)

        location = await self.pantry_repo.get_location(data.location_id)
        if location is None or location.pantry_id != pantry_id:
            raise LocationNotFoundError("La ubicación no existe o no pertenece a esta despensa.")

        product = await self.pantry_repo.get_product(data.product_id)
        if product is None:
            raise ProductNotFoundError("El producto no existe en el catálogo.")

        unit = await self.pantry_repo.get_unit(data.unit_code)
        if unit is None:
            raise UnitNotFoundError(f"La unidad '{data.unit_code}' no es válida.")

        batch = await self.pantry_repo.create_batch(
            location_id=data.location_id,
            product_id=data.product_id,
            unit_code=data.unit_code,
            quantity=data.quantity,
            expiration_date=data.expiration_date,
            purchase_date=data.purchase_date,
            unit_cost=data.unit_cost,
        )

        await self.pantry_repo.record_movement(
            batch_id=batch.id,
            user_id=user_id,
            movement_type="purchase",
            quantity=data.quantity,
            notes="Registro inicial de lote",
        )

        event = EventEnvelope(
            event_type="pantry.item_added.v1",
            correlation_id=correlation_id,
            payload={
                "pantry_id": str(pantry_id),
                "batch_id": str(batch.id),
                "product_id": str(product.id),
                "product_name": product.name,
                "quantity": str(data.quantity),
                "expiration_date": str(data.expiration_date),
            },
        )
        self.outbox_repo.enqueue(
            event=event,
            aggregate_type="batch",
            aggregate_id=str(batch.id),
        )

        await self._commit()

        dias = (batch.expiration_date - date.today()).days
        return FoodBatchResponse(
            id=batch.id,
            location_id=batch.location_id,
            product_id=batch.product_id,
            product_name=product.name,
            unit_code=batch.unit_code,
            initial_quantity=batch.initial_quantity,
            current_quantity=batch.current_quantity,
            expiration_date=batch.expiration_date,
            purchase_date=batch.purchase_date,
            unit_cost=batch.unit_cost,
            status=cast(Literal["available", "consumed", "expired"], batch.status),
            dias_para_vencer=dias,
            semaforo=calcular_semaforo(dias),
        )

    async def list_pantry_batches(
        self,
        pantry_id: UUID,
        *,
        user_id: UUID,
    ) -> list[FoodBatchResponse]:
        """Lista los lotes disponibles calculando el semáforo de caducidad."""
        await self.assert_membership(pantry_id=pantry_id, user_id=user_id)
        batches = await self.pantry_repo.list_batches_by_pantry(pantry_id)
        today = date.today()

        response = []
        for b in batches:
            dias = (b.expiration_date - today).days
            response.append(
                FoodBatchResponse(
                    id=b.id,
                    location_id=b.location_id,
                    product_id=b.product_id,
                    product_name=b.product.name,
                    unit_code=b.unit_code,
                    initial_quantity=b.initial_quantity,
                    current_quantity=b.current_quantity,
                    expiration_date=b.expiration_date,
                    purchase_date=b.purchase_date,
                    unit_cost=b.unit_cost,
                    status=cast(Literal["available", "consumed", "expired"], b.status),
                    dias_para_vencer=dias,
                    semaforo=calcular_semaforo(dias),
                )
            )
        return response

    async def consume_product_fefo(
        self,
        pantry_id: UUID,
        data: ConsumeRequest,
        *,
        user_id: UUID,
        correlation_id: str = "",
    ) -> ConsumeResultResponse:
        """Aplica el algoritmo FEFO descontando stock del lote más próximo a caducar."""
        await self.assert_membership(pantry_id=pantry_id, user_id=user_id)

        # 1. Obtener lotes ordenados por fecha de expiración ascendente (con bloqueo pesimista)
        batches = await self.pantry_repo.get_available_batches_for_fefo(
            pantry_id=pantry_id,
            product_id=data.product_id,
        )

        total_available = sum((b.current_quantity for b in batches), Decimal("0"))
        if total_available < data.quantity:
            raise InsufficientStockError(
                f"Stock insuficiente. Disponible: {total_available}, solicitado: {data.quantity}"
            )

        remaining_to_consume = data.quantity
        affected_details: list[BatchConsumeDetail] = []

        # 2. Iterar por lotes aplicando FEFO (First Expired, First Out)
        for batch in batches:
            if remaining_to_consume <= Decimal("0"):
                break

            if batch.current_quantity <= remaining_to_consume:
                deducted = batch.current_quantity
                batch.current_quantity = Decimal("0")
                batch.status = "consumed"
                exhausted = True
            else:
                deducted = remaining_to_consume
                batch.current_quantity -= deducted
                exhausted = False

            remaining_to_consume -= deducted

            # Registrar movimiento de stock inmutable
            await self.pantry_repo.record_movement(
                batch_id=batch.id,
                user_id=user_id,
                movement_type="consume",
                quantity=deducted,
                notes=data.notes or "Consumo FEFO",
            )

            affected_details.append(
                BatchConsumeDetail(
                    batch_id=batch.id,
                    expiration_date=batch.expiration_date,
                    quantity_deducted=deducted,
                    batch_exhausted=exhausted,
                )
            )

        # 3. Encolar evento outbox
        event = EventEnvelope(
            event_type="pantry.item_consumed.v1",
            correlation_id=correlation_id,
            payload={
                "pantry_id": str(pantry_id),
                "product_id": str(data.product_id),
                "consumed_quantity": str(data.quantity),
                "user_id": str(user_id),
            },
        )
        self.outbox_repo.enqueue(
            event=event,
            aggregate_type="pantry",
            aggregate_id=str(pantry_id),
        )

        await self._commit()

        remaining_total = total_available - data.quantity
        return ConsumeResultResponse(
            product_id=data.product_id,
            requested_quantity=data.quantity,
            consumed_quantity=data.quantity,
            remaining_stock=remaining_total,
            batches_affected=affected_details,
        )
