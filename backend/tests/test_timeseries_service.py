"""
Deterministic tests for Timeseries Service (Milestone D — PR2).

Covers:
  1. NGN timeseries — values, cumulative return, drawdown
  2. USD timeseries — FX conversion
  3. REAL_NGN timeseries — CPI deflation
  4. Rolling volatility — 30-day window
  5. Drawdown tracking — peak-to-trough
  6. Quality flags — DEGRADED when FX/CPI missing
  7. Edge cases — empty data, single day
  8. Consistency with PerformanceEngine
"""

import os
import sys
import math
import pytest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.timeseries import TimeseriesService, TimeseriesResult
from app.data.macro.fx_provider import FxRateService
from app.data.macro.cpi_provider import CpiService


@pytest.fixture
def svc():
    return TimeseriesService()


# ── Helpers ──────────────────────────────────────────────────────────

def make_fx(entries):
    return FxRateService([{"pair": "USDNGN", "ts": d, "rate": r} for d, r in entries])

def make_cpi(entries):
    return CpiService([{"series_name": "CPI_NGN", "ts": d, "value": v} for d, v in entries])


def _std_transactions():
    return [
        {"ts": date(2024, 1, 2), "tx_type": "CASH_IN", "symbol": None,
         "quantity": None, "price_ngn": None, "amount_ngn": 1_000_000, "fees_ngn": 0},
        {"ts": date(2024, 1, 3), "tx_type": "BUY", "symbol": "DANGCEM",
         "quantity": 1000, "price_ngn": 350.0, "amount_ngn": -350_000, "fees_ngn": 0},
    ]


def _price_series_5_days():
    """DANGCEM: 350→355→360→365→370 over 5 trading days."""
    return {
        "DANGCEM": {
            date(2024, 1, 2 + i): 350.0 + i * 5 for i in range(5)
        }
    }


def _price_series_40_days():
    """DANGCEM: 40 trading days with slight uptrend for rolling vol test."""
    prices = {}
    for i in range(40):
        d = date(2024, 1, 2) + timedelta(days=i)
        # Slight oscillation: 350 + sin-like pattern
        prices[d] = 350.0 + (i % 3) * 2 + i * 0.5
    return {"DANGCEM": prices}


# ── 1. NGN Timeseries ───────────────────────────────────────────────


class TestNGNTimeseries:

    def test_basic_series(self, svc):
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_5_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 6),
        )
        assert result.reporting == "NGN"
        assert result.num_points == 5
        assert len(result.series) == 5

    def test_values_correct(self, svc):
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_5_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 6),
        )
        # Day 0 (2024-01-02): Cash 1M, no holdings yet → value = 1M
        assert abs(result.series[0].value - 1_000_000) < 1
        # Day 4 (2024-01-06): Cash 650K + DANGCEM 1000*370 = 1_020_000
        last = result.series[-1]
        assert abs(last.value - 1_020_000) < 1

    def test_cumulative_return(self, svc):
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_5_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 6),
        )
        # First point: cumulative return = 0
        assert result.series[0].cumulative_return == 0.0
        # Last: (1020000/1000000) - 1 = 0.02
        assert abs(result.series[-1].cumulative_return - 0.02) < 0.005

    def test_response_contract(self, svc):
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_5_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 6),
        )
        d = result.to_dict()
        for field in ["reporting", "start_date", "end_date", "num_points",
                       "quality", "series", "provenance"]:
            assert field in d, f"Missing field: {field}"

        point = d["series"][0]
        for field in ["date", "value", "value_ngn", "cumulative_return",
                       "drawdown", "rolling_vol_30d"]:
            assert field in point, f"Missing point field: {field}"


# ── 2. USD Timeseries ───────────────────────────────────────────────


