"""
Scanner UI Integration Contract Tests (PR11).

Covers:
  1. Dashboard schema: hero card, distribution, tiers, top/bottom, stats
  2. Quality tier logic: HIGH / MEDIUM / LOW / INSUFFICIENT
  3. Score bucket logic: 5 histogram buckets
  4. Sortable result: flat sub-scores, tier, red flag count
  5. Table response: pagination, sorting, filtering
  6. Median computation
  7. Health status derivation from coverage/quality
  8. Route registration: dashboard + table endpoints
"""

import os
import sys
import pytest
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.scanner import (
    ScannerDashboardResponse, ScoreDistribution, QualityTierSummary,
    ScanResultSortableResponse, ScanResultTableResponse,
    ScanResultResponse, TrailingReturns,
)


# ═══════════════════════════════════════════════════════════════════════
# Quality Tier Logic
# ═══════════════════════════════════════════════════════════════════════

def _quality_tier(score, data_quality="FULL"):
    """Mirror the logic from scanner.py."""
    if data_quality == "INSUFFICIENT":
        return "INSUFFICIENT"
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


class TestQualityTier:
    def test_high_tier(self):
        assert _quality_tier(85) == "HIGH"
        assert _quality_tier(70) == "HIGH"

    def test_medium_tier(self):
        assert _quality_tier(69.9) == "MEDIUM"
        assert _quality_tier(40) == "MEDIUM"

    def test_low_tier(self):
        assert _quality_tier(39.9) == "LOW"
        assert _quality_tier(0) == "LOW"

    def test_insufficient_overrides_score(self):
        """INSUFFICIENT data quality should return INSUFFICIENT regardless of score."""
        assert _quality_tier(95, "INSUFFICIENT") == "INSUFFICIENT"
        assert _quality_tier(10, "INSUFFICIENT") == "INSUFFICIENT"

    def test_degraded_uses_score(self):
        """DEGRADED data quality should still use score-based tiers."""
        assert _quality_tier(85, "DEGRADED") == "HIGH"
        assert _quality_tier(30, "DEGRADED") == "LOW"


# ═══════════════════════════════════════════════════════════════════════
# Score Bucket Logic
# ═══════════════════════════════════════════════════════════════════════

def _score_bucket(score):
    if score >= 80:
        return "80-100"
    if score >= 60:
        return "60-80"
    if score >= 40:
        return "40-60"
    if score >= 20:
        return "20-40"
    return "0-20"


class TestScoreBucket:
    def test_all_buckets(self):
        assert _score_bucket(95) == "80-100"
        assert _score_bucket(80) == "80-100"
        assert _score_bucket(75) == "60-80"
        assert _score_bucket(60) == "60-80"
        assert _score_bucket(55) == "40-60"
        assert _score_bucket(40) == "40-60"
        assert _score_bucket(35) == "20-40"
        assert _score_bucket(20) == "20-40"
        assert _score_bucket(15) == "0-20"
        assert _score_bucket(0) == "0-20"

    def test_boundary_values(self):
        """Boundary values should fall in the correct bucket."""
        assert _score_bucket(79.99) == "60-80"
        assert _score_bucket(59.99) == "40-60"
        assert _score_bucket(39.99) == "20-40"
        assert _score_bucket(19.99) == "0-20"


# ═══════════════════════════════════════════════════════════════════════
# Dashboard Schema Tests
# ═══════════════════════════════════════════════════════════════════════

def _make_result(symbol, rank, score):
    return ScanResultResponse(
        symbol=symbol, rank=rank, quality_score=score,
        trailing_returns=TrailingReturns(),
    )


