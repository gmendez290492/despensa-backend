"""Deuda de auth (issue #9): sesiones, rate limit compartido y recuperación de contraseña.

- auth_sessions: familia de refresh tokens; revocarla invalida sus access tokens (claim sid).
- refresh_tokens: session_id, issued_at y replaced_by_jti (rotación con ventana de gracia).
- rate_limit_buckets: contadores compartidos entre réplicas.
- password_reset_tokens: tokens de un solo uso (solo se guarda su SHA-256).

Los refresh tokens existentes se migran a una sesión propia cada uno (sesión = id del token),
de modo que los usuarios con sesión abierta no tienen que volver a iniciar sesión.

Revision ID: 0005_auth_debt
Revises: 0004_etapa4
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_auth_debt"
down_revision: str | Sequence[str] | None = "0004_etapa4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea sesiones, buckets de rate limit y tokens de reset; migra refresh tokens."""
    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_binding_hash", sa.String(length=64), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)

    # Backfill: una sesión por refresh token existente, reutilizando su id como id de sesión.
    op.execute(
        """
        INSERT INTO auth_sessions (id, user_id, revoked_at, revoked_reason, created_at)
        SELECT id, user_id, revoked_at,
               CASE WHEN revoked_at IS NOT NULL THEN 'legacy' END,
               created_at
        FROM refresh_tokens
        """,
    )

    op.add_column(
        "refresh_tokens",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("replaced_by_jti", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        "UPDATE refresh_tokens SET session_id = id, issued_at = date_trunc('second', created_at)",
    )
    op.alter_column("refresh_tokens", "session_id", nullable=False)
    op.alter_column("refresh_tokens", "issued_at", nullable=False)
    op.create_foreign_key(
        op.f("fk_refresh_tokens_session_id_auth_sessions"),
        "refresh_tokens",
        "auth_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_refresh_tokens_session_id"),
        "refresh_tokens",
        ["session_id"],
        unique=False,
    )

    op.create_table(
        "rate_limit_buckets",
        sa.Column("bucket_key", sa.String(length=160), nullable=False),
        sa.Column("window_start", sa.BigInteger(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("bucket_key", "window_start", name=op.f("pk_rate_limit_buckets")),
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_password_reset_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_password_reset_tokens_user_id"),
        "password_reset_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Revierte las tablas y columnas de la deuda de auth."""
    op.drop_index(op.f("ix_password_reset_tokens_user_id"), table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_table("rate_limit_buckets")
    op.drop_index(op.f("ix_refresh_tokens_session_id"), table_name="refresh_tokens")
    op.drop_constraint(
        op.f("fk_refresh_tokens_session_id_auth_sessions"),
        "refresh_tokens",
        type_="foreignkey",
    )
    op.drop_column("refresh_tokens", "replaced_by_jti")
    op.drop_column("refresh_tokens", "issued_at")
    op.drop_column("refresh_tokens", "session_id")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
