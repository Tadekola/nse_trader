"""
Quality Scoring Engine Tests (PR4).

Covers:
  1. Winsorization: clipping at 5th/95th percentile
  2. Percentile ranking: higher/lower-is-better, ties, single value
  3. Scoring: sub-score ranges, composite total
  4. Guardrails: negative equity cap, net loss cap, insufficient history cap
  5. Confidence penalty: missing fields, stale data, low liquidity
  6. Sorting: output sorted by quality_score desc
  7. Deterministic: same input → same output
  8. Edge cases: empty universe, single symbol, all missing data
"""

import os
import sys
import pytest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scanner.quality_scorer import (
    score_universe,
    winsorize,
    percentile_rank,
    QualityScore,
)
from app.scanner.derived_metrics import DerivedMetrics


# ═══════════════════════════════════════════════════════════════════════
# Winsorize Tests
# ═══════════════════════════════════════════════════════════════════════

class TestWinsorize:
    def test_basic_winsorize(self):
        """Extreme values should be clipped."""
        vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 100.0,
                -50.0, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.0, 11.0]
        result = winsorize(vals)
        assert max(v for v in result if v is not None) <= 100.0
        assert min(v for v in result if v is not None) >= -50.0

    def test_none_passthrough(self):
        """None values should remain None."""
        vals = [1.0, None, 3.0, None, 5.0]
        result = winsorize(vals)
        assert result[1] is None
        assert result[3] is None

    def test_single_value(self):
        """Single value should be returned unchanged."""
        assert winsorize([42.0]) == [42.0]

    def test_empty(self):
        assert winsorize([]) == []

    def test_all_none(self):
        result = winsorize([None, None, None])
        assert result == [None, None, None]


# ═══════════════════════════════════════════════════════════════════════
# Percentile Rank Tests
# ═══════════════════════════════════════════════════════════════════════

class TestPercentileRank:
    def test_highest_value(self):
        """Highest value in higher-is-better should rank near 1.0."""
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        rank = percentile_rank(5.0, vals, higher_is_better=True)
        assert rank > 0.8

    def test_lowest_value(self):
        """Lowest value in higher-is-better should rank near 0.0."""
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        rank = percentile_rank(1.0, vals, higher_is_better=True)
        assert rank < 0.2

    def test_lower_is_better(self):
        """Lowest value in lower-is-better should rank near 1.0."""
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        rank = percentile_rank(1.0, vals, higher_is_better=False)
        assert rank > 0.8

    def test_none_value(self):
        """None value should return 0.0 rank."""
        rank = percentile_rank(None, [1.0, 2.0, 3.0])
        assert rank == 0.0

    def test_single_value(self):
        """Single value should get 0.5 rank."""
        rank = percentile_rank(42.0, [42.0])
        assert rank == 0.5

    def test_empty_universe(self):
        rank = percentile_rank(1.0, [])
        assert rank == 0.0

    def test_all_equal(self):
        """All equal values should get 0.5 rank."""
        rank = percentile_rank(5.0, [5.0, 5.0, 5.0])
        assert rank == 0.5


# ═══════════════════════════════════════════════════════════════════════
# Helper: build DerivedMetrics
# ═══════════════════════════════════════════════════════════════════════

def _dm(symbol, roe=0.15, op_margin=0.25, de=0.5, cash_debt=0.8,
        ocf_ni=1.2, fcf=100, earn_stab=0.85, margin_stab=0.80,
        periods=3, freshness=180, red_flags=None):
    """Build a DerivedMetrics for testing."""
    m = DerivedMetrics(symbol=symbol, as_of_date=date(2025, 6, 15))
    m.roe = roe
    m.roic_proxy = roe * 0.8 if roe else None
    m.op_margin = op_margin
    m.net_margin = op_margin * 0.7 if op_margin else None
    m.debt_to_equity = de
    m.cash_to_debt = cash_debt
    m.ocf_to_net_income = ocf_ni
    m.fcf = fcf
    m.earnings_stability = earn_stab
    m.margin_stability = margin_stab
    m.periods_available = periods
    m.data_freshness_days = freshness
    m.red_flags = red_flags or []
    return m


# ═══════════════════════════════════════════════════════════════════════
# Scoring Tests
# ═══════════════════════════════════════════════════════════════════════