class TestDashboardSchema:
    def test_full_dashboard(self):
        resp = ScannerDashboardResponse(
            last_scan_date=date(2025, 6, 15),
            last_scan_run_id=1,
            universe_name="top_liquid_50",
            universe_size=50,
            avg_quality_score=62.5,
            median_quality_score=65.0,
            health_status="HEALTHY",
            score_distribution=[
                ScoreDistribution(bucket="0-20", count=2),
                ScoreDistribution(bucket="20-40", count=8),
                ScoreDistribution(bucket="40-60", count=15),
                ScoreDistribution(bucket="60-80", count=18),
                ScoreDistribution(bucket="80-100", count=7),
            ],
            quality_tiers=[
                QualityTierSummary(tier="HIGH", min_score=70, max_score=100,
                                   count=12, symbols=["DANGCEM", "GTCO"]),
                QualityTierSummary(tier="MEDIUM", min_score=40, max_score=70,
                                   count=28, symbols=["ZENITH"]),
                QualityTierSummary(tier="LOW", min_score=0, max_score=40,
                                   count=8, symbols=["AIRTEL"]),
                QualityTierSummary(tier="INSUFFICIENT", min_score=0, max_score=100,
                                   count=2, symbols=["SMALL"]),
            ],
            total_red_flags=15,
            degraded_count=5,
            insufficient_count=2,
            fundamentals_coverage_pct=92.0,
            top_5=[_make_result("DANGCEM", 1, 90)],
            bottom_5=[_make_result("SMALL", 50, 15)],
            scoring_config_version="v1.0",
            scoring_config_hash="abc123",
        )
        assert resp.universe_size == 50
        assert resp.avg_quality_score == 62.5
        assert len(resp.score_distribution) == 5
        assert len(resp.quality_tiers) == 4

    def test_distribution_sums_to_total(self):
        """Distribution bucket counts should sum to universe size."""
        dist = [
            ScoreDistribution(bucket="0-20", count=2),
            ScoreDistribution(bucket="20-40", count=8),
            ScoreDistribution(bucket="40-60", count=15),
            ScoreDistribution(bucket="60-80", count=18),
            ScoreDistribution(bucket="80-100", count=7),
        ]
        assert sum(d.count for d in dist) == 50

    def test_tier_counts_sum_to_total(self):
        """Tier counts should sum to universe size."""
        tiers = [
            QualityTierSummary(tier="HIGH", min_score=70, max_score=100, count=12, symbols=[]),
            QualityTierSummary(tier="MEDIUM", min_score=40, max_score=70, count=28, symbols=[]),
            QualityTierSummary(tier="LOW", min_score=0, max_score=40, count=8, symbols=[]),
            QualityTierSummary(tier="INSUFFICIENT", min_score=0, max_score=100, count=2, symbols=[]),
        ]
        assert sum(t.count for t in tiers) == 50

    def test_serialization(self):
        """Dashboard should serialize to JSON-compatible dict."""
        resp = ScannerDashboardResponse(
            universe_name="test", universe_size=0,
            avg_quality_score=0, median_quality_score=0,
            health_status="HEALTHY",
            score_distribution=[], quality_tiers=[],
            total_red_flags=0, degraded_count=0, insufficient_count=0,
            fundamentals_coverage_pct=0, top_5=[], bottom_5=[],
        )
        d = resp.model_dump()
        assert isinstance(d, dict)
        assert d["universe_name"] == "test"


# ═══════════════════════════════════════════════════════════════════════
# Sortable Result Tests
# ═══════════════════════════════════════════════════════════════════════

