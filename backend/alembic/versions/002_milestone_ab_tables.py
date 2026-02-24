"""Add Milestone A + B tables

Revision ID: 002
Revises: 001
Create Date: 2026-02-23

Tables added:
- source_health (P1-3)
- corporate_actions (Milestone A)
- adjusted_prices (Milestone A)
- fx_rates (Milestone B)
- macro_series (Milestone B)
- portfolios (Milestone B)
- portfolio_transactions (Milestone B)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── source_health (P1-3) ─────────────────────────────────────────
    op.create_table(
        "source_health",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("last_success", sa.DateTime, nullable=True),
        sa.Column("last_error", sa.DateTime, nullable=True),
        sa.Column("last_error_message", sa.Text, nullable=True),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_calls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_rate", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("stale_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("circuit_state", sa.String(20), nullable=False, server_default="CLOSED"),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_source_health_name", "source_health", ["name"])

    # ── corporate_actions (Milestone A) ──────────────────────────────
    op.create_table(
        "corporate_actions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("ex_date", sa.Date, nullable=False),
        sa.Column("record_date", sa.Date, nullable=True),
        sa.Column("payment_date", sa.Date, nullable=True),
        sa.Column("amount", sa.Float, nullable=True),
        sa.Column("ratio_from", sa.Integer, nullable=True),
        sa.Column("ratio_to", sa.Integer, nullable=True),
        sa.Column("currency", sa.String(5), nullable=False, server_default="NGN"),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("confidence", sa.String(10), nullable=False, server_default="HIGH"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("artifact_ref", sa.String(255), nullable=True),
        sa.Column("ingested_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("provenance", JSONB, nullable=True),
        sa.UniqueConstraint("symbol", "action_type", "ex_date",
                            name="uq_corp_action_symbol_type_exdate"),
    )
    op.create_index("ix_corporate_actions_symbol", "corporate_actions", ["symbol"])
    op.create_index("ix_corporate_actions_action_type", "corporate_actions", ["action_type"])
    op.create_index("ix_corporate_actions_ex_date", "corporate_actions", ["ex_date"])
    op.create_index("ix_corp_action_symbol_exdate", "corporate_actions",
                     ["symbol", sa.text("ex_date DESC")])

    # ── adjusted_prices (Milestone A) ────────────────────────────────
    op.create_table(
        "adjusted_prices",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("ts", sa.Date, nullable=False),
        sa.Column("close_raw", sa.Float, nullable=False),
        sa.Column("adj_factor", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("adj_close", sa.Float, nullable=False),
        sa.Column("tri", sa.Float, nullable=False),
        sa.Column("daily_return_price", sa.Float, nullable=True),
        sa.Column("daily_return_total", sa.Float, nullable=True),
        sa.Column("tri_quality", sa.String(20), nullable=False, server_default="PRICE_ONLY"),
        sa.Column("computed_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("provenance", JSONB, nullable=True),
        sa.UniqueConstraint("symbol", "ts", name="uq_adj_price_symbol_ts"),
    )
    op.create_index("ix_adjusted_prices_symbol", "adjusted_prices", ["symbol"])
    op.create_index("ix_adj_price_symbol_ts_desc", "adjusted_prices",
                     ["symbol", sa.text("ts DESC")])

    # ── fx_rates (Milestone B) ───────────────────────────────────────
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("pair", sa.String(10), nullable=False),
        sa.Column("ts", sa.Date, nullable=False),
        sa.Column("rate", sa.Float, nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("confidence", sa.String(10), nullable=False, server_default="HIGH"),
        sa.Column("ingested_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("provenance", JSONB, nullable=True),
        sa.UniqueConstraint("pair", "ts", name="uq_fx_rate_pair_ts"),
    )
    op.create_index("ix_fx_rates_pair", "fx_rates", ["pair"])
    op.create_index("ix_fx_rates_ts", "fx_rates", ["ts"])
    op.create_index("ix_fx_rate_pair_ts_desc", "fx_rates",
                     ["pair", sa.text("ts DESC")])

    # ── macro_series (Milestone B) ───────────────────────────────────
    op.create_table(
        "macro_series",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("series_name", sa.String(30), nullable=False),
        sa.Column("ts", sa.Date, nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("frequency", sa.String(10), nullable=False, server_default="MONTHLY"),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("confidence", sa.String(10), nullable=False, server_default="HIGH"),
        sa.Column("ingested_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("provenance", JSONB, nullable=True),
        sa.UniqueConstraint("series_name", "ts", name="uq_macro_series_name_ts"),
    )
    op.create_index("ix_macro_series_series_name", "macro_series", ["series_name"])
    op.create_index("ix_macro_series_ts", "macro_series", ["ts"])
    op.create_index("ix_macro_series_name_ts_desc", "macro_series",
                     ["series_name", sa.text("ts DESC")])

    # ── portfolios (Milestone B) ─────────────────────────────────────
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("base_currency", sa.String(5), nullable=False, server_default="NGN"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ── portfolio_transactions (Milestone B) ─────────────────────────
    op.create_table(
        "portfolio_transactions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("portfolio_id", sa.Integer, nullable=False),
        sa.Column("ts", sa.Date, nullable=False),
        sa.Column("symbol", sa.String(20), nullable=True),
        sa.Column("tx_type", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Float, nullable=True),
        sa.Column("price_ngn", sa.Float, nullable=True),
        sa.Column("amount_ngn", sa.Float, nullable=False),
        sa.Column("fees_ngn", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("provenance", JSONB, nullable=True),
    )
    op.create_index("ix_portfolio_transactions_portfolio_id",
                     "portfolio_transactions", ["portfolio_id"])
    op.create_index("ix_portfolio_transactions_ts",
                     "portfolio_transactions", ["ts"])
    op.create_index("ix_portfolio_transactions_symbol",
                     "portfolio_transactions", ["symbol"])
    op.create_index("ix_ptx_portfolio_ts", "portfolio_transactions",
                     ["portfolio_id", sa.text("ts DESC")])
    op.create_index("ix_ptx_portfolio_symbol", "portfolio_transactions",
                     ["portfolio_id", "symbol"])


def downgrade() -> None:
    op.drop_table("portfolio_transactions")
    op.drop_table("portfolios")
    op.drop_table("macro_series")
    op.drop_table("fx_rates")
    op.drop_table("adjusted_prices")
    op.drop_table("corporate_actions")
    op.drop_table("source_health")
