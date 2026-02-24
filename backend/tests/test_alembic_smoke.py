"""
Alembic Migration Smoke Test (Milestone C — PR2).

Verifies:
  1. `alembic upgrade head` runs without error on a fresh SQLite DB
  2. All 12 expected tables exist after migration
  3. Key unique constraints and indexes are present
  4. Downgrade to base removes all tables
  5. Re-upgrade works (idempotent)
  6. create_all gating respects ENV/AUTO_CREATE_SCHEMA
"""

import os
import sys
import pytest
import sqlite3
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from alembic.config import Config
from alembic import command


EXPECTED_TABLES = {
    "ohlcv_prices",
    "market_index",
    "signals",
    "no_trade_events",
    "audit_events",
    "source_health",
    "corporate_actions",
    "adjusted_prices",
    "fx_rates",
    "macro_series",
    "portfolios",
    "portfolio_transactions",
}


def _get_alembic_config(db_path: str) -> Config:
    """Create Alembic config pointing at a SQLite file."""
    sqlite_url = f"sqlite:///{db_path}"
    # Set env var so alembic/env.py uses SQLite instead of PostgreSQL
    os.environ["ALEMBIC_DATABASE_URL"] = sqlite_url

    alembic_dir = os.path.join(os.path.dirname(__file__), "..", "alembic")
    ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    cfg = Config(ini_path)
    cfg.set_main_option("script_location", alembic_dir)
    cfg.set_main_option("sqlalchemy.url", sqlite_url)
    return cfg


def _get_tables(db_path: str) -> set:
    """Get all user table names from a SQLite DB."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'alembic%'"
    )
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    return tables


def _get_indexes(db_path: str, table: str) -> set:
    """Get index names for a table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        f"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
        (table,),
    )
    indexes = {row[0] for row in cursor.fetchall()}
    conn.close()
    return indexes


# ── 1. Upgrade Head ──────────────────────────────────────────────────


class TestAlembicUpgrade:

    def test_upgrade_head_creates_all_tables(self, tmp_path):
        """alembic upgrade head on empty DB creates all 12 tables."""
        db_path = str(tmp_path / "test.db")
        cfg = _get_alembic_config(db_path)
        command.upgrade(cfg, "head")

        tables = _get_tables(db_path)
        for t in EXPECTED_TABLES:
            assert t in tables, f"Missing table: {t}"

    def test_table_count(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        cfg = _get_alembic_config(db_path)
        command.upgrade(cfg, "head")

        tables = _get_tables(db_path)
        assert len(tables) >= len(EXPECTED_TABLES)

    def test_ohlcv_has_unique_constraint(self, tmp_path):
        """ohlcv_prices has unique constraint on (symbol, ts)."""
        db_path = str(tmp_path / "test.db")
        cfg = _get_alembic_config(db_path)
        command.upgrade(cfg, "head")

        conn = sqlite3.connect(db_path)
        # Insert and try duplicate
        conn.execute(
            "INSERT INTO ohlcv_prices (id, symbol, ts, open, high, low, close, volume, source, ingested_at) "
            "VALUES (1, 'TEST', '2024-01-01', 100, 105, 95, 100, 1000, 'TEST', '2024-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ohlcv_prices (id, symbol, ts, open, high, low, close, volume, source, ingested_at) "
                "VALUES (2, 'TEST', '2024-01-01', 200, 205, 195, 200, 2000, 'TEST2', '2024-01-02')"
            )
        conn.close()

    def test_fx_rates_has_unique_constraint(self, tmp_path):
        """fx_rates has unique constraint on (pair, ts)."""
        db_path = str(tmp_path / "test.db")
        cfg = _get_alembic_config(db_path)
        command.upgrade(cfg, "head")

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO fx_rates (id, pair, ts, rate, source, confidence, ingested_at) "
            "VALUES (1, 'USDNGN', '2024-01-01', 900, 'CBN', 'HIGH', '2024-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO fx_rates (id, pair, ts, rate, source, confidence, ingested_at) "
                "VALUES (2, 'USDNGN', '2024-01-01', 910, 'CBN2', 'HIGH', '2024-01-02')"
            )
        conn.close()

    def test_portfolios_use_integer_pk(self, tmp_path):
        """portfolios and portfolio_transactions use Integer PK (autoincrement on SQLite)."""
        db_path = str(tmp_path / "test.db")
        cfg = _get_alembic_config(db_path)
        command.upgrade(cfg, "head")

        conn = sqlite3.connect(db_path)
        # Insert without explicit id — should auto-increment
        conn.execute(
            "INSERT INTO portfolios (name, base_currency, created_at, updated_at) "
            "VALUES ('Test', 'NGN', '2024-01-01', '2024-01-01')"
        )
        row = conn.execute("SELECT id FROM portfolios").fetchone()
        assert row[0] is not None
        assert row[0] > 0
        conn.close()


# ── 2. Downgrade ─────────────────────────────────────────────────────


class TestAlembicDowngrade:

    def test_downgrade_to_001_removes_milestone_tables(self, tmp_path):
        """Downgrade from 002 to 001 removes Milestone A+B tables."""
        db_path = str(tmp_path / "test.db")
        cfg = _get_alembic_config(db_path)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "001")

        tables = _get_tables(db_path)
        # Original 5 should remain
        assert "ohlcv_prices" in tables
        assert "audit_events" in tables
        # Milestone A+B should be gone
        assert "corporate_actions" not in tables
        assert "fx_rates" not in tables
        assert "portfolios" not in tables

    def test_downgrade_to_base_removes_all(self, tmp_path):
        """Full downgrade removes all tables."""
        db_path = str(tmp_path / "test.db")
        cfg = _get_alembic_config(db_path)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")

        tables = _get_tables(db_path)
        assert len(tables) == 0


# ── 3. Re-upgrade (idempotent) ───────────────────────────────────────


class TestAlembicReupgrade:

    def test_upgrade_downgrade_upgrade(self, tmp_path):
        """Full cycle: upgrade → downgrade → upgrade works."""
        db_path = str(tmp_path / "test.db")
        cfg = _get_alembic_config(db_path)

        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")

        tables = _get_tables(db_path)
        for t in EXPECTED_TABLES:
            assert t in tables


# ── 4. create_all gating ─────────────────────────────────────────────


class TestCreateAllGating:

    @pytest.mark.asyncio
    async def test_production_skips_create_all(self, monkeypatch):
        """ENV=production + no AUTO_CREATE_SCHEMA → init_db skips create_all."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.delenv("AUTO_CREATE_SCHEMA", raising=False)

        # init_db should return without error (no engine needed)
        from app.db.engine import init_db
        await init_db()  # should not raise; just logs and returns

    @pytest.mark.asyncio
    async def test_auto_create_off_skips(self, monkeypatch):
        """AUTO_CREATE_SCHEMA=off → init_db skips even in dev."""
        monkeypatch.setenv("ENV", "dev")
        monkeypatch.setenv("AUTO_CREATE_SCHEMA", "off")

        from app.db.engine import init_db
        await init_db()  # should not raise