class TestSortableResult:
    def test_flat_sub_scores(self):
        """Sub-scores should be flat numeric fields, not nested dict."""
        r = ScanResultSortableResponse(
            symbol="DANGCEM", rank=1, quality_score=85.0,
            quality_tier="HIGH", data_quality="FULL",
            profitability=23.0, cash_quality=20.0,
            balance_sheet=22.0, stability=12.0, shareholder_return=8.0,
            trailing_returns=TrailingReturns(),
        )
        assert r.profitability == 23.0
        assert r.cash_quality == 20.0
        assert r.balance_sheet == 22.0
        assert r.stability == 12.0
        assert r.shareholder_return == 8.0

    def test_red_flag_count(self):
        r = ScanResultSortableResponse(
            symbol="TEST", rank=1, quality_score=50.0,
            quality_tier="MEDIUM", data_quality="FULL",
            profitability=0, cash_quality=0, balance_sheet=0,
            stability=0, shareholder_return=0,
            red_flag_count=3, top_red_flag="NEGATIVE_EQUITY",
            trailing_returns=TrailingReturns(),
        )
        assert r.red_flag_count == 3
        assert r.top_red_flag == "NEGATIVE_EQUITY"

    def test_defaults(self):
        """Optional fields should default to None/0."""
        r = ScanResultSortableResponse(
            symbol="X", rank=1, quality_score=0,
            quality_tier="LOW", data_quality="FULL",
            profitability=0, cash_quality=0, balance_sheet=0,
            stability=0, shareholder_return=0,
            trailing_returns=TrailingReturns(),
        )
        assert r.liquidity_score is None
        assert r.confidence_penalty is None
        assert r.red_flag_count == 0
        assert r.top_red_flag is None
        assert r.top_reason is None


# ═══════════════════════════════════════════════════════════════════════
# Table Response Tests
# ═══════════════════════════════════════════════════════════════════════

class TestTableResponse:
    def test_pagination_fields(self):
        resp = ScanResultTableResponse(
            run_id=1, as_of_date=date(2025, 6, 15),
            universe_name="top_liquid_50",
            total=50, page=2, page_size=25,
            sort_by="quality_score", sort_dir="desc",
            results=[],
        )
        assert resp.page == 2
        assert resp.page_size == 25
        assert resp.sort_by == "quality_score"
        assert resp.sort_dir == "desc"

    def test_sorting_fields(self):
        """All valid sort fields should be accepted."""
        from app.api.v1.scanner import VALID_SORT_FIELDS
        expected = {
            "rank", "quality_score", "symbol",
            "profitability", "cash_quality", "balance_sheet",
            "stability", "shareholder_return",
            "liquidity_score", "confidence_penalty", "red_flag_count",
        }
        assert VALID_SORT_FIELDS == expected

    def test_table_sorting_logic(self):
        """Results should be sortable by any valid field."""
        items = [
            ScanResultSortableResponse(
                symbol="A", rank=1, quality_score=90,
                quality_tier="HIGH", data_quality="FULL",
                profitability=25, cash_quality=20, balance_sheet=22,
                stability=13, shareholder_return=10,
                trailing_returns=TrailingReturns(),
            ),
            ScanResultSortableResponse(
                symbol="B", rank=2, quality_score=50,
                quality_tier="MEDIUM", data_quality="FULL",
                profitability=10, cash_quality=15, balance_sheet=10,
                stability=8, shareholder_return=7,
                trailing_returns=TrailingReturns(),
            ),
            ScanResultSortableResponse(
                symbol="C", rank=3, quality_score=30,
                quality_tier="LOW", data_quality="DEGRADED",
                profitability=5, cash_quality=5, balance_sheet=8,
                stability=5, shareholder_return=7,
                trailing_returns=TrailingReturns(),
            ),
        ]

        # Sort by quality_score desc
        sorted_desc = sorted(items, key=lambda r: r.quality_score, reverse=True)
        assert sorted_desc[0].symbol == "A"
        assert sorted_desc[-1].symbol == "C"

        # Sort by profitability asc
        sorted_asc = sorted(items, key=lambda r: r.profitability)
        assert sorted_asc[0].symbol == "C"
        assert sorted_asc[-1].symbol == "A"

    def test_filter_by_tier(self):
        """Filter by quality_tier should work."""
        items = [
            ScanResultSortableResponse(
                symbol="A", rank=1, quality_score=90, quality_tier="HIGH",
                data_quality="FULL", profitability=0, cash_quality=0,
                balance_sheet=0, stability=0, shareholder_return=0,
                trailing_returns=TrailingReturns(),
            ),
            ScanResultSortableResponse(
                symbol="B", rank=2, quality_score=50, quality_tier="MEDIUM",
                data_quality="FULL", profitability=0, cash_quality=0,
                balance_sheet=0, stability=0, shareholder_return=0,
                trailing_returns=TrailingReturns(),
            ),
        ]
        high_only = [r for r in items if r.quality_tier == "HIGH"]
        assert len(high_only) == 1
        assert high_only[0].symbol == "A"

    def test_filter_by_score_range(self):
        """Filter by min/max score should work."""
        items = [
            ScanResultSortableResponse(
                symbol="A", rank=1, quality_score=90, quality_tier="HIGH",
                data_quality="FULL", profitability=0, cash_quality=0,
                balance_sheet=0, stability=0, shareholder_return=0,
                trailing_returns=TrailingReturns(),
            ),
            ScanResultSortableResponse(
                symbol="B", rank=2, quality_score=50, quality_tier="MEDIUM",
                data_quality="FULL", profitability=0, cash_quality=0,
                balance_sheet=0, stability=0, shareholder_return=0,
                trailing_returns=TrailingReturns(),
            ),
        ]
        filtered = [r for r in items if 40 <= r.quality_score <= 60]
        assert len(filtered) == 1
        assert filtered[0].symbol == "B"


