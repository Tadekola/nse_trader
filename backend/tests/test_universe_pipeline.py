"""
Universe Pipeline Tests (PR2).

Covers:
  1. Pure liquidity computation (no DB)
  2. Exclusion rules: insufficient sessions, chronic illiquidity
  3. Normalization and ranking
  4. Top-N truncation
  5. Edge cases: empty input, single symbol, all excluded
  6. Migration 004 creates scanner tables
"""

import os
import sys
import sqlite3
import tempfile
import pytest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scanner.universe import (
    compute_liquidity,
    LiquidityResult,
    DEFAULT_MIN_SESSIONS,
    DEFAULT_MAX_ZERO_PCT,
)


# ── Fixtures ─────────────────────────────────────────────────────────

def _make_row(symbol, adv, sessions, zero_days):
    return {
        "symbol": symbol,
        "avg_daily_value": adv,
        "total_sessions": sessions,
        "zero_volume_days": zero_days,
    }


SAMPLE_ROWS = [
    _make_row("DANGCEM", 500_000_000, 100, 2),    # most liquid
    _make_row("GTCO", 300_000_000, 95, 5),
    _make_row("ZENITH", 250_000_000, 90, 3),
    _make_row("MTNN", 200_000_000, 80, 1),
    _make_row("AIRTEL", 150_000_000, 85, 0),
    _make_row("SEPLAT", 100_000_000, 70, 10),
    _make_row("BUACEMENT", 50_000_000, 60, 15),
    _make_row("STANBIC", 30_000_000, 50, 8),
    _make_row("UBA", 20_000_000, 40, 5),
    _make_row("FBNH", 10_000_000, 35, 3),
]


# ── Pure computation tests ───────────────────────────────────────────

class TestComputeLiquidity:
    def test_basic_ranking(self):
        """Symbols should be ranked by avg_daily_value descending."""
        results = compute_liquidity(SAMPLE_ROWS, top_n=10)
        members = [r for r in results if not r.excluded]
        assert members[0].symbol == "DANGCEM"
        assert members[0].rank == 1
        assert members[1].symbol == "GTCO"
        assert members[1].rank == 2

    def test_liquidity_score_normalization(self):
        """Top symbol should have score=1.0, others proportionally less."""
        results = compute_liquidity(SAMPLE_ROWS, top_n=10)
        members = [r for r in results if not r.excluded]
        assert members[0].liquidity_score == 1.0
        # GTCO has 300M/500M = 0.6
        assert abs(members[1].liquidity_score - 0.6) < 0.01

    def test_insufficient_sessions_excluded(self):
        """Symbols with fewer sessions than min should be excluded."""
        rows = [
            _make_row("A", 100_000, 10, 0),  # only 10 sessions
            _make_row("B", 200_000, 50, 0),  # 50 sessions (meets default 30)
        ]
        results = compute_liquidity(rows, min_sessions=30, top_n=10)
        a = next(r for r in results if r.symbol == "A")
        b = next(r for r in results if r.symbol == "B")
        assert a.excluded is True
        assert "insufficient_sessions" in a.exclude_reason
        assert b.excluded is False

    def test_chronic_illiquid_excluded(self):
        """Symbols with too many zero-volume days should be excluded."""
        rows = [
            _make_row("LIQUID", 100_000, 100, 10),    # 10% zero
            _make_row("ILLIQUID", 50_000, 100, 50),   # 50% zero > 40% threshold
        ]
        results = compute_liquidity(rows, max_zero_pct=0.40, top_n=10)
        liquid = next(r for r in results if r.symbol == "LIQUID")
        illiquid = next(r for r in results if r.symbol == "ILLIQUID")
        assert liquid.excluded is False
        assert illiquid.excluded is True
        assert "chronic_illiquid" in illiquid.exclude_reason

    def test_top_n_truncation(self):
        """Only top_n symbols should be included."""
        results = compute_liquidity(SAMPLE_ROWS, top_n=3, min_sessions=30)
        members = [r for r in results if not r.excluded]
        assert len(members) == 3
        assert members[0].symbol == "DANGCEM"
        assert members[2].symbol == "ZENITH"

    def test_outside_top_n_marked(self):
        """Symbols outside top_n should be marked as excluded."""
        results = compute_liquidity(SAMPLE_ROWS, top_n=3, min_sessions=30)
        excluded_topn = [r for r in results if r.excluded and r.exclude_reason and "outside" in r.exclude_reason]
        assert len(excluded_topn) > 0

    def test_empty_input(self):
        """Empty input should return empty list."""
        results = compute_liquidity([], top_n=10)
        assert results == []

    def test_single_symbol(self):
        """Single eligible symbol should have score=1.0 and rank=1."""
        rows = [_make_row("ONLY", 100_000, 50, 2)]
        results = compute_liquidity(rows, min_sessions=30, top_n=10)
        members = [r for r in results if not r.excluded]
        assert len(members) == 1
        assert members[0].liquidity_score == 1.0
        assert members[0].rank == 1

    def test_all_excluded(self):
        """If all symbols are excluded, no members returned."""
        rows = [
            _make_row("A", 100_000, 5, 0),   # insufficient sessions
            _make_row("B", 50_000, 10, 9),    # illiquid (90% zero)
        ]
        results = compute_liquidity(rows, min_sessions=30, max_zero_pct=0.40, top_n=10)
        members = [r for r in results if not r.excluded]
        assert len(members) == 0

    def test_zero_volume_pct_calculation(self):
        """Zero volume percentage should be correctly calculated."""
        rows = [_make_row("A", 100_000, 100, 25)]
        results = compute_liquidity(rows, min_sessions=30, max_zero_pct=0.40, top_n=10)
        a = next(r for r in results if r.symbol == "A")
        assert a.zero_volume_pct == 0.25

    def test_to_dict(self):
        """LiquidityResult.to_dict should return all expected keys."""
        rows = [_make_row("TEST", 100_000, 50, 5)]
        results = compute_liquidity(rows, min_sessions=30, top_n=10)
        d = results[0].to_dict()
        assert "symbol" in d
        assert "avg_daily_value" in d
        assert "liquidity_score" in d
        assert "rank" in d
        assert "excluded" in d

    def test_deterministic(self):
        """Same input should produce identical output."""
        r1 = compute_liquidity(SAMPLE_ROWS, top_n=5)
        r2 = compute_liquidity(SAMPLE_ROWS, top_n=5)
        for a, b in zip(r1, r2):
            assert a.symbol == b.symbol
            assert a.rank == b.rank
            assert a.liquidity_score == b.liquidity_score


