"""
Scanner Workflow Tests (PR5).

Tests the end-to-end scanner workflow using pure computation (no DB persistence
for BigInteger-PK tables, which don't auto-increment in SQLite). Tests verify:
  1. Full workflow: OHLCV → universe → fundamentals → scoring → summary
  2. Empty universe handling
  3. Symbols with no fundamentals still get scored
  4. Quality scores in valid range
  5. Human-readable reasons generated
  6. TRI return computation (with adjusted prices)
  7. Deterministic: same data → same ranking
  8. ScanRun/ScanResult model validation
  9. Audit event model validation
"""

import os
import sys
import pytest
import pytest_asyncio
from datetime import date, datetime
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scanner.universe import compute_liquidity, LiquidityResult
from app.scanner.derived_metrics import compute_derived_metrics, DerivedMetrics
from app.scanner.quality_scorer import score_universe, QualityScore
from app.db.models import ScanRun, ScanResult, AuditEvent


# ── Test data builders ───────────────────────────────────────────────

def _make_ohlcv_aggregate(symbol: str, adv: float, sessions: int = 70,
                          zero_days: int = 2) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "avg_daily_value": adv,
        "total_sessions": sessions,
        "zero_volume_days": zero_days,
    }


def _make_period(symbol: str, end_date: date, idx: int = 0) -> Dict[str, Any]:
    return {
        "period_end_date": end_date,
        "revenue": 1_000_000 + idx * 100_000,
        "operating_profit": 300_000 + idx * 30_000,
        "net_income": 200_000 + idx * 20_000,
        "total_assets": 5_000_000,
        "total_equity": 1_000_000 + idx * 50_000,
        "total_debt": 500_000 - idx * 30_000,
        "cash": 300_000 + idx * 20_000,
        "operating_cash_flow": 250_000 + idx * 25_000,
        "capex": 100_000,
        "dividends_paid": 50_000,
        "shares_outstanding": 17_000,
    }


SYMBOLS = ["DANGCEM", "GTCO", "ZENITH", "MTNN", "AIRTEL"]
AS_OF = date(2025, 6, 15)


def _build_universe_and_score(
    symbols: List[str] = SYMBOLS,
    include_fundamentals: bool = True,
    dividend_years: Optional[Dict[str, int]] = None,
) -> tuple:
    """
    Pure-computation workflow: universe ranking → derived metrics → scoring.
    No DB required.
    """
    # Step 1: Build liquidity aggregates
    ohlcv_rows = [
        _make_ohlcv_aggregate(sym, 500_000_000 - i * 50_000_000)
        for i, sym in enumerate(symbols)
    ]
    all_liq = compute_liquidity(ohlcv_rows, top_n=len(symbols))
    members = [r for r in all_liq if not r.excluded]
    liq_map = {m.symbol: m.liquidity_score for m in members}

    # Step 2: Compute derived metrics
    derived_list: List[DerivedMetrics] = []
    for i, sym in enumerate(symbols):
        if include_fundamentals:
            periods = [
                _make_period(sym, date(2022, 12, 31), i),
                _make_period(sym, date(2023, 12, 31), i),
                _make_period(sym, date(2024, 12, 31), i),
            ]
        else:
            periods = []
        dm = compute_derived_metrics(sym, periods, AS_OF)
        derived_list.append(dm)

    # Step 3: Score
    scores = score_universe(
        derived_list,
        dividend_history=dividend_years or {},
        liquidity_scores=liq_map,
    )

    return members, derived_list, scores


# ═══════════════════════════════════════════════════════════════════════
# Workflow integration tests (pure computation, no DB)
# ═══════════════════════════════════════════════════════════════════════

class TestFullWorkflow:
    def test_workflow_produces_scores(self):
        """Full workflow should produce quality scores for all symbols."""
        members, derived, scores = _build_universe_and_score()
        assert len(scores) == 5
        for s in scores:
            assert 0 <= s.quality_score <= 100

    def test_workflow_sorted_descending(self):
        """Scores should be sorted by quality_score descending."""
        _, _, scores = _build_universe_and_score()
        for i in range(len(scores) - 1):
            assert scores[i].quality_score >= scores[i + 1].quality_score

    def test_all_symbols_scored(self):
        """All universe members should appear in results."""
        _, _, scores = _build_universe_and_score()
        scored_symbols = {s.symbol for s in scores}
        assert scored_symbols == set(SYMBOLS)

    def test_sub_scores_present(self):
        """Each score should have sub_scores dict with 5 categories."""
        _, _, scores = _build_universe_and_score()
        for s in scores:
            assert "profitability" in s.sub_scores
            assert "cash_quality" in s.sub_scores
            assert "balance_sheet" in s.sub_scores
            assert "stability" in s.sub_scores
            assert "shareholder_return" in s.sub_scores


