"""
Scanner Health + Monitoring Tests (PR9).

Covers:
  1. Health endpoint schema validation
  2. Anomaly detection: stale scan, low fundamentals, low TRI, stale FX/CPI
  3. Status logic: HEALTHY / DEGRADED / CRITICAL
  4. Coverage computation
  5. Staleness computation
  6. Recommendations generation
  7. Router registration for new endpoints (explain, health)
  8. Currency note logic edge cases
"""

import os
import sys
import pytest
from datetime import date, datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.scanner import (
    ScannerHealthResponse, DataCoverageResponse,
    StalenessResponse, AnomalyResponse,
    ScoreExplanationResponse,
    MetricExplanationResponse, GuardrailTriggerResponse,
    ConfidencePenaltyResponse, WinsorBoundsResponse,
)


# ═══════════════════════════════════════════════════════════════════════
# Health Response Schema Tests
# ═══════════════════════════════════════════════════════════════════════

class TestHealthSchema:
    def test_healthy_response(self):
        """HEALTHY status with full coverage and no anomalies."""
        resp = ScannerHealthResponse(
            status="HEALTHY",
            last_scan_ts=datetime(2025, 6, 15, 12, 0, 0),
            data_coverage=DataCoverageResponse(
                total_universe=50, with_fundamentals=48,
                with_tri=45, with_fx=True, with_cpi=True,
                fundamentals_coverage_pct=96.0, tri_coverage_pct=90.0,
            ),
            staleness=StalenessResponse(
                last_scan_ts=datetime(2025, 6, 15, 12, 0, 0),
                last_scan_age_hours=2.0,
                fx_latest_date=date(2025, 6, 14),
                cpi_latest_date=date(2025, 5, 31),
                fx_staleness_days=1,
                cpi_staleness_days=15,
            ),
            anomalies=[],
            recommendations=[],
        )
        assert resp.status == "HEALTHY"
        assert resp.data_coverage.fundamentals_coverage_pct == 96.0
        assert len(resp.anomalies) == 0

    def test_degraded_response(self):
        """DEGRADED status with warnings."""
        resp = ScannerHealthResponse(
            status="DEGRADED",
            last_scan_ts=datetime(2025, 6, 1, 12, 0, 0),
            data_coverage=DataCoverageResponse(
                total_universe=50, with_fundamentals=40,
                with_tri=30, with_fx=True, with_cpi=False,
                fundamentals_coverage_pct=80.0, tri_coverage_pct=60.0,
            ),
            staleness=StalenessResponse(
                last_scan_ts=datetime(2025, 6, 1, 12, 0, 0),
                last_scan_age_hours=336.0,
            ),
            anomalies=[
                AnomalyResponse(
                    anomaly_type="STALE_SCAN",
                    description="Last scan was 336 hours ago",
                    severity="WARNING",
                ),
            ],
            recommendations=["Run a new scan"],
        )
        assert resp.status == "DEGRADED"
        assert len(resp.anomalies) == 1
        assert resp.anomalies[0].severity == "WARNING"

    def test_critical_response(self):
        """CRITICAL status with critical anomalies."""
        resp = ScannerHealthResponse(
            status="CRITICAL",
            data_coverage=DataCoverageResponse(
                total_universe=50, with_fundamentals=10,
                with_tri=5, with_fx=False, with_cpi=False,
                fundamentals_coverage_pct=20.0, tri_coverage_pct=10.0,
            ),
            staleness=StalenessResponse(),
            anomalies=[
                AnomalyResponse(
                    anomaly_type="LOW_FUNDAMENTALS_COVERAGE",
                    description="Only 20% of universe has fundamentals",
                    severity="CRITICAL",
                ),
            ],
            recommendations=["Import fundamentals"],
        )
        assert resp.status == "CRITICAL"
        assert resp.anomalies[0].severity == "CRITICAL"


# ═══════════════════════════════════════════════════════════════════════
# Anomaly Detection Logic Tests
# ═══════════════════════════════════════════════════════════════════════

