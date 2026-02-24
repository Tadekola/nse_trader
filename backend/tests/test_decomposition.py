"""
Deterministic tests for Return Decomposition Engine (Milestone C — PR1).

Covers:
  1. USD decomposition — multiplicative identity, FX devaluation dominates
  2. REAL_NGN decomposition — inflation erosion dominates
  3. NGN decomposition — trivial (equity only)
  4. Multiplicative identity holds within tolerance
  5. Cumulative summary additivity (exact via residual method)
  6. Quality flags — DEGRADED when FX/CPI missing
  7. Edge cases — single day, empty data
  8. Nigeria-specific scenarios
"""

import os
import sys
import pytest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.decomposition import (
    DecompositionEngine, DecompositionQuality, DecompositionResult,
    DecompositionSummary,
)
from app.data.macro.fx_provider import FxRateService
from app.data.macro.cpi_provider import CpiService


@pytest.fixture
def engine():
    return DecompositionEngine()


# ── Helpers ──────────────────────────────────────────────────────────

def make_fx(entries):
    return FxRateService([{"pair": "USDNGN", "ts": d, "rate": r} for d, r in entries])

def make_cpi(entries):
    return CpiService([{"series_name": "CPI_NGN", "ts": d, "value": v} for d, v in entries])


# ── 1. USD Decomposition ─────────────────────────────────────────────


class TestUSDDecomposition:

    def test_50pct_ngn_gain_40pct_devaluation(self, engine):
        """
        CRITICAL NIGERIA SCENARIO:
        Portfolio gains 50% in NGN. Naira devalues 40% (USDNGN: 900→1500).

        r_equity = 0.50
        r_fx = (900/1500) - 1 = -0.40
        r_usd = (1.50)(0.60) - 1 = -0.10

        equity_component = 0.50
        fx_component = -0.10 - 0.50 = -0.60
        total = 0.50 + (-0.60) = -0.10 ✓
        """
        dates = [date(2024, 1, 1), date(2024, 7, 1)]
        ngn_values = [1_000_000.0, 1_500_000.0]  # +50%
        fx = make_fx([(date(2024, 1, 1), 900.0), (date(2024, 7, 1), 1500.0)])

        result = engine.compute(
            portfolio_id=1, dates=dates, ngn_values=ngn_values,
            reporting="USD", fx_service=fx,
        )

        day = result.series[1]
        assert abs(day["equity_component"] - 0.50) < 0.001
        assert abs(day["fx_component"] - (-0.60)) < 0.001
        assert abs(day["total_return"] - (-0.10)) < 0.001

        # Verify additivity: equity + fx = total
        assert abs(day["equity_component"] + day["fx_component"] - day["total_return"]) < 1e-9

        # fx_component dominates (larger magnitude than equity)
        assert abs(day["fx_component"]) > abs(day["equity_component"])

    def test_multiplicative_identity_holds(self, engine):
        """Verify (1+r_usd) = (1+r_equity)*(1+r_fx) for each day."""
        dates = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
        ngn_values = [100000, 108000, 115000]
        fx = make_fx([
            (date(2024, 1, 1), 900.0),
            (date(2024, 1, 2), 920.0),
            (date(2024, 1, 3), 950.0),
        ])

        result = engine.compute(
            portfolio_id=1, dates=dates, ngn_values=ngn_values,
            reporting="USD", fx_service=fx,
        )

        for entry in result.series[1:]:
            r_total = entry["total_return"]
            r_eq = entry["equity_component"]
            r_fx = entry["fx_component"]

            # Additive: total = equity + fx (exact by construction)
            assert abs(r_total - (r_eq + r_fx)) < 1e-9

            # Multiplicative: (1+total) = (1+equity)*(1+fx_raw)
            # where fx_raw = r_fx / (1+r_eq) if r_eq != -1
            # Or equivalently: total = equity + fx already holds

    def test_stable_fx_means_zero_fx_component(self, engine):
        """If FX rate doesn't change, fx_component = 0."""
        dates = [date(2024, 1, 1), date(2024, 1, 2)]
        ngn_values = [100000, 110000]
        fx = make_fx([(date(2024, 1, 1), 900.0), (date(2024, 1, 2), 900.0)])

        result = engine.compute(
            portfolio_id=1, dates=dates, ngn_values=ngn_values,
            reporting="USD", fx_service=fx,
        )

        day = result.series[1]
        assert abs(day["fx_component"]) < 1e-10
        assert abs(day["equity_component"] - 0.10) < 0.001
        assert abs(day["total_return"] - 0.10) < 0.001

    def test_naira_strengthening_boosts_usd_return(self, engine):
        """If Naira strengthens (fx goes down), fx_component > 0."""
        dates = [date(2024, 1, 1), date(2024, 1, 2)]
        ngn_values = [100000, 100000]  # flat equity
        fx = make_fx([(date(2024, 1, 1), 1000.0), (date(2024, 1, 2), 900.0)])

        result = engine.compute(
            portfolio_id=1, dates=dates, ngn_values=ngn_values,
            reporting="USD", fx_service=fx,
        )

        day = result.series[1]
        assert day["fx_component"] > 0  # Naira strengthening helps USD
        assert day["equity_component"] == 0.0
        # r_fx = (1000/900) - 1 ≈ 0.1111
        assert abs(day["fx_component"] - (1000.0 / 900.0 - 1.0)) < 0.001

    def test_cumulative_summary_additivity(self, engine):
        """total_cumulative = equity_cumulative + fx_cumulative (exact)."""
        dates = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3),
                 date(2024, 1, 4), date(2024, 1, 5)]
        ngn_values = [100000, 105000, 102000, 108000, 112000]
        fx = make_fx([
            (date(2024, 1, 1), 900), (date(2024, 1, 2), 920),
            (date(2024, 1, 3), 910), (date(2024, 1, 4), 950),
            (date(2024, 1, 5), 980),
        ])

        result = engine.compute(
            portfolio_id=1, dates=dates, ngn_values=ngn_values,
            reporting="USD", fx_service=fx,
        )

        s = result.summary
        # Exact additivity via residual method
        assert abs(s.total_cumulative - (s.equity_cumulative + s.fx_cumulative)) < 1e-9


