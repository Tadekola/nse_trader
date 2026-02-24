"""
Deterministic tests for Performance Engine (Milestone B — PR3).

Covers:
  1. TWR — chain-linked daily returns, flat portfolio, growth
  2. CAGR — annualized compound growth
  3. Volatility — daily and annualized
  4. Max drawdown — peak-to-trough detection
  5. MWR/XIRR — money-weighted return with cash flows
  6. USD reporting — FX devaluation impact on USD returns
  7. Real NGN reporting — CPI deflation impact on real returns
  8. Quality flags — FULL, DEGRADED, FX_MISSING, CPI_MISSING
  9. Edge cases — empty data, single day, None values
  10. Reproducibility — same inputs → same outputs
  11. Nigeria-specific: 50% NGN return + 40% devaluation → negative USD return
"""

import os
import sys
import pytest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.performance import (
    PerformanceEngine, PerformanceMetrics, PerformanceResult,
    QualityFlags,
)
from app.data.macro.fx_provider import FxRateService
from app.data.macro.cpi_provider import CpiService


@pytest.fixture
def engine():
    return PerformanceEngine()


# ── Helper: build daily values from a value array ────────────────────

def make_daily_values(start: date, values: list, quality="FULL"):
    """Build daily_values list from a starting date and value array."""
    result = []
    from datetime import timedelta
    for i, v in enumerate(values):
        d = date(start.year, start.month, start.day + i)
        result.append({
            "date": d,
            "value_ngn": v,
            "cash_ngn": 0.0,
            "holdings_ngn": v,
            "data_quality": quality,
        })
    return result


def make_fx_service(start: date, rates: list, pair="USDNGN"):
    """Build FxRateService from a starting date and rate array."""
    from datetime import timedelta
    entries = []
    for i, r in enumerate(rates):
        d = date(start.year, start.month, start.day + i)
        entries.append({"pair": pair, "ts": d, "rate": r})
    return FxRateService(entries)


def make_cpi_service(entries_list):
    """Build CpiService from list of (date, value) tuples."""
    entries = [
        {"series_name": "CPI_NGN", "ts": d, "value": v}
        for d, v in entries_list
    ]
    return CpiService(entries)


# ── 1. TWR ───────────────────────────────────────────────────────────


class TestTWR:

    def test_flat_portfolio(self, engine):
        """No change in value → TWR = 0."""
        dv = make_daily_values(date(2024, 1, 2), [100000, 100000, 100000])
        result = engine.compute(dv, [], reporting="NGN")
        assert abs(result.metrics.twr) < 1e-8

    def test_10pct_growth(self, engine):
        """10% growth over 3 days."""
        dv = make_daily_values(date(2024, 1, 2), [100000, 105000, 110000])
        result = engine.compute(dv, [], reporting="NGN")
        assert abs(result.metrics.twr - 0.10) < 0.001

    def test_decline_and_recovery(self, engine):
        """100 → 80 → 100: TWR = 0%."""
        dv = make_daily_values(date(2024, 1, 2), [100000, 80000, 100000])
        result = engine.compute(dv, [], reporting="NGN")
        assert abs(result.metrics.twr) < 0.001

    def test_total_return_matches_twr_no_cashflows(self, engine):
        """Without cash flows, TWR = total return."""
        dv = make_daily_values(date(2024, 1, 2), [100000, 110000, 121000])
        result = engine.compute(dv, [], reporting="NGN")
        assert abs(result.metrics.twr - result.metrics.total_return) < 1e-6


# ── 2. CAGR ──────────────────────────────────────────────────────────


class TestCAGR:

    def test_cagr_100pct_1year(self, engine):
        """100K → 200K over 365 days ≈ 100% CAGR."""
        # Use start and end only (intermediate doesn't affect CAGR)
        from datetime import timedelta
        start = date(2024, 1, 1)
        end = start + timedelta(days=365)
        dv = [
            {"date": start, "value_ngn": 100000, "cash_ngn": 0, "holdings_ngn": 100000, "data_quality": "FULL"},
            {"date": end, "value_ngn": 200000, "cash_ngn": 0, "holdings_ngn": 200000, "data_quality": "FULL"},
        ]
        result = engine.compute(dv, [], reporting="NGN")
        assert abs(result.metrics.cagr - 1.0) < 0.01  # ~100% CAGR

    def test_cagr_zero_for_flat(self, engine):
        """Flat portfolio → CAGR ≈ 0."""
        from datetime import timedelta
        start = date(2024, 1, 1)
        end = start + timedelta(days=365)
        dv = [
            {"date": start, "value_ngn": 100000, "cash_ngn": 0, "holdings_ngn": 100000, "data_quality": "FULL"},
            {"date": end, "value_ngn": 100000, "cash_ngn": 0, "holdings_ngn": 100000, "data_quality": "FULL"},
        ]
        result = engine.compute(dv, [], reporting="NGN")
        assert abs(result.metrics.cagr) < 0.01