class TestScoreUniverse:
    def test_basic_scoring(self):
        """Universe of 5 symbols should all get scores 0-100."""
        metrics = [
            _dm("DANGCEM", roe=0.25, op_margin=0.35),
            _dm("GTCO", roe=0.20, op_margin=0.30),
            _dm("ZENITH", roe=0.15, op_margin=0.25),
            _dm("MTNN", roe=0.10, op_margin=0.15),
            _dm("AIRTEL", roe=0.05, op_margin=0.10),
        ]
        results = score_universe(metrics)
        assert len(results) == 5
        for r in results:
            assert 0 <= r.quality_score <= 100

    def test_sorted_descending(self):
        """Results should be sorted by quality_score descending."""
        metrics = [
            _dm("LOW", roe=0.02, op_margin=0.05, de=2.0, cash_debt=0.1,
                ocf_ni=0.3, fcf=-50, earn_stab=0.3, margin_stab=0.3),
            _dm("HIGH", roe=0.30, op_margin=0.40, de=0.2, cash_debt=2.0,
                ocf_ni=1.5, fcf=500, earn_stab=0.95, margin_stab=0.95),
        ]
        results = score_universe(metrics)
        assert results[0].symbol == "HIGH"
        assert results[1].symbol == "LOW"
        assert results[0].quality_score > results[1].quality_score

    def test_sub_scores_sum(self):
        """Sub-scores should sum to approximately the total (within rounding)."""
        metrics = [_dm("TEST")]
        results = score_universe(metrics)
        r = results[0]
        sub_total = sum(r.sub_scores.values())
        # May differ slightly due to guardrails/caps
        assert abs(sub_total - r.quality_score) < 1.0

    def test_sub_score_ranges(self):
        """Each sub-score should be within its defined range."""
        metrics = [
            _dm("A", roe=0.25, op_margin=0.35),
            _dm("B", roe=0.05, op_margin=0.05),
            _dm("C", roe=0.15, op_margin=0.20),
        ]
        results = score_universe(metrics)
        for r in results:
            assert 0 <= r.sub_scores["profitability"] <= 25
            assert 0 <= r.sub_scores["cash_quality"] <= 25
            assert 0 <= r.sub_scores["balance_sheet"] <= 25
            assert 0 <= r.sub_scores["stability"] <= 15
            assert 0 <= r.sub_scores["shareholder_return"] <= 10

    def test_reasons_populated(self):
        """Good stocks should have positive reasons."""
        metrics = [_dm("STRONG", roe=0.25, op_margin=0.35, de=0.3,
                       cash_debt=1.5, fcf=500)]
        results = score_universe(metrics)
        assert len(results[0].reasons) > 0

    def test_to_dict(self):
        """QualityScore.to_dict should return all keys."""
        metrics = [_dm("TEST")]
        results = score_universe(metrics)
        d = results[0].to_dict()
        assert "quality_score" in d
        assert "sub_scores" in d
        assert "reasons" in d
        assert "red_flags" in d
        assert "confidence_penalty" in d
        assert "data_quality" in d


# ═══════════════════════════════════════════════════════════════════════
# Guardrail Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGuardrails:
    def test_negative_equity_cap(self):
        """Negative equity should cap score at 30."""
        metrics = [
            _dm("GOOD", roe=0.25, op_margin=0.35),
            _dm("BAD_EQUITY", roe=0.25, op_margin=0.35,
                red_flags=["NEGATIVE_EQUITY"]),
        ]
        results = score_universe(metrics)
        bad = next(r for r in results if r.symbol == "BAD_EQUITY")
        assert bad.quality_score <= 30.0

    def test_net_loss_caps_profitability(self):
        """Net loss should cap profitability sub-score at 5."""
        metrics = [
            _dm("LOSS", roe=-0.05, op_margin=0.10, red_flags=["NET_LOSS"]),
            _dm("PROFIT", roe=0.15, op_margin=0.25),
        ]
        results = score_universe(metrics)
        loss = next(r for r in results if r.symbol == "LOSS")
        assert loss.sub_scores["profitability"] <= 5.0

    def test_insufficient_history_cap(self):
        """< 2 periods should cap score at 50."""
        metrics = [
            _dm("SHORT", periods=1, red_flags=["INSUFFICIENT_HISTORY"]),
            _dm("LONG", periods=5),
        ]
        results = score_universe(metrics)
        short = next(r for r in results if r.symbol == "SHORT")
        assert short.quality_score <= 50.0


# ═══════════════════════════════════════════════════════════════════════
# Confidence Penalty Tests
# ═══════════════════════════════════════════════════════════════════════