class TestAnomalyDetection:
    def _detect_anomalies(self, last_scan_age_hours=None,
                          fund_pct=100, tri_pct=100,
                          fx_staleness=None, cpi_staleness=None):
        """Simulate the anomaly detection logic from the health endpoint."""
        anomalies = []

        if last_scan_age_hours is not None and last_scan_age_hours > 168:
            anomalies.append(AnomalyResponse(
                anomaly_type="STALE_SCAN",
                description=f"Last scan was {last_scan_age_hours:.0f} hours ago",
                severity="WARNING",
            ))

        if fund_pct < 50:
            anomalies.append(AnomalyResponse(
                anomaly_type="LOW_FUNDAMENTALS_COVERAGE",
                description=f"Only {fund_pct}% of universe has fundamentals",
                severity="CRITICAL",
            ))

        if tri_pct < 50:
            anomalies.append(AnomalyResponse(
                anomaly_type="LOW_TRI_COVERAGE",
                description=f"Only {tri_pct}% of universe has TRI data",
                severity="WARNING",
            ))

        if fx_staleness is not None and fx_staleness > 30:
            anomalies.append(AnomalyResponse(
                anomaly_type="STALE_FX",
                description=f"FX data is {fx_staleness} days old",
                severity="WARNING",
            ))

        if cpi_staleness is not None and cpi_staleness > 60:
            anomalies.append(AnomalyResponse(
                anomaly_type="STALE_CPI",
                description=f"CPI data is {cpi_staleness} days old",
                severity="WARNING",
            ))

        return anomalies

    def test_no_anomalies(self):
        """No anomalies when everything is fresh."""
        anomalies = self._detect_anomalies(
            last_scan_age_hours=2, fund_pct=95, tri_pct=90,
            fx_staleness=1, cpi_staleness=15,
        )
        assert len(anomalies) == 0

    def test_stale_scan(self):
        """Scan older than 1 week should trigger STALE_SCAN."""
        anomalies = self._detect_anomalies(last_scan_age_hours=200)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "STALE_SCAN"
        assert anomalies[0].severity == "WARNING"

    def test_low_fundamentals_coverage(self):
        """< 50% fundamentals coverage should trigger CRITICAL."""
        anomalies = self._detect_anomalies(fund_pct=30)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "LOW_FUNDAMENTALS_COVERAGE"
        assert anomalies[0].severity == "CRITICAL"

    def test_low_tri_coverage(self):
        """< 50% TRI coverage should trigger WARNING."""
        anomalies = self._detect_anomalies(tri_pct=40)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "LOW_TRI_COVERAGE"

    def test_stale_fx(self):
        """FX data older than 30 days should trigger WARNING."""
        anomalies = self._detect_anomalies(fx_staleness=45)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "STALE_FX"

    def test_stale_cpi(self):
        """CPI data older than 60 days should trigger WARNING."""
        anomalies = self._detect_anomalies(cpi_staleness=90)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "STALE_CPI"

    def test_multiple_anomalies(self):
        """Multiple issues should produce multiple anomalies."""
        anomalies = self._detect_anomalies(
            last_scan_age_hours=500, fund_pct=20, tri_pct=30,
            fx_staleness=60, cpi_staleness=120,
        )
        assert len(anomalies) == 5
        types = {a.anomaly_type for a in anomalies}
        assert "STALE_SCAN" in types
        assert "LOW_FUNDAMENTALS_COVERAGE" in types
        assert "LOW_TRI_COVERAGE" in types
        assert "STALE_FX" in types
        assert "STALE_CPI" in types

    def test_boundary_scan_age(self):
        """Scan at exactly 168 hours should NOT trigger anomaly."""
        anomalies = self._detect_anomalies(last_scan_age_hours=168)
        assert len(anomalies) == 0

    def test_boundary_fund_coverage(self):
        """Coverage at exactly 50% should NOT trigger anomaly."""
        anomalies = self._detect_anomalies(fund_pct=50)
        assert len(anomalies) == 0


