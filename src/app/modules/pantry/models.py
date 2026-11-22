"""Modelos ORM de SQLAlchemy para el módulo pantry normalizados en 3NF / BCNF."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.users.models import User


class UnitOfMeasure(Base):
    """Catálogo canónico de unidades de medida físicas y factores de conversión."""

    __tablename__ = "units_of_measure"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)  # 'MASS', 'VOLUME', 'COUNT'
    base_conversion_factor: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        default=Decimal("1.0000"),
    )


class Category(Base):
    """Categoría para agrupación de alimentos (Lácteos, Proteínas, Granos, etc.)."""

    __tablename__ = "categories"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class Product(Base):
    """Catálogo maestro de alimentos genéricos (ej. Leche Entera 1L, Arroz Blanco)."""

    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    category_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    barcode: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    base_unit_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("units_of_measure.code", ondelete="RESTRICT"),
        nullable=False,
    )
    estimated_shelf_life_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    category: Mapped[Category] = relationship()
    base_unit: Mapped[UnitOfMeasure] = relationship()


class Pantry(Base):
    """Entidad Despensa / Hogar compartible entre múltiples miembros (Multi-Tenancy)."""

    __tablename__ = "pantries"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    members: Mapped[list["PantryMember"]] = relationship(
        back_populates="pantry",
        cascade="all, delete-orphan",
    )
    locations: Mapped[list["Location"]] = relationship(
        back_populates="pantry",
        cascade="all, delete-orphan",
    )


class PantryMember(Base):
    """Membresía N:M entre usuario y despensa con control de roles (RBAC)."""

    __tablename__ = "pantry_members"
    __table_args__ = (
        UniqueConstraint("pantry_id", "user_id", name="uq_pantry_members_pantry_user"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    pantry_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("pantries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    pantry: Mapped[Pantry] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class Location(Base):
    """Zona de almacenamiento físico dentro de una despensa (Refrigerador, Alacena, etc.)."""

    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("pantry_id", "name", name="uq_locations_pantry_name"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    pantry_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("pantries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    pantry: Mapped[Pantry] = relationship(back_populates="locations")
    batches: Mapped[list["FoodBatch"]] = relationship(back_populates="location")


class FoodBatch(Base):
    """Lote físico de alimento con fecha de caducidad e inventario FEFO."""

    __tablename__ = "food_batches"
    __table_args__ = (
        CheckConstraint("initial_quantity > 0", name="ck_food_batches_initial_qty_positive"),
        CheckConstraint("current_quantity >= 0", name="ck_food_batches_current_qty_non_negative"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    location_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    unit_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("units_of_measure.code", ondelete="RESTRICT"),
        nullable=False,
    )
    initial_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    current_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    expiration_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="available",
        index=True,
    )  # 'available', 'consumed', 'expired'
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    location: Mapped[Location] = relationship(back_populates="batches")
    product: Mapped[Product] = relationship()
    unit: Mapped[UnitOfMeasure] = relationship()
    movements: Mapped[list["StockMovement"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
    )


class StockMovement(Base):
    """Auditoría inmutable de movimientos de stock (consumo, desperdicio, reabastecimiento)."""

    __tablename__ = "stock_movements"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("food_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    movement_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # 'purchase', 'consume', 'spoiled', 'adjustment'
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    batch: Mapped[FoodBatch] = relationship(back_populates="movements")
