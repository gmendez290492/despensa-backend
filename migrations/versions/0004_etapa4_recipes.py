"""Etapa 4: catálogo de recetas e ingredientes.

Revision ID: 0004_etapa4
Revises: 0003_etapa3
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_etapa4"
down_revision: str | Sequence[str] | None = "0003_etapa3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea las tablas recipes y recipe_ingredients con claves foráneas e índices."""
    op.create_table(
        "recipes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("prep_time_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("cook_time_minutes", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("servings", sa.Integer(), nullable=False, server_default="2"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_recipes_title", "recipes", ["title"])

    op.create_table(
        "recipe_ingredients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recipe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column(
            "unit_code",
            sa.String(length=16),
            sa.ForeignKey("units_of_measure.code"),
            nullable=False,
        ),
        sa.Column(
            "is_optional",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("ix_recipe_ingredients_recipe_id", "recipe_ingredients", ["recipe_id"])
    op.create_index("ix_recipe_ingredients_product_id", "recipe_ingredients", ["product_id"])


def downgrade() -> None:
    """Elimina las tablas recipes y recipe_ingredients."""
    op.drop_index("ix_recipe_ingredients_product_id", table_name="recipe_ingredients")
    op.drop_index("ix_recipe_ingredients_recipe_id", table_name="recipe_ingredients")
    op.drop_table("recipe_ingredients")
    op.drop_index("ix_recipes_title", table_name="recipes")
    op.drop_table("recipes")