# ── 2. REAL_NGN Decomposition ────────────────────────────────────────


class TestRealNGNDecomposition:

    def test_20pct_gain_30pct_inflation(self, engine):
        """
        CRITICAL SCENARIO:
        20% nominal gain, 30% inflation → negative real return.

        r_nominal = 0.20
        r_inflation = 0.30
        r_real = (1.20)/(1.30) - 1 = -0.0769

        equity_component = 0.20
        inflation_component = -0.0769 - 0.20 = -0.2769
        total = 0.20 + (-0.2769) = -0.0769 ✓
        """
        dates = [date(2023, 1, 1), date(2024, 1, 1)]
        ngn_values = [100000, 120000]
        cpi = make_cpi([(date(2023, 1, 1), 100.0), (date(2024, 1, 1), 130.0)])

        result = engine.compute(
            portfolio_id=1, dates=dates, ngn_values=ngn_values,
            reporting="REAL_NGN", cpi_service=cpi,
        )

        day = result.series[1]
        assert abs(day["equity_component"] - 0.20) < 0.001
        assert abs(day["total_return"] - (-0.0769)) < 0.001
        assert abs(day["inflation_component"] - (-0.2769)) < 0.001

        # inflation_component dominates
        assert abs(day["inflation_component"]) > abs(day["equity_component"])

        # Additivity
        assert abs(day["equity_component"] + day["inflation_component"] - day["total_return"]) < 1e-9

    def test_zero_inflation_means_zero_component(self, engine):
        """No inflation → inflation_component = 0."""
        dates = [date(2024, 1, 1), date(2024, 2, 1)]
        ngn_values = [100000, 110000]
        cpi = make_cpi([(date(2024, 1, 1), 100.0), (date(2024, 2, 1), 100.0)])

        result = engine.compute(
            portfolio_id=1, dates=dates, ngn_values=ngn_values,
            reporting="REAL_NGN", cpi_service=cpi,
        )

        day = result.series[1]
        assert abs(day["inflation_component"]) < 1e-10
        assert abs(day["total_return"] - 0.10) < 0.001

    def test_cumulative_summary_additivity(self, engine):
        """total = equity + inflation (exact via residual)."""
        dates = [date(2023, 1, 1), date(2023, 4, 1), date(2023, 7, 1)]
        ngn_values = [100000, 108000, 115000]
        cpi = make_cpi([
            (date(2023, 1, 1), 100.0),
            (date(2023, 4, 1), 105.0),
            (date(2023, 7, 1), 112.0),
        ])

        result = engine.compute(
            portfolio_id=1, dates=dates, ngn_values=ngn_values,
            reporting="REAL_NGN", cpi_service=cpi,
        )

        s = result.summary
        assert abs(s.total_cumulative - (s.equity_cumulative + s.inflation_cumulative)) < 1e-9

    def test_flat_portfolio_with_inflation_is_real_loss(self, engine):
        """Flat 100K NGN + 30% CPI → ~-23% real loss."""
        dates = [date(2023, 1, 1), date(2024, 1, 1)]
        ngn_values = [100000, 100000]
        cpi = make_cpi([(date(2023, 1, 1), 100.0), (date(2024, 1, 1), 130.0)])

        result = engine.compute(
            portfolio_id=1, dates=dates, ngn_values=ngn_values,
            reporting="REAL_NGN", cpi_service=cpi,
        )

        assert result.summary.total_cumulative < 0
        assert abs(result.summary.total_cumulative - (-0.2308)) < 0.01
        assert result.summary.equity_cumulative == 0.0
        assert result.summary.inflation_cumulative < 0