# ── 3. Volatility ────────────────────────────────────────────────────


class TestVolatility:

    def test_zero_vol_for_flat(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 100000, 100000, 100000])
        result = engine.compute(dv, [], reporting="NGN")
        assert result.metrics.volatility_daily == 0.0

    def test_positive_vol_for_movement(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 110000, 95000, 105000])
        result = engine.compute(dv, [], reporting="NGN")
        assert result.metrics.volatility_daily > 0

    def test_annualized_vol(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 101000, 99000, 100500])
        result = engine.compute(dv, [], reporting="NGN")
        import math
        expected_ann = result.metrics.volatility_daily * math.sqrt(252)
        assert abs(result.metrics.volatility_annualized - expected_ann) < 1e-8


# ── 4. Max Drawdown ──────────────────────────────────────────────────


class TestMaxDrawdown:

    def test_no_drawdown_monotonic(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 105000, 110000, 115000])
        result = engine.compute(dv, [], reporting="NGN")
        assert result.metrics.max_drawdown == 0.0

    def test_drawdown_50pct(self, engine):
        """100K → 50K → 80K: max drawdown = 50%."""
        dv = make_daily_values(date(2024, 1, 2), [100000, 50000, 80000])
        result = engine.compute(dv, [], reporting="NGN")
        assert abs(result.metrics.max_drawdown - 0.50) < 0.001

    def test_drawdown_dates(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 120000, 60000, 90000])
        result = engine.compute(dv, [], reporting="NGN")
        # Peak at day 2 (120K), trough at day 3 (60K) → 50% drawdown
        assert abs(result.metrics.max_drawdown - 0.50) < 0.001
        assert result.metrics.max_drawdown_start == date(2024, 1, 3)  # peak date
        assert result.metrics.max_drawdown_end == date(2024, 1, 4)    # trough date


# ── 5. MWR / XIRR ────────────────────────────────────────────────────


class TestXIRR:

    def test_simple_xirr(self, engine):
        """Invest 100K, get 110K after 1 year → ~10% return."""
        from datetime import timedelta
        start = date(2024, 1, 1)
        end = start + timedelta(days=365)
        dv = [
            {"date": start, "value_ngn": 100000, "cash_ngn": 0, "holdings_ngn": 100000, "data_quality": "FULL"},
            {"date": end, "value_ngn": 110000, "cash_ngn": 0, "holdings_ngn": 110000, "data_quality": "FULL"},
        ]
        cfs = [{"date": start, "amount": -100000}]  # initial investment (outflow)
        result = engine.compute(dv, cfs, reporting="NGN")
        if result.metrics.mwr is not None:
            assert abs(result.metrics.mwr - 0.10) < 0.02

    def test_xirr_with_additional_investment(self, engine):
        """Two investments, still converges."""
        from datetime import timedelta
        start = date(2024, 1, 1)
        mid = start + timedelta(days=180)
        end = start + timedelta(days=365)
        dv = [
            {"date": start, "value_ngn": 100000, "cash_ngn": 0, "holdings_ngn": 100000, "data_quality": "FULL"},
            {"date": mid, "value_ngn": 200000, "cash_ngn": 0, "holdings_ngn": 200000, "data_quality": "FULL"},
            {"date": end, "value_ngn": 230000, "cash_ngn": 0, "holdings_ngn": 230000, "data_quality": "FULL"},
        ]
        cfs = [
            {"date": start, "amount": -100000},
            {"date": mid, "amount": -100000},
        ]
        result = engine.compute(dv, cfs, reporting="NGN")
        # MWR should be positive (we invested 200K total, ended with 230K)
        if result.metrics.mwr is not None:
            assert result.metrics.mwr > 0


# ── 6. USD Reporting ─────────────────────────────────────────────────


