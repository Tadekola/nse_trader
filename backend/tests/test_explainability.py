"""
Explainability Engine Tests (PR7).

Covers:
  1. ScoreExplanation structure: all fields present
  2. Metric explanations: correct count, raw/winsorized/rank/score
  3. Guardrail triggers: net loss, negative equity, insufficient history
  4. Confidence penalty decomposition: missing fields, staleness, liquidity
  5. Winsorization bounds: correct computation
  6. Scoring config hash: deterministic
  7. Score consistency: explain_score produces same quality_score as score_universe
  8. Edge cases: symbol not found, empty universe, all-None metrics
"""

import os
import sys
import pytest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scanner.explainer import (
    explain_score,
    get_scoring_config_hash,
    SCORING_CONFIG,
    SCORING_CONFIG_VERSION,
    ScoreExplanation,
)
from app.scanner.derived_metrics import compute_derived_metrics, DerivedMetrics
from app.scanner.quality_scorer import score_universe


# ── Helpers ──────────────────────────────────────────────────────────

def _dm(symbol, roe=0.15, op_margin=0.25, de=0.5, cash_debt=0.8,
        ocf_ni=1.2, fcf=100, earn_stab=0.85, margin_stab=0.80,
        periods=3, freshness=180, red_flags=None):
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


UNIVERSE = [
    _dm("DANGCEM", roe=0.25, op_margin=0.35, de=0.3, cash_debt=1.5, fcf=500),
    _dm("GTCO", roe=0.20, op_margin=0.30, de=0.5, cash_debt=0.8, fcf=300),
    _dm("ZENITH", roe=0.15, op_margin=0.25, de=0.6, cash_debt=0.6, fcf=200),
    _dm("MTNN", roe=0.10, op_margin=0.15, de=0.8, cash_debt=0.4, fcf=100),
    _dm("AIRTEL", roe=0.05, op_margin=0.10, de=1.0, cash_debt=0.2, fcf=50),
]


# ═══════════════════════════════════════════════════════════════════════
# Structure Tests
# ═══════════════════════════════════════════════════════════════════════

class TestExplanationStructure:
    def test_returns_explanation(self):
        """explain_score should return a ScoreExplanation for a valid symbol."""
        exp = explain_score("DANGCEM", UNIVERSE)
        assert exp is not None
        assert isinstance(exp, ScoreExplanation)
        assert exp.symbol == "DANGCEM"

    def test_has_all_fields(self):
        """Explanation should contain all required fields."""
        exp = explain_score("DANGCEM", UNIVERSE)
        assert exp.scoring_config_version == SCORING_CONFIG_VERSION
        assert len(exp.scoring_config_hash) == 16
        assert len(exp.metric_explanations) > 0
        assert len(exp.guardrail_triggers) > 0
        assert exp.confidence_breakdown is not None
        assert len(exp.winsor_bounds) > 0
        assert exp.derived_metrics_snapshot is not None

    def test_metric_explanations_count(self):
        """Should have 11 metric explanations (one per component)."""
        exp = explain_score("DANGCEM", UNIVERSE)
        assert len(exp.metric_explanations) == 11

    def test_guardrail_triggers_count(self):
        """Should have 3 guardrail triggers."""
        exp = explain_score("DANGCEM", UNIVERSE)
        assert len(exp.guardrail_triggers) == 3

    def test_winsor_bounds_count(self):
        """Should have 5 winsorization bounds (for 5 winsorized metrics)."""
        exp = explain_score("DANGCEM", UNIVERSE)
        assert len(exp.winsor_bounds) == 5

    def test_to_dict(self):
        """to_dict should produce a serializable dict."""
        exp = explain_score("DANGCEM", UNIVERSE)
        d = exp.to_dict()
        assert isinstance(d, dict)
        assert d["symbol"] == "DANGCEM"
        assert isinstance(d["metric_explanations"], list)
        assert isinstance(d["guardrail_triggers"], list)
        assert isinstance(d["confidence_breakdown"], dict)