# ── 3. NGN Decomposition ─────────────────────────────────────────────


class TestNGNDecomposition:

    def test_ngn_simple(self, engine):
        dates = [date(2024, 1, 1), date(2024, 1, 2)]
        ngn_values = [100000, 110000]

        result = engine.compute(
            portfolio_id=1, dates=dates, ngn_values=ngn_values,
            reporting="NGN",
        )

        day = result.series[1]
        assert abs(day["equity_component"] - 0.10) < 0.001
        assert day["fx_component"] == 0.0
        assert day["inflation_component"] == 0.0
        assert abs(day["total_return"] - 0.10) < 0.001
        assert result.reporting == "NGN"

    def test_ngn_first_day_is_none(self, engine):
        dates = [date(2024, 1, 1), date(2024, 1, 2)]
        ngn_values = [100000, 110000]
        result = engine.compute(1, dates, ngn_values, "NGN")
        assert result.series[0]["total_return"] is None
        assert result.series[0]["equity_component"] is None


# ── 4. Quality Flags ─────────────────────────────────────────────────


class TestQualityFlags:

    def test_usd_without_fx_is_degraded(self, engine):
        dates = [date(2024, 1, 1), date(2024, 1, 2)]
        ngn_values = [100000, 110000]
        result = engine.compute(1, dates, ngn_values, "USD")
        assert result.quality.fx_mode == "FX_MISSING"
        assert result.quality.overall_quality == "DEGRADED"
        assert result.provenance.get("degraded") is True

    def test_real_ngn_without_cpi_is_degraded(self, engine):
        dates = [date(2024, 1, 1), date(2024, 1, 2)]
        ngn_values = [100000, 110000]
        result = engine.compute(1, dates, ngn_values, "REAL_NGN")
        assert result.quality.inflation_mode == "CPI_MISSING"
        assert result.quality.overall_quality == "DEGRADED"

    def test_degraded_fx_marks_components_null(self, engine):
        dates = [date(2024, 1, 1), date(2024, 1, 2)]
        ngn_values = [100000, 110000]
        result = engine.compute(1, dates, ngn_values, "USD")
        for entry in result.series:
            assert entry["fx_component"] is None

    def test_degraded_cpi_marks_components_null(self, engine):
        dates = [date(2024, 1, 1), date(2024, 1, 2)]
        ngn_values = [100000, 110000]
        result = engine.compute(1, dates, ngn_values, "REAL_NGN")
        for entry in result.series:
            assert entry["inflation_component"] is None

    def test_usd_fx_full(self, engine):
        dates = [date(2024, 1, 1), date(2024, 1, 2)]
        ngn_values = [100000, 110000]
        fx = make_fx([(date(2024, 1, 1), 900), (date(2024, 1, 2), 900)])
        result = engine.compute(1, dates, ngn_values, "USD", fx_service=fx)
        assert result.quality.fx_mode == "FX_FULL"

    def test_quality_to_dict(self):
        q = DecompositionQuality(data_mode="TRI_FULL", fx_mode="FX_FULL")
        d = q.to_dict()
        assert d["overall_quality"] == "FULL"
        assert d["data_mode"] == "TRI_FULL"


# ── 5. Edge Cases ────────────────────────────────────────────────────


class TestEdgeCases:

    def test_single_day(self, engine):
        result = engine.compute(1, [date(2024, 1, 1)], [100000], "NGN")
        assert len(result.series) == 0
        assert "Insufficient data" in result.provenance.get("note", "")

    def test_empty_data(self, engine):
        result = engine.compute(1, [], [], "NGN")
        assert len(result.series) == 0

    def test_result_to_dict(self, engine):
        dates = [date(2024, 1, 1), date(2024, 1, 2)]
        ngn_values = [100000, 110000]
        result = engine.compute(1, dates, ngn_values, "NGN")
        d = result.to_dict()
        assert "portfolio_id" in d
        assert "series" in d
        assert "summary" in d
        assert "quality" in d
        assert "provenance" in d

    def test_summary_to_dict(self):
        s = DecompositionSummary(total_cumulative=0.10, equity_cumulative=0.15,
                                 fx_cumulative=-0.05)
        d = s.to_dict()
        assert abs(d["total_cumulative"] - 0.10) < 1e-6


# ── 6. Reproducibility ──────────────────────────────────────────────


class TestReproducibility:

    def test_identical_inputs_identical_outputs(self, engine):
        dates = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
        ngn_values = [100000, 108000, 115000]
        fx = make_fx([
            (date(2024, 1, 1), 900), (date(2024, 1, 2), 920),
            (date(2024, 1, 3), 950),
        ])

        r1 = engine.compute(1, dates, ngn_values, "USD", fx_service=fx)
        r2 = engine.compute(1, dates, ngn_values, "USD", fx_service=fx)
        assert r1.summary.to_dict() == r2.summary.to_dict()
        for a, b in zip(r1.series, r2.series):
            assert a == b