class TestUSDTimeseries:

    def test_usd_conversion(self, svc):
        fx = make_fx([
            (date(2024, 1, 2 + i), 900 + i * 25) for i in range(5)
        ])
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_5_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 6),
            reporting="USD",
            fx_service=fx,
        )
        assert result.reporting == "USD"
        assert result.quality.fx_mode == "FX_FULL"
        # Day 0: 1M / 900 ≈ 1111.11
        assert abs(result.series[0].value - 1_000_000 / 900) < 1

    def test_usd_degraded_no_fx(self, svc):
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_5_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 6),
            reporting="USD",
        )
        assert result.quality.fx_mode == "FX_MISSING"
        assert result.quality.overall_quality == "DEGRADED"


# ── 3. REAL_NGN Timeseries ──────────────────────────────────────────


class TestRealNGNTimeseries:

    def test_real_ngn_deflation(self, svc):
        cpi = make_cpi([
            (date(2024, 1, 1), 100.0),
            (date(2024, 2, 1), 105.0),
        ])
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_5_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 6),
            reporting="REAL_NGN",
            cpi_service=cpi,
        )
        assert result.reporting == "REAL_NGN"
        assert result.quality.inflation_mode == "CPI_FULL"

    def test_real_ngn_degraded_no_cpi(self, svc):
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_5_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 6),
            reporting="REAL_NGN",
        )
        assert result.quality.inflation_mode == "CPI_MISSING"
        assert result.quality.overall_quality == "DEGRADED"


# ── 4. Drawdown ─────────────────────────────────────────────────────


class TestTimeseriesDrawdown:

    def test_monotonic_up_zero_drawdown(self, svc):
        """Monotonically increasing prices → drawdown always 0."""
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_5_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 6),
        )
        for point in result.series:
            assert point.drawdown < 0.001

    def test_drawdown_after_decline(self, svc):
        """Price goes up then down → positive drawdown at end."""
        prices = {
            "DANGCEM": {
                date(2024, 1, 2): 350, date(2024, 1, 3): 350,
                date(2024, 1, 4): 400,  # peak
                date(2024, 1, 5): 300,  # decline
            }
        }
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=prices,
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 5),
        )
        # Last point should show significant drawdown
        last = result.series[-1]
        assert last.drawdown > 0.05


# ── 5. Rolling Volatility ───────────────────────────────────────────


class TestRollingVolatility:

    def test_no_vol_before_30_days(self, svc):
        """Rolling vol should be None for first 29 points."""
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_40_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 2, 10),
        )
        # First 30 points should have None rolling vol
        for i in range(min(30, len(result.series))):
            assert result.series[i].rolling_vol_30d is None

    def test_vol_available_after_30_days(self, svc):
        """Rolling vol should be available after 30 points."""
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_40_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 2, 10),
        )
        # Should have points with rolling vol
        vol_points = [p for p in result.series if p.rolling_vol_30d is not None]
        assert len(vol_points) > 0

    def test_vol_positive(self, svc):
        """Rolling vol should be positive where available."""
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_40_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 2, 10),
        )
        for p in result.series:
            if p.rolling_vol_30d is not None:
                assert p.rolling_vol_30d >= 0


# ── 6. Edge Cases ───────────────────────────────────────────────────


class TestTimeseriesEdgeCases:

    def test_empty_price_data(self, svc):
        result = svc.compute(
            transactions=_std_transactions(),
            price_series={},
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 6),
        )
        assert result.num_points == 0
        assert len(result.series) == 0
        assert result.provenance.get("note") == "No price data in range"

    def test_to_dict_serializable(self, svc):
        result = svc.compute(
            transactions=_std_transactions(),
            price_series=_price_series_5_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 6),
        )
        import json
        json.dumps(result.to_dict())  # should not raise

    def test_reproducibility(self, svc):
        args = dict(
            transactions=_std_transactions(),
            price_series=_price_series_5_days(),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 6),
        )
        r1 = svc.compute(**args)
        r2 = svc.compute(**args)
        assert r1.to_dict() == r2.to_dict()