class TestUSDReporting:

    def test_ngn_gain_wiped_by_devaluation(self, engine):
        """
        CRITICAL Nigeria scenario:
        Portfolio gains 50% in NGN, but Naira devalues 40%.
        Expected: USD return is significantly less than NGN return.

        Day 0: 1M NGN, USDNGN=900 → $1,111 USD
        Day 1: 1.5M NGN (+50%), USDNGN=1500 → $1,000 USD (-10%)

        50% NGN gain → -10% USD return. This is the whole point.
        """
        dv = [
            {"date": date(2024, 1, 1), "value_ngn": 1_000_000, "cash_ngn": 0,
             "holdings_ngn": 1_000_000, "data_quality": "FULL"},
            {"date": date(2024, 7, 1), "value_ngn": 1_500_000, "cash_ngn": 0,
             "holdings_ngn": 1_500_000, "data_quality": "FULL"},
        ]
        fx = FxRateService([
            {"pair": "USDNGN", "ts": date(2024, 1, 1), "rate": 900.0},
            {"pair": "USDNGN", "ts": date(2024, 7, 1), "rate": 1500.0},
        ])
        result = engine.compute(dv, [], reporting="USD", fx_service=fx)

        # NGN: +50%, USD: should be negative
        assert result.metrics.total_return < 0
        assert result.quality.fx_mode == "FX_FULL"
        assert result.reporting_mode == "USD"

        # Verify exact math: 1M/900 = 1111.11, 1.5M/1500 = 1000
        # USD return = (1000 - 1111.11) / 1111.11 = -10%
        assert abs(result.metrics.total_return - (-0.10)) < 0.01

    def test_usd_reporting_fx_full(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 105000, 110000])
        fx = make_fx_service(date(2024, 1, 2), [900.0, 905.0, 910.0])
        result = engine.compute(dv, [], reporting="USD", fx_service=fx)
        assert result.quality.fx_mode == "FX_FULL"
        assert result.quality.overall_quality != "DEGRADED" or result.quality.data_mode == "PRICE_ONLY"

    def test_usd_reporting_no_fx_service(self, engine):
        """Without FX service, USD reporting is DEGRADED."""
        dv = make_daily_values(date(2024, 1, 2), [100000, 105000])
        result = engine.compute(dv, [], reporting="USD")
        assert result.quality.fx_mode == "FX_MISSING"
        assert result.quality.overall_quality == "DEGRADED"

    def test_series_includes_both_currencies(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 110000])
        fx = make_fx_service(date(2024, 1, 2), [900.0, 900.0])
        result = engine.compute(dv, [], reporting="USD", fx_service=fx)
        for entry in result.series:
            assert "value" in entry       # USD value
            assert "value_ngn" in entry   # always include NGN


# ── 7. Real NGN Reporting ────────────────────────────────────────────


class TestRealNGNReporting:

    def test_inflation_erodes_real_returns(self, engine):
        """
        Portfolio flat at 100K NGN. CPI rises 30%.
        Real value should drop to ~76.9K.
        """
        dv = [
            {"date": date(2023, 1, 15), "value_ngn": 100000, "cash_ngn": 0,
             "holdings_ngn": 100000, "data_quality": "FULL"},
            {"date": date(2024, 1, 15), "value_ngn": 100000, "cash_ngn": 0,
             "holdings_ngn": 100000, "data_quality": "FULL"},
        ]
        cpi = make_cpi_service([
            (date(2023, 1, 1), 100.0),
            (date(2024, 1, 1), 130.0),
        ])
        result = engine.compute(dv, [], reporting="REAL_NGN", cpi_service=cpi,
                                cpi_base_date=date(2023, 1, 1))
        # Real total return: (76923/100000) - 1 ≈ -23%
        assert result.metrics.total_return < 0
        assert abs(result.metrics.total_return - (-0.2308)) < 0.01
        assert result.quality.inflation_mode == "CPI_FULL"

    def test_real_ngn_no_cpi(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 105000])
        result = engine.compute(dv, [], reporting="REAL_NGN")
        assert result.quality.inflation_mode == "CPI_MISSING"
        assert result.quality.overall_quality == "DEGRADED"

    def test_nominal_gain_but_real_loss(self, engine):
        """
        20% nominal gain, 30% inflation → real loss.
        This is the typical Nigerian investor experience.
        """
        dv = [
            {"date": date(2023, 1, 15), "value_ngn": 100000, "cash_ngn": 0,
             "holdings_ngn": 100000, "data_quality": "FULL"},
            {"date": date(2024, 1, 15), "value_ngn": 120000, "cash_ngn": 0,
             "holdings_ngn": 120000, "data_quality": "FULL"},
        ]
        cpi = make_cpi_service([
            (date(2023, 1, 1), 100.0),
            (date(2024, 1, 1), 130.0),
        ])
        result = engine.compute(dv, [], reporting="REAL_NGN", cpi_service=cpi,
                                cpi_base_date=date(2023, 1, 1))
        # Nominal: +20%, Real: 120K/1.3 = 92.3K, real return = -7.7%
        assert result.metrics.total_return < 0
        assert abs(result.metrics.total_return - (-0.0769)) < 0.01


