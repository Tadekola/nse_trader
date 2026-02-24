"""Add NGX Quality Scanner tables

Revision ID: 004
Revises: 003
Create Date: 2026-02-23

Tables added:
- universe_members: Liquid universe membership
- fundamentals_periodic: Periodic financial statements
- fundamentals_derived: Derived quality metrics
- scan_runs: Scanner execution records
- scan_results: Per-symbol scan results (FK -> scan_runs)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── universe_members ──────────────────────────────────────────────
    op.create_table(
        "universe_members",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("universe_name", sa.String(50), nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("liquidity_score", sa.Float, nullable=False),
        sa.Column("avg_daily_value", sa.Float, nullable=True),
        sa.Column("zero_volume_days", sa.Integer, nullable=True),
        sa.Column("provenance", JSONB, nullable=True),
        sa.UniqueConstraint("symbol", "universe_name", "as_of_date",
                            name="uq_universe_member"),
    )
    op.create_index("ix_universe_members_symbol", "universe_members", ["symbol"])
    op.create_index("ix_universe_members_name", "universe_members", ["universe_name"])
    op.create_index("ix_universe_members_date", "universe_members", ["as_of_date"])
    op.create_index("ix_universe_name_date", "universe_members",
                     ["universe_name", sa.text("as_of_date DESC")])

    # ── fundamentals_periodic ─────────────────────────────────────────
    op.create_table(
        "fundamentals_periodic",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("period_end_date", sa.Date, nullable=False),
        sa.Column("period_type", sa.String(10), nullable=False, server_default="ANNUAL"),
        sa.Column("currency", sa.String(5), nullable=False, server_default="NGN"),
        sa.Column("revenue", sa.Float, nullable=True),
        sa.Column("operating_profit", sa.Float, nullable=True),
        sa.Column("net_income", sa.Float, nullable=True),
        sa.Column("total_assets", sa.Float, nullable=True),
        sa.Column("total_equity", sa.Float, nullable=True),
        sa.Column("total_debt", sa.Float, nullable=True),
        sa.Column("cash", sa.Float, nullable=True),
        sa.Column("operating_cash_flow", sa.Float, nullable=True),
        sa.Column("capex", sa.Float, nullable=True),
        sa.Column("dividends_paid", sa.Float, nullable=True),
        sa.Column("shares_outstanding", sa.Float, nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("ingested_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("provenance", JSONB, nullable=True),
        sa.UniqueConstraint("symbol", "period_end_date", "period_type", "source",
                            name="uq_fundamentals_periodic"),
    )
    op.create_index("ix_fund_periodic_symbol", "fundamentals_periodic", ["symbol"])
    op.create_index("ix_fund_periodic_date", "fundamentals_periodic", ["period_end_date"])
    op.create_index("ix_fund_periodic_symbol_date", "fundamentals_periodic",
                     ["symbol", sa.text("period_end_date DESC")])

    # ── fundamentals_derived ──────────────────────────────────────────
    op.create_table(
        "fundamentals_derived",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("roe", sa.Float, nullable=True),
        sa.Column("roic_proxy", sa.Float, nullable=True),
        sa.Column("op_margin", sa.Float, nullable=True),
        sa.Column("net_margin", sa.Float, nullable=True),
        sa.Column("debt_to_equity", sa.Float, nullable=True),
        sa.Column("cash_to_debt", sa.Float, nullable=True),
        sa.Column("ocf_to_net_income", sa.Float, nullable=True),
        sa.Column("fcf", sa.Float, nullable=True),
        sa.Column("earnings_stability", sa.Float, nullable=True),
        sa.Column("margin_stability", sa.Float, nullable=True),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("sub_scores", JSONB, nullable=True),
        sa.Column("reasons", JSONB, nullable=True),
        sa.Column("red_flags", JSONB, nullable=True),
        sa.Column("data_freshness_days", sa.Integer, nullable=True),
        sa.Column("periods_available", sa.Integer, nullable=True),
        sa.Column("computed_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("provenance", JSONB, nullable=True),
        sa.UniqueConstraint("symbol", "as_of_date", name="uq_fundamentals_derived"),
    )
    op.create_index("ix_fund_derived_symbol", "fundamentals_derived", ["symbol"])
    op.create_index("ix_fund_derived_date", "fundamentals_derived", ["as_of_date"])
    op.create_index("ix_fund_derived_symbol_date", "fundamentals_derived",
                     ["symbol", sa.text("as_of_date DESC")])
    op.create_index("ix_fund_derived_score", "fundamentals_derived",
                     [sa.text("quality_score DESC")])

    # ── scan_runs ─────────────────────────────────────────────────────
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("universe_name", sa.String(50), nullable=False),
        sa.Column("symbols_scanned", sa.Integer, nullable=False, server_default="0"),
        sa.Column("symbols_ranked", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("summary", JSONB, nullable=True),
        sa.Column("provenance", JSONB, nullable=True),
    )
    op.create_index("ix_scan_runs_date", "scan_runs", ["as_of_date"])

    # ── scan_results ──────────────────────────────────────────────────
    op.create_table(
        "scan_results",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("scan_runs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("quality_score", sa.Float, nullable=False),
        sa.Column("sub_scores", JSONB, nullable=True),
        sa.Column("reasons", JSONB, nullable=True),
        sa.Column("red_flags", JSONB, nullable=True),
        sa.Column("flags", JSONB, nullable=True),
        sa.Column("liquidity_score", sa.Float, nullable=True),
        sa.Column("confidence_penalty", sa.Float, nullable=True, server_default="0.0"),
        sa.Column("tri_1y_ngn", sa.Float, nullable=True),
        sa.Column("tri_3y_ngn", sa.Float, nullable=True),
        sa.Column("tri_1y_usd", sa.Float, nullable=True),
        sa.Column("tri_3y_usd", sa.Float, nullable=True),
        sa.Column("tri_1y_real", sa.Float, nullable=True),
        sa.Column("tri_3y_real", sa.Float, nullable=True),
        sa.UniqueConstraint("run_id", "symbol", name="uq_scan_result_run_symbol"),
    )
    op.create_index("ix_scan_results_run_id", "scan_results", ["run_id"])
    op.create_index("ix_scan_results_symbol", "scan_results", ["symbol"])
    op.create_index("ix_scan_result_run_rank", "scan_results", ["run_id", "rank"])


def downgrade() -> None:
    op.drop_table("scan_results")
    op.drop_table("scan_runs")
    op.drop_table("fundamentals_derived")
    op.drop_table("fundamentals_periodic")
    op.drop_table("universe_members")