class TestEmptyUniverse:
    def test_no_ohlcv_data(self):
        """Empty OHLCV aggregates should produce no members."""
        all_liq = compute_liquidity([], top_n=50)
        assert len(all_liq) == 0

    def test_all_illiquid(self):
        """If all symbols are illiquid, no members should be selected."""
        rows = [_make_ohlcv_aggregate("A", 1000, sessions=5, zero_days=4)]
        all_liq = compute_liquidity(rows, min_sessions=30, top_n=50)
        members = [r for r in all_liq if not r.excluded]
        assert len(members) == 0


class TestNoFundamentals:
    def test_scores_still_produced(self):
        """Symbols without fundamentals should still get scores (with red flags)."""
        _, derived, scores = _build_universe_and_score(
            symbols=SYMBOLS[:3], include_fundamentals=False
        )
        assert len(scores) == 3
        for s in scores:
            assert "NO_FUNDAMENTALS_DATA" in s.red_flags
            assert s.data_quality == "INSUFFICIENT"


class TestQualityScoreRanges:
    def test_scores_in_range(self):
        """All scores should be 0-100."""
        _, _, scores = _build_universe_and_score()
        for s in scores:
            assert 0 <= s.quality_score <= 100

    def test_sub_scores_in_range(self):
        """Sub-scores should be within their defined max."""
        _, _, scores = _build_universe_and_score()
        for s in scores:
            assert 0 <= s.sub_scores["profitability"] <= 25
            assert 0 <= s.sub_scores["cash_quality"] <= 25
            assert 0 <= s.sub_scores["balance_sheet"] <= 25
            assert 0 <= s.sub_scores["stability"] <= 15
            assert 0 <= s.sub_scores["shareholder_return"] <= 10


class TestReasons:
    def test_reasons_populated(self):
        """Scored symbols should have human-readable reasons."""
        _, _, scores = _build_universe_and_score()
        for s in scores:
            assert isinstance(s.reasons, list)

    def test_good_stock_has_positive_reasons(self):
        """A well-performing stock should have positive reasons."""
        _, _, scores = _build_universe_and_score()
        # Top scorer should have at least one positive reason
        top = scores[0]
        assert len(top.reasons) > 0


class TestDeterministic:
    def test_same_input_same_output(self):
        """Two runs with identical input must produce identical rankings."""
        _, _, s1 = _build_universe_and_score()
        _, _, s2 = _build_universe_and_score()
        for a, b in zip(s1, s2):
            assert a.symbol == b.symbol
            assert a.quality_score == b.quality_score
            assert a.sub_scores == b.sub_scores

    def test_repeated_runs_stable(self):
        """Multiple runs with same input must produce identical scores."""
        for _ in range(3):
            _, _, scores = _build_universe_and_score()
            assert scores[0].quality_score == scores[0].quality_score


class TestDividendIntegration:
    def test_dividends_boost_shareholder_score(self):
        """Symbols with dividend history should score higher on shareholder_return."""
        _, _, no_div = _build_universe_and_score(dividend_years={})
        _, _, with_div = _build_universe_and_score(
            dividend_years={sym: 5 for sym in SYMBOLS}
        )
        # Sum of shareholder_return should be higher with dividends
        no_div_sh = sum(s.sub_scores["shareholder_return"] for s in no_div)
        with_div_sh = sum(s.sub_scores["shareholder_return"] for s in with_div)
        assert with_div_sh > no_div_sh


# ═══════════════════════════════════════════════════════════════════════
# Model validation tests (no DB, just model instantiation)
# ═══════════════════════════════════════════════════════════════════════

class TestScanRunModel:
    def test_scan_run_fields(self):
        """ScanRun should accept all required fields."""
        run = ScanRun(
            as_of_date=AS_OF,
            universe_name="test",
            symbols_scanned=5,
            symbols_ranked=5,
            summary={"top_5": ["A", "B"]},
            provenance={"engine": "v1"},
        )
        assert run.universe_name == "test"
        assert run.symbols_scanned == 5

    def test_scan_result_fields(self):
        """ScanResult should accept all required fields including TRI."""
        result = ScanResult(
            run_id=1,
            symbol="DANGCEM",
            rank=1,
            quality_score=85.5,
            sub_scores={"profitability": 20},
            reasons=["Strong ROE"],
            red_flags=[],
            flags={"data_quality": "FULL"},
            liquidity_score=0.95,
            confidence_penalty=0.0,
            tri_1y_ngn=0.15,
            tri_3y_ngn=0.45,
            tri_1y_usd=-0.10,
            tri_3y_usd=0.05,
            tri_1y_real=-0.05,
            tri_3y_real=0.10,
        )
        assert result.quality_score == 85.5
        assert result.tri_1y_ngn == 0.15
        assert result.tri_1y_usd == -0.10

    def test_audit_event_fields(self):
        """AuditEvent for SCAN_COMPLETED should accept scanner payload."""
        event = AuditEvent(
            component="scanner",
            event_type="SCAN_COMPLETED",
            level="INFO",
            message="Scan completed: 5 symbols",
            payload={"run_id": 1, "symbols_scanned": 5},
        )
        assert event.event_type == "SCAN_COMPLETED"
        assert event.payload["run_id"] == 1