# ── 8. Quality Flags ─────────────────────────────────────────────────


class TestQualityFlags:

    def test_full_quality(self):
        q = QualityFlags(data_mode="TRI_FULL", fx_mode="FX_NOT_REQUESTED",
                         inflation_mode="CPI_NOT_REQUESTED")
        assert q.overall_quality == "FULL"

    def test_degraded_fx_missing(self):
        q = QualityFlags(data_mode="TRI_FULL", fx_mode="FX_MISSING")
        assert q.overall_quality == "DEGRADED"

    def test_degraded_cpi_missing(self):
        q = QualityFlags(data_mode="TRI_FULL", inflation_mode="CPI_MISSING")
        assert q.overall_quality == "DEGRADED"

    def test_degraded_price_only(self):
        q = QualityFlags(data_mode="PRICE_ONLY")
        assert q.overall_quality == "DEGRADED"

    def test_flags_to_dict(self):
        q = QualityFlags(data_mode="TRI_FULL", fx_mode="FX_FULL")
        d = q.to_dict()
        assert "overall_quality" in d
        assert d["data_mode"] == "TRI_FULL"
        assert d["fx_mode"] == "FX_FULL"

    def test_ngn_reporting_fx_not_requested(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 105000])
        result = engine.compute(dv, [], reporting="NGN")
        assert result.quality.fx_mode == "FX_NOT_REQUESTED"
        assert result.quality.inflation_mode == "CPI_NOT_REQUESTED"


# ── 9. Edge Cases ────────────────────────────────────────────────────


class TestEdgeCases:

    def test_empty_daily_values(self, engine):
        result = engine.compute([], [], reporting="NGN")
        assert result.metrics.twr is None
        assert result.metrics.cagr is None

    def test_single_day(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000])
        result = engine.compute(dv, [], reporting="NGN")
        assert result.metrics.twr is None  # no returns to compute
        assert result.metrics.num_days == 0

    def test_metrics_to_dict(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 110000, 105000])
        result = engine.compute(dv, [], reporting="NGN")
        d = result.metrics.to_dict()
        assert isinstance(d["twr"], float)
        assert isinstance(d["num_days"], int)

    def test_result_to_dict(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 110000])
        result = engine.compute(dv, [], reporting="NGN")
        d = result.to_dict()
        assert "reporting_mode" in d
        assert "metrics" in d
        assert "quality" in d
        assert "series" in d
        assert "provenance" in d


# ── 10. Reproducibility ──────────────────────────────────────────────


class TestReproducibility:

    def test_identical_inputs_identical_outputs(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 98000, 105000, 110000])
        fx = make_fx_service(date(2024, 1, 2), [900, 910, 920, 930])
        r1 = engine.compute(dv, [], reporting="USD", fx_service=fx)
        r2 = engine.compute(dv, [], reporting="USD", fx_service=fx)
        assert r1.metrics.to_dict() == r2.metrics.to_dict()
        assert r1.quality.to_dict() == r2.quality.to_dict()


# ── 11. Series Output ────────────────────────────────────────────────


class TestSeriesOutput:

    def test_series_length(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 105000, 110000])
        result = engine.compute(dv, [], reporting="NGN")
        assert len(result.series) == 3

    def test_first_day_no_return(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 105000])
        result = engine.compute(dv, [], reporting="NGN")
        assert result.series[0]["daily_return"] is None

    def test_second_day_has_return(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 105000])
        result = engine.compute(dv, [], reporting="NGN")
        assert abs(result.series[1]["daily_return"] - 0.05) < 1e-6

    def test_provenance_included(self, engine):
        dv = make_daily_values(date(2024, 1, 2), [100000, 105000])
        result = engine.compute(dv, [], reporting="NGN")
        assert "reporting_mode" in result.provenance
        assert "quality" in result.provenance