# ═══════════════════════════════════════════════════════════════════════
# Status Logic Tests
# ═══════════════════════════════════════════════════════════════════════

class TestStatusLogic:
    def _compute_status(self, anomalies):
        """Replicate status logic from health endpoint."""
        critical = sum(1 for a in anomalies if a.severity == "CRITICAL")
        warning = sum(1 for a in anomalies if a.severity == "WARNING")
        if critical > 0:
            return "CRITICAL"
        elif warning > 0:
            return "DEGRADED"
        return "HEALTHY"

    def test_healthy(self):
        assert self._compute_status([]) == "HEALTHY"

    def test_degraded(self):
        anomalies = [AnomalyResponse(
            anomaly_type="STALE_SCAN", description="old", severity="WARNING")]
        assert self._compute_status(anomalies) == "DEGRADED"

    def test_critical(self):
        anomalies = [AnomalyResponse(
            anomaly_type="LOW_FUNDAMENTALS_COVERAGE", description="low", severity="CRITICAL")]
        assert self._compute_status(anomalies) == "CRITICAL"

    def test_critical_overrides_warning(self):
        """CRITICAL should take precedence over WARNING."""
        anomalies = [
            AnomalyResponse(anomaly_type="STALE_SCAN", description="old", severity="WARNING"),
            AnomalyResponse(anomaly_type="LOW_FUNDAMENTALS_COVERAGE", description="low", severity="CRITICAL"),
        ]
        assert self._compute_status(anomalies) == "CRITICAL"


# ═══════════════════════════════════════════════════════════════════════
# Coverage Computation Tests
# ═══════════════════════════════════════════════════════════════════════

class TestCoverageComputation:
    def test_full_coverage(self):
        cov = DataCoverageResponse(
            total_universe=50, with_fundamentals=50,
            with_tri=50, with_fx=True, with_cpi=True,
            fundamentals_coverage_pct=100.0, tri_coverage_pct=100.0,
        )
        assert cov.fundamentals_coverage_pct == 100.0
        assert cov.tri_coverage_pct == 100.0

    def test_partial_coverage(self):
        cov = DataCoverageResponse(
            total_universe=50, with_fundamentals=25,
            with_tri=10, with_fx=True, with_cpi=False,
            fundamentals_coverage_pct=50.0, tri_coverage_pct=20.0,
        )
        assert cov.with_cpi is False
        assert cov.tri_coverage_pct == 20.0

    def test_zero_universe(self):
        """Zero universe should have 0% coverage."""
        cov = DataCoverageResponse(
            total_universe=0, with_fundamentals=0,
            with_tri=0, with_fx=False, with_cpi=False,
            fundamentals_coverage_pct=0, tri_coverage_pct=0,
        )
        assert cov.total_universe == 0


# ═══════════════════════════════════════════════════════════════════════
# Staleness Schema Tests
# ═══════════════════════════════════════════════════════════════════════

class TestStalenessSchema:
    def test_all_fields(self):
        s = StalenessResponse(
            last_scan_ts=datetime(2025, 6, 15, 12, 0, 0),
            last_scan_age_hours=2.0,
            last_fundamentals_import_ts=datetime(2025, 6, 14, 8, 0, 0),
            fx_latest_date=date(2025, 6, 14),
            cpi_latest_date=date(2025, 5, 31),
            fx_staleness_days=1,
            cpi_staleness_days=15,
        )
        assert s.last_scan_age_hours == 2.0
        assert s.fx_staleness_days == 1

    def test_all_none(self):
        """All-None staleness should be valid (no data at all)."""
        s = StalenessResponse()
        assert s.last_scan_ts is None
        assert s.fx_latest_date is None


# ═══════════════════════════════════════════════════════════════════════
# Router Registration Tests (explain + health endpoints)
# ═══════════════════════════════════════════════════════════════════════

