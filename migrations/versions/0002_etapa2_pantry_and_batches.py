"""Etapa 2: tablas de despensa, miembros, ubicaciones, catalogo, lotes y movimientos.

Revision ID: 0002_etapa2
Revises: 0001_etapa1
Create Date: 2026-11-22
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_etapa2"
down_revision: str | Sequence[str] | None = "0001_etapa1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea tablas del módulo pantry con restricciones de integridad y semillas."""
    # 1. Unidades de Medida
    units_table = op.create_table(
        "units_of_measure",
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("base_conversion_factor", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_units_of_measure")),
    )

    # Semilla canónica de unidades
    op.bulk_insert(
        units_table,
        [
            {"code": "g", "name": "Gramos", "dimension": "MASS", "base_conversion_factor": 1.0},
            {
                "code": "kg",
                "name": "Kilogramos",
                "dimension": "MASS",
                "base_conversion_factor": 1000.0,
            },
            {
                "code": "ml",
                "name": "Mililitros",
                "dimension": "VOLUME",
                "base_conversion_factor": 1.0,
            },
            {
                "code": "l",
                "name": "Litros",
                "dimension": "VOLUME",
                "base_conversion_factor": 1000.0,
            },
            {"code": "pza", "name": "Piezas", "dimension": "COUNT", "base_conversion_factor": 1.0},
        ],
    )

    # 2. Categorías de Alimentos
    categories_table = op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    op.create_index(op.f("ix_categories_name"), "categories", ["name"], unique=True)

    # Semilla básica de categorías
    now_utc = datetime.now(UTC)
    op.bulk_insert(
        categories_table,
        [
            {"id": uuid4(), "name": "Lácteos y Huevos", "icon": "dairy", "created_at": now_utc},
            {"id": uuid4(), "name": "Proteínas y Carnes", "icon": "meat", "created_at": now_utc},
            {"id": uuid4(), "name": "Frutas y Verduras", "icon": "produce", "created_at": now_utc},
            {"id": uuid4(), "name": "Granos y Cereales", "icon": "grain", "created_at": now_utc},
            {"id": uuid4(), "name": "Despensa Seca", "icon": "pantry", "created_at": now_utc},
            {"id": uuid4(), "name": "Bebidas", "icon": "beverage", "created_at": now_utc},
            {"id": uuid4(), "name": "Condimentos y Salsas", "icon": "spice", "created_at": now_utc},
        ],
    )

    # 3. Catálogo de Productos
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_unit_code", sa.String(length=16), nullable=False),
        sa.Column("estimated_shelf_life_days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_products_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["base_unit_code"],
            ["units_of_measure.code"],
            name=op.f("fk_products_base_unit_code_units_of_measure"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
    )
    op.create_index(op.f("ix_products_barcode"), "products", ["barcode"], unique=True)
    op.create_index(op.f("ix_products_category_id"), "products", ["category_id"], unique=False)
    op.create_index(op.f("ix_products_name"), "products", ["name"], unique=False)

    # 4. Despensas / Hogares
    op.create_table(
        "pantries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("invite_code", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pantries")),
    )
    op.create_index(op.f("ix_pantries_invite_code"), "pantries", ["invite_code"], unique=True)

    # 5. Miembros de Despensa (Multi-Tenancy)
    op.create_table(
        "pantry_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pantry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["pantry_id"],
            ["pantries.id"],
            name=op.f("fk_pantry_members_pantry_id_pantries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_pantry_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pantry_members")),
        sa.UniqueConstraint("pantry_id", "user_id", name="uq_pantry_members_pantry_user"),
    )
    op.create_index(
        op.f("ix_pantry_members_pantry_id"), "pantry_members", ["pantry_id"], unique=False
    )
    op.create_index(op.f("ix_pantry_members_user_id"), "pantry_members", ["user_id"], unique=False)

    # 6. Ubicaciones Físicas (Refrigerador, Alacena, etc.)
    op.create_table(
        "locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pantry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["pantry_id"],
            ["pantries.id"],
            name=op.f("fk_locations_pantry_id_pantries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
        sa.UniqueConstraint("pantry_id", "name", name="uq_locations_pantry_name"),
    )
    op.create_index(op.f("ix_locations_pantry_id"), "locations", ["pantry_id"], unique=False)

    # 7. Lotes de Alimentos (Inventario FEFO)
    op.create_table(
        "food_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_code", sa.String(length=16), nullable=False),
        sa.Column("initial_quantity", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("current_quantity", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("initial_quantity > 0", name="ck_food_batches_initial_qty_positive"),
        sa.CheckConstraint(
            "current_quantity >= 0", name="ck_food_batches_current_qty_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_food_batches_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_food_batches_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unit_code"],
            ["units_of_measure.code"],
            name=op.f("fk_food_batches_unit_code_units_of_measure"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_batches")),
    )
    op.create_index(
        op.f("ix_food_batches_expiration_date"), "food_batches", ["expiration_date"], unique=False
    )
    op.create_index(
        op.f("ix_food_batches_location_id"), "food_batches", ["location_id"], unique=False
    )
    op.create_index(
        op.f("ix_food_batches_product_id"), "food_batches", ["product_id"], unique=False
    )
    op.create_index(op.f("ix_food_batches_status"), "food_batches", ["status"], unique=False)

    # 8. Movimientos de Stock (Auditoría Inmutable)
    op.create_table(
        "stock_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["food_batches.id"],
            name=op.f("fk_stock_movements_batch_id_food_batches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_stock_movements_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
    )
    op.create_index(
        op.f("ix_stock_movements_batch_id"), "stock_movements", ["batch_id"], unique=False
    )
    op.create_index(
        op.f("ix_stock_movements_user_id"), "stock_movements", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Elimina tablas del módulo pantry en orden inverso de dependencias."""
    op.drop_table("stock_movements")
    op.drop_table("food_batches")
    op.drop_table("locations")
    op.drop_table("pantry_members")
    op.drop_table("pantries")
    op.drop_table("products")
    op.drop_table("categories")
    op.drop_table("units_of_measure")