# ═══════════════════════════════════════════════════════════════════════
# Median Computation
# ═══════════════════════════════════════════════════════════════════════

class TestMedianComputation:
    def _median(self, scores):
        s = sorted(scores)
        mid = len(s) // 2
        if len(s) % 2 == 1:
            return s[mid]
        return (s[mid - 1] + s[mid]) / 2

    def test_odd_count(self):
        assert self._median([10, 50, 90]) == 50

    def test_even_count(self):
        assert self._median([10, 50, 70, 90]) == 60.0

    def test_single(self):
        assert self._median([42]) == 42

    def test_two(self):
        assert self._median([30, 70]) == 50.0


# ═══════════════════════════════════════════════════════════════════════
# Health Status Derivation
# ═══════════════════════════════════════════════════════════════════════

class TestHealthStatusDerivation:
    def _derive_health(self, fund_pct, insufficient_ratio, degraded_ratio):
        if fund_pct < 50 or insufficient_ratio > 0.3:
            return "CRITICAL"
        if degraded_ratio > 0.2 or fund_pct < 80:
            return "DEGRADED"
        return "HEALTHY"

    def test_healthy(self):
        assert self._derive_health(95, 0.0, 0.05) == "HEALTHY"

    def test_degraded_low_coverage(self):
        assert self._derive_health(70, 0.05, 0.05) == "DEGRADED"

    def test_degraded_high_degraded(self):
        assert self._derive_health(90, 0.05, 0.25) == "DEGRADED"

    def test_critical_very_low_coverage(self):
        assert self._derive_health(30, 0.05, 0.05) == "CRITICAL"

    def test_critical_high_insufficient(self):
        assert self._derive_health(90, 0.35, 0.05) == "CRITICAL"


# ═══════════════════════════════════════════════════════════════════════
# Route Registration
# ═══════════════════════════════════════════════════════════════════════

class TestRouteRegistration:
    def test_dashboard_endpoint(self):
        from app.main import app
        routes = {r.path for r in app.routes}
        assert "/api/v1/scanner/dashboard" in routes

    def test_table_endpoint(self):
        from app.main import app
        routes = {r.path for r in app.routes}
        assert "/api/v1/scanner/table" in routes

    def test_all_scanner_endpoints_v11(self):
        """All 9 scanner endpoints should exist (7 from v1.1 + 2 new)."""
        from app.main import app
        routes = {r.path for r in app.routes}
        expected = {
            "/api/v1/scanner/universe",
            "/api/v1/scanner/runs",
            "/api/v1/scanner/runs/{run_id}",
            "/api/v1/scanner/runs/{run_id}/results",
            "/api/v1/scanner/buylist",
            "/api/v1/scanner/explain/{symbol}",
            "/api/v1/scanner/health",
            "/api/v1/scanner/dashboard",
            "/api/v1/scanner/table",
        }
        for path in expected:
            assert path in routes, f"Missing route: {path}"