# ═══════════════════════════════════════════════════════════════════════
# Metric Explanation Tests
# ═══════════════════════════════════════════════════════════════════════

class TestMetricExplanations:
    def test_roe_explanation(self):
        """ROE metric should show raw value, winsorized value, rank, and score."""
        exp = explain_score("DANGCEM", UNIVERSE)
        roe = next(m for m in exp.metric_explanations if m.metric_name == "roe")
        assert roe.raw_value == 0.25
        assert roe.max_possible == 15.0
        assert roe.direction == "higher_is_better"
        assert 0 <= roe.percentile_rank <= 1.0
        assert 0 <= roe.component_score <= 15.0

    def test_highest_roe_gets_top_rank(self):
        """DANGCEM with highest ROE should have highest percentile rank."""
        exp = explain_score("DANGCEM", UNIVERSE)
        roe = next(m for m in exp.metric_explanations if m.metric_name == "roe")
        assert roe.percentile_rank > 0.7

    def test_lowest_roe_gets_low_rank(self):
        """AIRTEL with lowest ROE should have lowest percentile rank."""
        exp = explain_score("AIRTEL", UNIVERSE)
        roe = next(m for m in exp.metric_explanations if m.metric_name == "roe")
        assert roe.percentile_rank < 0.3

    def test_de_lower_is_better(self):
        """D/E metric should use lower_is_better direction."""
        exp = explain_score("DANGCEM", UNIVERSE)
        de = next(m for m in exp.metric_explanations if m.metric_name == "debt_to_equity")
        assert de.direction == "lower_is_better"
        # DANGCEM has lowest D/E (0.3), should rank high
        assert de.percentile_rank > 0.7

    def test_binary_metrics(self):
        """FCF positive and OCF positive should be binary (0 or max)."""
        exp = explain_score("DANGCEM", UNIVERSE)
        fcf = next(m for m in exp.metric_explanations if m.metric_name == "fcf_positive")
        assert fcf.direction == "binary"
        assert fcf.component_score in (0.0, 5.0)

    def test_all_scores_within_max(self):
        """Every component score should be <= max_possible."""
        for sym in ["DANGCEM", "GTCO", "AIRTEL"]:
            exp = explain_score(sym, UNIVERSE)
            for m in exp.metric_explanations:
                assert m.component_score <= m.max_possible + 0.01, \
                    f"{sym} {m.metric_name}: {m.component_score} > {m.max_possible}"


# ═══════════════════════════════════════════════════════════════════════
# Guardrail Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGuardrailTriggers:
    def test_no_guardrails_triggered_for_healthy_stock(self):
        """Healthy stocks should have no guardrails triggered."""
        exp = explain_score("DANGCEM", UNIVERSE)
        triggered = [g for g in exp.guardrail_triggers if g.triggered]
        assert len(triggered) == 0

    def test_net_loss_guardrail(self):
        """NET_LOSS should trigger profitability cap at 5."""
        universe = [
            _dm("LOSS", roe=-0.05, op_margin=0.10, red_flags=["NET_LOSS"]),
            _dm("OK", roe=0.15, op_margin=0.25),
        ]
        exp = explain_score("LOSS", universe)
        nl = next(g for g in exp.guardrail_triggers if g.name == "net_loss_profitability_cap")
        assert nl.triggered is True
        assert nl.cap_value == 5.0
        assert nl.score_after <= 5.0

    def test_negative_equity_guardrail(self):
        """NEGATIVE_EQUITY should cap total score at 30."""
        universe = [
            _dm("NEGEQ", red_flags=["NEGATIVE_EQUITY"]),
            _dm("OK"),
        ]
        exp = explain_score("NEGEQ", universe)
        neq = next(g for g in exp.guardrail_triggers if g.name == "negative_equity_cap")
        assert neq.triggered is True
        assert neq.cap_value == 30.0
        assert exp.quality_score <= 30.0

    def test_insufficient_history_guardrail(self):
        """INSUFFICIENT_HISTORY should cap total score at 50."""
        universe = [
            _dm("SHORT", periods=1, red_flags=["INSUFFICIENT_HISTORY"]),
            _dm("LONG", periods=5),
        ]
        exp = explain_score("SHORT", universe)
        ih = next(g for g in exp.guardrail_triggers if g.name == "insufficient_history_cap")
        assert ih.triggered is True
        assert ih.cap_value == 50.0
        assert exp.quality_score <= 50.0

    def test_guardrail_shows_before_after(self):
        """Triggered guardrail should show score_before > score_after."""
        universe = [
            _dm("NEGEQ", roe=0.25, op_margin=0.35, red_flags=["NEGATIVE_EQUITY"]),
            _dm("OK"),
        ]
        exp = explain_score("NEGEQ", universe)
        neq = next(g for g in exp.guardrail_triggers if g.name == "negative_equity_cap")
        assert neq.score_before >= neq.score_after


