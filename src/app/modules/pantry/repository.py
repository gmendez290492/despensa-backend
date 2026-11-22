"""Repositorio de persistencia SQLAlchemy para el módulo pantry."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.pantry.models import (
    Category,
    FoodBatch,
    Location,
    Pantry,
    PantryMember,
    Product,
    StockMovement,
    UnitOfMeasure,
)


class PantryRepository:
    """Acceso a datos para despensas, miembros y ubicaciones."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_pantry(self, *, name: str, invite_code: str) -> Pantry:
        pantry = Pantry(name=name, invite_code=invite_code)
        self.session.add(pantry)
        await self.session.flush()
        return pantry

    async def get_pantry_by_id(self, pantry_id: UUID) -> Pantry | None:
        return await self.session.get(Pantry, pantry_id)

    async def get_pantry_by_invite_code(self, invite_code: str) -> Pantry | None:
        stmt = select(Pantry).where(Pantry.invite_code == invite_code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_member(
        self,
        *,
        pantry_id: UUID,
        user_id: UUID,
        role: str = "member",
    ) -> PantryMember:
        member = PantryMember(pantry_id=pantry_id, user_id=user_id, role=role)
        self.session.add(member)
        await self.session.flush()
        return member

    async def get_member(self, *, pantry_id: UUID, user_id: UUID) -> PantryMember | None:
        stmt = select(PantryMember).where(
            PantryMember.pantry_id == pantry_id,
            PantryMember.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_user_pantries(self, user_id: UUID) -> Sequence[Pantry]:
        stmt = (
            select(Pantry)
            .join(PantryMember, PantryMember.pantry_id == Pantry.id)
            .where(PantryMember.user_id == user_id)
            .order_by(Pantry.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_location(
        self,
        *,
        pantry_id: UUID,
        name: str,
        description: str | None = None,
    ) -> Location:
        location = Location(pantry_id=pantry_id, name=name, description=description)
        self.session.add(location)
        await self.session.flush()
        return location

    async def get_location(self, location_id: UUID) -> Location | None:
        return await self.session.get(Location, location_id)

    async def list_locations_by_pantry(self, pantry_id: UUID) -> Sequence[Location]:
        stmt = select(Location).where(Location.pantry_id == pantry_id).order_by(Location.name.asc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_categories(self) -> Sequence[Category]:
        stmt = select(Category).order_by(Category.name.asc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_category(self, category_id: UUID) -> Category | None:
        return await self.session.get(Category, category_id)

    async def get_unit(self, code: str) -> UnitOfMeasure | None:
        return await self.session.get(UnitOfMeasure, code)

    async def create_product(
        self,
        *,
        category_id: UUID,
        name: str,
        base_unit_code: str,
        barcode: str | None = None,
        estimated_shelf_life_days: int = 7,
    ) -> Product:
        product = Product(
            category_id=category_id,
            name=name,
            base_unit_code=base_unit_code,
            barcode=barcode,
            estimated_shelf_life_days=estimated_shelf_life_days,
        )
        self.session.add(product)
        await self.session.flush()
        return product

    async def get_product(self, product_id: UUID) -> Product | None:
        return await self.session.get(Product, product_id)

    async def list_products(
        self,
        *,
        category_id: UUID | None = None,
        search: str | None = None,
    ) -> Sequence[Product]:
        stmt = select(Product)
        if category_id:
            stmt = stmt.where(Product.category_id == category_id)
        if search:
            stmt = stmt.where(Product.name.ilike(f"%{search}%"))
        stmt = stmt.order_by(Product.name.asc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_batch(
        self,
        *,
        location_id: UUID,
        product_id: UUID,
        unit_code: str,
        quantity: Decimal,
        expiration_date: date,
        purchase_date: date,
        unit_cost: Decimal | None = None,
    ) -> FoodBatch:
        batch = FoodBatch(
            location_id=location_id,
            product_id=product_id,
            unit_code=unit_code,
            initial_quantity=quantity,
            current_quantity=quantity,
            expiration_date=expiration_date,
            purchase_date=purchase_date,
            unit_cost=unit_cost,
            status="available",
        )
        self.session.add(batch)
        await self.session.flush()
        return batch

    async def get_batch(self, batch_id: UUID) -> FoodBatch | None:
        stmt = (
            select(FoodBatch)
            .options(
                selectinload(FoodBatch.product),
                selectinload(FoodBatch.location),
            )
            .where(FoodBatch.id == batch_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_batches_by_pantry(
        self,
        pantry_id: UUID,
        *,
        status: str = "available",
    ) -> Sequence[FoodBatch]:
        """Obtiene lotes filtrando por despensa a través de la relación de ubicación (3NF)."""
        stmt = (
            select(FoodBatch)
            .join(Location, FoodBatch.location_id == Location.id)
            .options(
                selectinload(FoodBatch.product),
                selectinload(FoodBatch.location),
            )
            .where(Location.pantry_id == pantry_id, FoodBatch.status == status)
            .order_by(FoodBatch.expiration_date.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_available_batches_for_fefo(
        self,
        *,
        pantry_id: UUID,
        product_id: UUID,
    ) -> Sequence[FoodBatch]:
        """Obtiene lotes disponibles ordenados por FEFO (First Expired, First Out) con bloqueo."""
        stmt = (
            select(FoodBatch)
            .join(Location, FoodBatch.location_id == Location.id)
            .where(
                Location.pantry_id == pantry_id,
                FoodBatch.product_id == product_id,
                FoodBatch.status == "available",
                FoodBatch.current_quantity > Decimal("0"),
            )
            .order_by(FoodBatch.expiration_date.asc())
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def record_movement(
        self,
        *,
        batch_id: UUID,
        user_id: UUID,
        movement_type: str,
        quantity: Decimal,
        notes: str | None = None,
    ) -> StockMovement:
        movement = StockMovement(
            batch_id=batch_id,
            user_id=user_id,
            movement_type=movement_type,
            quantity=quantity,
            notes=notes,
        )
        self.session.add(movement)
        await self.session.flush()
        return movement