# ── Migration 004 tests ──────────────────────────────────────────────

class TestMigration004:
    def _run_migration(self, db_path: str):
        from alembic.config import Config
        from alembic import command

        sqlite_url = f"sqlite:///{db_path}"
        os.environ["ALEMBIC_DATABASE_URL"] = sqlite_url

        alembic_dir = os.path.join(os.path.dirname(__file__), "..", "alembic")
        ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
        cfg = Config(ini_path)
        cfg.set_main_option("script_location", alembic_dir)
        cfg.set_main_option("sqlalchemy.url", sqlite_url)
        command.upgrade(cfg, "head")
        return cfg

    def _get_tables(self, db_path: str) -> set:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'alembic%'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        return tables

    def test_scanner_tables_created(self):
        """Migration 004 should create all 5 scanner tables."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            self._run_migration(db_path)
            tables = self._get_tables(db_path)
            expected = {"universe_members", "fundamentals_periodic", "fundamentals_derived",
                        "scan_runs", "scan_results"}
            assert expected.issubset(tables), f"Missing: {expected - tables}"
        finally:
            os.unlink(db_path)

    def test_total_tables_after_004(self):
        """After migration 004, should have 18 tables."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            self._run_migration(db_path)
            tables = self._get_tables(db_path)
            # 12 original + api_keys + 5 scanner = 18
            assert len(tables) >= 18, f"Expected >= 18 tables, got {len(tables)}: {tables}"
        finally:
            os.unlink(db_path)

    def test_fundamentals_periodic_columns(self):
        """fundamentals_periodic should have all required columns."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            self._run_migration(db_path)
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("PRAGMA table_info(fundamentals_periodic)")
            cols = {row[1] for row in cursor.fetchall()}
            conn.close()
            required = {"symbol", "period_end_date", "period_type", "revenue",
                        "operating_profit", "net_income", "total_assets", "total_equity",
                        "total_debt", "cash", "operating_cash_flow", "capex",
                        "dividends_paid", "shares_outstanding", "source", "provenance"}
            assert required.issubset(cols), f"Missing: {required - cols}"
        finally:
            os.unlink(db_path)

    def test_scan_results_has_tri_columns(self):
        """scan_results should have trailing return columns."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            self._run_migration(db_path)
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("PRAGMA table_info(scan_results)")
            cols = {row[1] for row in cursor.fetchall()}
            conn.close()
            tri_cols = {"tri_1y_ngn", "tri_3y_ngn", "tri_1y_usd", "tri_3y_usd",
                        "tri_1y_real", "tri_3y_real"}
            assert tri_cols.issubset(cols), f"Missing TRI cols: {tri_cols - cols}"
        finally:
            os.unlink(db_path)

    def test_downgrade_removes_scanner_tables(self):
        """Downgrade from 004 should remove scanner tables."""
        from alembic.config import Config
        from alembic import command

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            cfg = self._run_migration(db_path)
            command.downgrade(cfg, "003")
            tables = self._get_tables(db_path)
            scanner_tables = {"universe_members", "fundamentals_periodic",
                              "fundamentals_derived", "scan_runs", "scan_results"}
            assert not scanner_tables.intersection(tables), \
                f"Scanner tables still present: {scanner_tables.intersection(tables)}"
        finally:
            os.unlink(db_path)