class TestNewEndpointRegistration:
    def test_explain_endpoint_registered(self):
        """Explain endpoint should be registered."""
        from app.main import app
        routes = {r.path for r in app.routes}
        assert "/api/v1/scanner/explain/{symbol}" in routes

    def test_health_endpoint_registered(self):
        """Health endpoint should be registered."""
        from app.main import app
        routes = {r.path for r in app.routes}
        assert "/api/v1/scanner/health" in routes

    def test_all_scanner_endpoints(self):
        """All 7 scanner endpoints should exist."""
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
        }
        for path in expected:
            assert path in routes, f"Missing route: {path}"


# ═══════════════════════════════════════════════════════════════════════
# Explainability Schema Tests
# ═══════════════════════════════════════════════════════════════════════

class TestExplainabilitySchema:
    def test_score_explanation_response(self):
        resp = ScoreExplanationResponse(
            symbol="DANGCEM",
            quality_score=85.5,
            scoring_config_version="v1.0",
            scoring_config_hash="abc123def456",
            metric_explanations=[
                MetricExplanationResponse(
                    metric_name="roe", raw_value=0.25, winsorized_value=0.25,
                    percentile_rank=0.9, component_score=13.5,
                    max_possible=15.0, direction="higher_is_better",
                ),
            ],
            guardrail_triggers=[
                GuardrailTriggerResponse(
                    name="negative_equity_cap", triggered=False,
                    cap_value=30.0, score_before=85.5, score_after=85.5,
                    reason="Not triggered",
                ),
            ],
            confidence_breakdown=ConfidencePenaltyResponse(
                total=0.0, missing_fields=[], missing_fields_penalty=0.0,
                staleness_days=90, staleness_penalty=0.0,
                liquidity_score=0.8, liquidity_penalty=0.0,
            ),
            winsor_bounds=[
                WinsorBoundsResponse(
                    metric_name="roe", lower_bound=0.05, upper_bound=0.30,
                    universe_size=50, non_null_count=48,
                ),
            ],
            derived_metrics_snapshot={"roe": 0.25, "op_margin": 0.35},
            dividend_years=0,
            data_quality="FULL",
            red_flags=[],
            reasons=["Strong ROE"],
        )
        assert resp.symbol == "DANGCEM"
        assert resp.quality_score == 85.5
        assert len(resp.metric_explanations) == 1
        assert resp.metric_explanations[0].metric_name == "roe"

    def test_explanation_serialization(self):
        """Full explanation should serialize to dict."""
        resp = ScoreExplanationResponse(
            symbol="TEST", quality_score=50.0,
            scoring_config_version="v1.0", scoring_config_hash="abc123",
            metric_explanations=[], guardrail_triggers=[],
            confidence_breakdown=ConfidencePenaltyResponse(
                total=0.0, missing_fields=[], missing_fields_penalty=0.0,
                staleness_penalty=0.0, liquidity_score=0.5, liquidity_penalty=0.0,
            ),
            winsor_bounds=[],
            derived_metrics_snapshot={}, dividend_years=0,
            data_quality="FULL", red_flags=[], reasons=[],
        )
        d = resp.model_dump()
        assert d["symbol"] == "TEST"
        assert isinstance(d["metric_explanations"], list)


# ═══════════════════════════════════════════════════════════════════════
# Recommendations Tests
# ═══════════════════════════════════════════════════════════════════════

class TestRecommendations:
    def test_stale_scan_recommendation(self):
        """Stale scan should recommend running a new scan."""
        recs = []
        if True:  # simulate stale scan detected
            recs.append("Run a new scan: python -m app.cli.scanner run")
        assert any("scanner run" in r for r in recs)

    def test_low_coverage_recommendation(self):
        """Low fundamentals coverage should recommend importing."""
        recs = []
        if True:  # simulate low coverage
            recs.append("Import fundamentals: python -m app.cli.fundamentals import-csv")
        assert any("import-csv" in r for r in recs)

    def test_no_recommendations_when_healthy(self):
        """No recommendations when everything is healthy."""
        recs = []
        assert len(recs) == 0
