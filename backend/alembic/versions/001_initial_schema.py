"""Initial schema — G3 gate tables

Revision ID: 001
Revises: None
Create Date: 2025-02-23

Tables:
- ohlcv_prices
- market_index
- signals
- no_trade_events
- audit_events
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ohlcv_prices
    op.create_table(
        "ohlcv_prices",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("ts", sa.Date, nullable=False),
        sa.Column("open", sa.Float, nullable=False),
        sa.Column("high", sa.Float, nullable=False),
        sa.Column("low", sa.Float, nullable=False),
        sa.Column("close", sa.Float, nullable=False),
        sa.Column("volume", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("source", sa.String(50), nullable=False, server_default="NGNMARKET_HISTORICAL"),
        sa.Column("ingested_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("symbol", "ts", name="uq_ohlcv_symbol_ts"),
    )
    op.create_index("ix_ohlcv_prices_symbol", "ohlcv_prices", ["symbol"])
    op.create_index("ix_ohlcv_symbol_ts_desc", "ohlcv_prices", ["symbol", sa.text("ts DESC")])

    # market_index
    op.create_table(
        "market_index",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(20), nullable=False, server_default="ASI"),
        sa.Column("ts", sa.Date, nullable=False),
        sa.Column("open", sa.Float, nullable=True),
        sa.Column("high", sa.Float, nullable=True),
        sa.Column("low", sa.Float, nullable=True),
        sa.Column("close", sa.Float, nullable=False),
        sa.Column("volume", sa.BigInteger, nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="NGNMARKET_HISTORICAL"),
        sa.Column("ingested_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", "ts", name="uq_market_index_name_ts"),
    )
    op.create_index("ix_market_index_name", "market_index", ["name"])
    op.create_index("ix_market_index_name_ts_desc", "market_index", ["name", sa.text("ts DESC")])

    # signals
    op.create_table(
        "signals",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.String(64), nullable=False, unique=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("as_of", sa.DateTime, nullable=False),
        sa.Column("strategy", sa.String(50), nullable=False),
        sa.Column("horizon", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("bias_probability", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("params", JSONB, nullable=True),
        sa.Column("provenance", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_signals_signal_id", "signals", ["signal_id"])
    op.create_index("ix_signals_symbol", "signals", ["symbol"])
    op.create_index("ix_signals_symbol_as_of", "signals", ["symbol", sa.text("as_of DESC")])
    op.create_index("ix_signals_status", "signals", ["status"])

    # no_trade_events
    op.create_table(
        "no_trade_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("scope", sa.String(20), nullable=False, server_default="symbol"),
        sa.Column("symbol", sa.String(20), nullable=True),
        sa.Column("reason_code", sa.String(50), nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("provenance", JSONB, nullable=True),
    )
    op.create_index("ix_no_trade_events_ts", "no_trade_events", ["ts"])
    op.create_index("ix_no_trade_events_symbol", "no_trade_events", ["symbol"])

    # audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("component", sa.String(50), nullable=False),
        sa.Column("level", sa.String(10), nullable=False, server_default="INFO"),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=True),
    )
    op.create_index("ix_audit_events_ts", "audit_events", ["ts"])
    op.create_index("ix_audit_events_component", "audit_events", ["component"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("no_trade_events")
    op.drop_table("signals")
    op.drop_table("market_index")
    op.drop_table("ohlcv_prices")