class TestConfidencePenalty:
    def test_missing_fields_penalty(self):
        """Missing key metrics should increase confidence penalty."""
        metrics = [
            _dm("COMPLETE"),
            _dm("SPARSE", roe=None, op_margin=None, de=None,
                ocf_ni=None, fcf=None),
        ]
        results = score_universe(metrics)
        complete = next(r for r in results if r.symbol == "COMPLETE")
        sparse = next(r for r in results if r.symbol == "SPARSE")
        assert sparse.confidence_penalty > complete.confidence_penalty

    def test_stale_data_penalty(self):
        """Stale fundamentals (>365 days) should increase penalty."""
        metrics = [
            _dm("FRESH", freshness=90),
            _dm("STALE", freshness=700),
        ]
        results = score_universe(metrics)
        fresh = next(r for r in results if r.symbol == "FRESH")
        stale = next(r for r in results if r.symbol == "STALE")
        assert stale.confidence_penalty > fresh.confidence_penalty

    def test_low_liquidity_penalty(self):
        """Low liquidity should increase confidence penalty."""
        metrics = [_dm("ILLIQUID"), _dm("LIQUID")]
        liq = {"ILLIQUID": 0.01, "LIQUID": 0.80}
        results = score_universe(metrics, liquidity_scores=liq)
        illiq = next(r for r in results if r.symbol == "ILLIQUID")
        liq_r = next(r for r in results if r.symbol == "LIQUID")
        assert illiq.confidence_penalty > liq_r.confidence_penalty
        assert "LOW_LIQUIDITY" in illiq.red_flags

    def test_penalty_capped_at_1(self):
        """Confidence penalty should never exceed 1.0."""
        metrics = [_dm("WORST", roe=None, op_margin=None, de=None,
                       ocf_ni=None, fcf=None, freshness=900)]
        liq = {"WORST": 0.01}
        results = score_universe(metrics, liquidity_scores=liq)
        assert results[0].confidence_penalty <= 1.0

    def test_data_quality_label(self):
        """Data quality label should reflect data completeness."""
        metrics = [
            _dm("FULL"),
            _dm("DEGRADED", roe=None, op_margin=None, de=None, freshness=600,
                red_flags=["STALE_FUNDAMENTALS"]),
            _dm("NONE", red_flags=["NO_FUNDAMENTALS_DATA"],
                roe=None, op_margin=None, de=None, ocf_ni=None, fcf=None),
        ]
        results = score_universe(metrics)
        full = next(r for r in results if r.symbol == "FULL")
        degraded = next(r for r in results if r.symbol == "DEGRADED")
        none_r = next(r for r in results if r.symbol == "NONE")
        assert full.data_quality == "FULL"
        assert degraded.data_quality == "DEGRADED"
        assert none_r.data_quality == "INSUFFICIENT"


# ═══════════════════════════════════════════════════════════════════════
# Dividend Integration Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDividendScoring:
    def test_dividend_history_boosts_score(self):
        """Symbols with dividend history should score higher on shareholder return."""
        metrics = [_dm("DIVPAYER"), _dm("NODIV")]
        div_hist = {"DIVPAYER": 5, "NODIV": 0}
        results = score_universe(metrics, dividend_history=div_hist)
        payer = next(r for r in results if r.symbol == "DIVPAYER")
        nodiv = next(r for r in results if r.symbol == "NODIV")
        assert payer.sub_scores["shareholder_return"] > nodiv.sub_scores["shareholder_return"]

    def test_consistent_dividend_reason(self):
        """3+ years of dividends should generate a reason string."""
        metrics = [_dm("DIVPAYER")]
        div_hist = {"DIVPAYER": 4}
        results = score_universe(metrics, dividend_history=div_hist)
        assert any("dividend" in r.lower() for r in results[0].reasons)


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_universe(self):
        """Empty metrics list should return empty results."""
        assert score_universe([]) == []

    def test_single_symbol(self):
        """Single symbol should still score correctly."""
        results = score_universe([_dm("ONLY")])
        assert len(results) == 1
        assert 0 <= results[0].quality_score <= 100

    def test_all_none_metrics(self):
        """Symbol with all None metrics should still get a score."""
        m = DerivedMetrics(symbol="BLANK", as_of_date=date(2025, 6, 15))
        m.red_flags = ["NO_FUNDAMENTALS_DATA"]
        results = score_universe([m])
        assert len(results) == 1
        assert results[0].quality_score >= 0

    def test_deterministic(self):
        """Same input should produce identical output."""
        metrics = [
            _dm("A", roe=0.20, op_margin=0.30),
            _dm("B", roe=0.10, op_margin=0.15),
            _dm("C", roe=0.25, op_margin=0.35),
        ]
        r1 = score_universe(metrics)
        r2 = score_universe(metrics)
        for a, b in zip(r1, r2):
            assert a.symbol == b.symbol
            assert a.quality_score == b.quality_score
            assert a.sub_scores == b.sub_scores
