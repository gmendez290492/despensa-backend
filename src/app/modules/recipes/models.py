"""Modelos ORM de SQLAlchemy para el catálogo de recetas e ingredientes."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.pantry.models import Product, UnitOfMeasure


class Recipe(Base):
    """Catálogo maestro de recetas culinarias."""

    __tablename__ = "recipes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    prep_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    cook_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    servings: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
    )


class RecipeIngredient(Base):
    """Ingrediente requerido por una receta asociado al catálogo maestro de productos."""

    __tablename__ = "recipe_ingredients"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    recipe_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("units_of_measure.code"),
        nullable=False,
    )
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    product: Mapped[Product] = relationship()
    unit: Mapped[UnitOfMeasure] = relationship()