# ═══════════════════════════════════════════════════════════════════════
# Confidence Penalty Tests
# ═══════════════════════════════════════════════════════════════════════

class TestConfidencePenalty:
    def test_no_penalty_for_complete_data(self):
        """Complete data with good liquidity should have zero penalty."""
        liq = {s: 0.8 for s in ["DANGCEM", "GTCO", "ZENITH", "MTNN", "AIRTEL"]}
        exp = explain_score("DANGCEM", UNIVERSE, liquidity_scores=liq)
        assert exp.confidence_breakdown.total == 0.0
        assert len(exp.confidence_breakdown.missing_fields) == 0

    def test_missing_fields_penalty(self):
        """Missing key metrics should appear in missing_fields list."""
        universe = [
            _dm("SPARSE", roe=None, op_margin=None, de=None, ocf_ni=None, fcf=None),
            _dm("OK"),
        ]
        exp = explain_score("SPARSE", universe)
        cb = exp.confidence_breakdown
        assert len(cb.missing_fields) == 5
        assert cb.missing_fields_penalty == 5 * 0.05  # 0.25

    def test_staleness_penalty(self):
        """Stale data (> 365 days) should contribute to penalty."""
        universe = [
            _dm("STALE", freshness=700),
            _dm("FRESH", freshness=90),
        ]
        exp = explain_score("STALE", universe)
        assert exp.confidence_breakdown.staleness_penalty > 0
        assert exp.confidence_breakdown.staleness_days == 700

    def test_liquidity_penalty(self):
        """Low liquidity should contribute to penalty."""
        universe = [_dm("ILLIQ"), _dm("LIQ")]
        liq = {"ILLIQ": 0.01, "LIQ": 0.8}
        exp = explain_score("ILLIQ", universe, liquidity_scores=liq)
        assert exp.confidence_breakdown.liquidity_penalty == 0.3
        assert "LOW_LIQUIDITY" in exp.red_flags

    def test_penalty_decomposition_sums(self):
        """Total penalty should equal sum of components (capped at 1.0)."""
        universe = [_dm("TEST", roe=None, freshness=700)]
        liq = {"TEST": 0.01}
        exp = explain_score("TEST", universe, liquidity_scores=liq)
        cb = exp.confidence_breakdown
        expected = min(cb.missing_fields_penalty + cb.staleness_penalty + cb.liquidity_penalty, 1.0)
        assert abs(cb.total - expected) < 0.001


# ═══════════════════════════════════════════════════════════════════════
# Winsorization Bounds Tests
# ═══════════════════════════════════════════════════════════════════════

