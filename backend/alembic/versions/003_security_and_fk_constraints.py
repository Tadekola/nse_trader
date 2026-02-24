"""Add beta security tables and FK constraints

Revision ID: 003
Revises: 002
Create Date: 2026-02-23

Changes:
- api_keys table for beta authentication
- FK constraint on portfolio_transactions.portfolio_id -> portfolios.id
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── api_keys ──────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
        sa.Column("scopes", sa.String(500), nullable=True),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    # ── FK: portfolio_transactions.portfolio_id -> portfolios.id ──────
    # Use batch mode for SQLite compatibility (ALTER constraint not supported)
    with op.batch_alter_table("portfolio_transactions") as batch_op:
        batch_op.create_foreign_key(
            "fk_ptx_portfolio_id",
            "portfolios",
            ["portfolio_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("portfolio_transactions") as batch_op:
        batch_op.drop_constraint("fk_ptx_portfolio_id", type_="foreignkey")
    op.drop_table("api_keys")