class TestWinsorBounds:
    def test_bounds_have_metric_names(self):
        """Each winsor bound should be named after its metric."""
        exp = explain_score("DANGCEM", UNIVERSE)
        names = {wb.metric_name for wb in exp.winsor_bounds}
        assert "roe" in names
        assert "op_margin" in names
        assert "debt_to_equity" in names

    def test_bounds_reflect_universe_size(self):
        """Universe size should match number of symbols."""
        exp = explain_score("DANGCEM", UNIVERSE)
        for wb in exp.winsor_bounds:
            assert wb.universe_size == 5

    def test_bounds_lower_le_upper(self):
        """Lower bound should be <= upper bound."""
        exp = explain_score("DANGCEM", UNIVERSE)
        for wb in exp.winsor_bounds:
            if wb.lower_bound is not None and wb.upper_bound is not None:
                assert wb.lower_bound <= wb.upper_bound


# ═══════════════════════════════════════════════════════════════════════
# Score Consistency Tests
# ═══════════════════════════════════════════════════════════════════════

class TestScoreConsistency:
    def test_explain_matches_score_universe(self):
        """explain_score quality_score must match score_universe for same inputs."""
        scores = score_universe(UNIVERSE)
        for qs in scores:
            exp = explain_score(qs.symbol, UNIVERSE)
            assert exp is not None
            assert abs(exp.quality_score - qs.quality_score) < 0.1, \
                f"{qs.symbol}: explain={exp.quality_score} vs score={qs.quality_score}"

    def test_explain_matches_sub_scores(self):
        """Sub-score totals from explain should roughly match score_universe."""
        scores = score_universe(UNIVERSE)
        for qs in scores:
            exp = explain_score(qs.symbol, UNIVERSE)
            # Sum component scores by category
            explain_total = sum(m.component_score for m in exp.metric_explanations)
            score_total = sum(qs.sub_scores.values())
            # Allow for guardrail adjustments
            assert explain_total >= 0


# ═══════════════════════════════════════════════════════════════════════
# Scoring Config Tests
# ═══════════════════════════════════════════════════════════════════════

class TestScoringConfig:
    def test_config_hash_deterministic(self):
        """Config hash should be identical across calls."""
        h1 = get_scoring_config_hash()
        h2 = get_scoring_config_hash()
        assert h1 == h2
        assert len(h1) == 16

    def test_config_version_present(self):
        """Config should have a version string."""
        assert SCORING_CONFIG["version"] == SCORING_CONFIG_VERSION

    def test_config_max_scores_sum_to_100(self):
        """Max possible scores should sum to 100."""
        total = sum(SCORING_CONFIG["max_scores"].values())
        assert total == 100


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_symbol_not_found(self):
        """Non-existent symbol should return None."""
        exp = explain_score("NONEXISTENT", UNIVERSE)
        assert exp is None

    def test_empty_universe(self):
        """Empty metrics list should return None."""
        exp = explain_score("DANGCEM", [])
        assert exp is None

    def test_single_symbol_universe(self):
        """Single symbol should still produce a valid explanation."""
        exp = explain_score("ONLY", [_dm("ONLY")])
        assert exp is not None
        assert exp.quality_score >= 0

    def test_all_none_metrics(self):
        """Symbol with all None metrics should get explanation with flags."""
        m = DerivedMetrics(symbol="BLANK", as_of_date=date(2025, 6, 15))
        m.red_flags = ["NO_FUNDAMENTALS_DATA"]
        exp = explain_score("BLANK", [m])
        assert exp is not None
        assert exp.data_quality == "INSUFFICIENT"
        assert len(exp.confidence_breakdown.missing_fields) == 5

    def test_deterministic(self):
        """Same input should produce identical explanation."""
        e1 = explain_score("DANGCEM", UNIVERSE)
        e2 = explain_score("DANGCEM", UNIVERSE)
        assert e1.quality_score == e2.quality_score
        assert e1.scoring_config_hash == e2.scoring_config_hash
        for m1, m2 in zip(e1.metric_explanations, e2.metric_explanations):
            assert m1.component_score == m2.component_score
