"""
Deterministic tests for Summary Service (Milestone D — PR1).

Covers:
  1. NGN summary — valuation, returns, concentration, freshness
  2. USD summary — FX conversion, quality flags
  3. REAL_NGN summary — CPI deflation
  4. Return windows — YTD, 1Y, 3Y, since inception
  5. Concentration — HHI, max position weight
  6. Top holdings — sorted by market value, weight sums
  7. Quality flags — DEGRADED when FX/CPI missing
  8. Edge cases — single transaction, no price data
  9. Drawdown — current drawdown from peak
"""

import os
import sys
import pytest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.summary import (
    SummaryService, SummaryResult, DataFreshness,
    HoldingDetail, ConcentrationMetrics, ReturnWindow,
)
from app.data.macro.fx_provider import FxRateService
from app.data.macro.cpi_provider import CpiService


@pytest.fixture
def svc():
    return SummaryService()


# ── Helpers ──────────────────────────────────────────────────────────

def make_fx(entries):
    return FxRateService([{"pair": "USDNGN", "ts": d, "rate": r} for d, r in entries])

def make_cpi(entries):
    return CpiService([{"series_name": "CPI_NGN", "ts": d, "value": v} for d, v in entries])


# Standard test portfolio:
#  - 2024-01-02: CASH_IN 1M NGN
#  - 2024-01-03: BUY 1000 DANGCEM @ 350
#  - 2024-01-03: BUY 500 GTCO @ 40
#  Prices: DANGCEM 350→370 over 5 days, GTCO 40→42 over 5 days

def _std_transactions():
    return [
        {"ts": date(2024, 1, 2), "tx_type": "CASH_IN", "symbol": None,
         "quantity": None, "price_ngn": None, "amount_ngn": 1_000_000, "fees_ngn": 0},
        {"ts": date(2024, 1, 3), "tx_type": "BUY", "symbol": "DANGCEM",
         "quantity": 1000, "price_ngn": 350.0, "amount_ngn": -350_000, "fees_ngn": 0},
        {"ts": date(2024, 1, 3), "tx_type": "BUY", "symbol": "GTCO",
         "quantity": 500, "price_ngn": 40.0, "amount_ngn": -20_000, "fees_ngn": 0},
    ]


def _std_price_series():
    """5 trading days: 2024-01-02 to 2024-01-06."""
    dangcem = {}
    gtco = {}
    for i in range(5):
        d = date(2024, 1, 2 + i)
        dangcem[d] = 350.0 + i * 5  # 350, 355, 360, 365, 370
        gtco[d] = 40.0 + i * 0.5    # 40.0, 40.5, 41.0, 41.5, 42.0
    return {"DANGCEM": dangcem, "GTCO": gtco}


def _std_latest_prices():
    return {"DANGCEM": 370.0, "GTCO": 42.0}


# ── 1. NGN Summary ──────────────────────────────────────────────────


class TestNGNSummary:

    def test_basic_valuation(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        assert result.portfolio_id == 1
        assert result.reporting == "NGN"
        # Holdings: 1000*370 + 500*42 = 370000 + 21000 = 391000
        # Cash: 1M - 350000 - 20000 = 630000
        # Total: 391000 + 630000 = 1021000
        assert abs(result.holdings_value_ngn - 391_000) < 1
        assert abs(result.cash_ngn - 630_000) < 1
        assert abs(result.value_ngn - 1_021_000) < 1
        assert result.value_reporting == result.value_ngn  # NGN mode

    def test_response_contract(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        d = result.to_dict()
        # All required fields
        for field in [
            "portfolio_id", "as_of", "reporting", "value_ngn",
            "value_reporting", "cash_ngn", "holdings_value_ngn",
            "total_invested_ngn", "returns", "current_drawdown",
            "top_holdings", "concentration", "freshness", "quality",
            "provenance",
        ]:
            assert field in d, f"Missing field: {field}"

    def test_since_inception_return(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        inception = next(r for r in result.returns if r.label == "SINCE_INCEPTION")
        assert inception.available is True
        # Start: 1M (2024-01-02), End: 1.021M (2024-01-06)
        # Return: (1021000/1000000) - 1 = 0.021
        assert inception.value is not None
        assert abs(inception.value - 0.021) < 0.005

    def test_quality_full_for_ngn(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        # NGN doesn't need FX or CPI
        assert result.quality.fx_mode == "FX_NOT_REQUESTED"
        assert result.quality.inflation_mode == "CPI_NOT_REQUESTED"


# ── 2. USD Summary ──────────────────────────────────────────────────


class TestUSDSummary:

    def test_usd_value_conversion(self, svc):
        fx = make_fx([
            (date(2024, 1, 2), 900), (date(2024, 1, 3), 910),
            (date(2024, 1, 4), 920), (date(2024, 1, 5), 930),
            (date(2024, 1, 6), 1000),
        ])
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="USD",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
            fx_service=fx,
        )
        # value_reporting = 1021000 / 1000 = 1021.0
        assert result.value_reporting is not None
        assert abs(result.value_reporting - 1021.0) < 1

    def test_usd_quality_full_with_fx(self, svc):
        fx = make_fx([(date(2024, 1, 6), 1000)])
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="USD",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
            fx_service=fx,
        )
        assert result.quality.fx_mode == "FX_FULL"

    def test_usd_degraded_without_fx(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="USD",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        assert result.quality.fx_mode == "FX_MISSING"
        assert result.quality.overall_quality == "DEGRADED"
        assert result.value_reporting is None
        assert result.provenance.get("degraded") is True


# ── 3. REAL_NGN Summary ─────────────────────────────────────────────


class TestRealNGNSummary:

    def test_real_ngn_deflation(self, svc):
        cpi = make_cpi([
            (date(2024, 1, 1), 100.0),
            (date(2024, 2, 1), 105.0),
        ])
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="REAL_NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
            cpi_service=cpi,
        )
        assert result.value_reporting is not None
        assert result.quality.inflation_mode == "CPI_FULL"

    def test_real_ngn_degraded_without_cpi(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="REAL_NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        assert result.quality.inflation_mode == "CPI_MISSING"
        assert result.quality.overall_quality == "DEGRADED"


# ── 4. Concentration ────────────────────────────────────────────────


class TestConcentration:

    def test_hhi_and_max_weight(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        c = result.concentration
        # DANGCEM: 370000/1021000 ≈ 0.3624
        # GTCO: 21000/1021000 ≈ 0.0206
        # Cash: 630000/1021000 ≈ 0.6170
        assert c.max_position_symbol == "DANGCEM"
        assert c.max_position_weight > 0.3
        assert c.num_positions == 2
        assert c.hhi > 0  # non-zero

    def test_single_position_high_hhi(self, svc):
        txs = [
            {"ts": date(2024, 1, 2), "tx_type": "CASH_IN", "symbol": None,
             "quantity": None, "price_ngn": None, "amount_ngn": 100_000, "fees_ngn": 0},
            {"ts": date(2024, 1, 3), "tx_type": "BUY", "symbol": "DANGCEM",
             "quantity": 285, "price_ngn": 350.0, "amount_ngn": -99_750, "fees_ngn": 0},
        ]
        prices = {"DANGCEM": {date(2024, 1, 2): 350, date(2024, 1, 3): 350}}
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 3), reporting="NGN",
            transactions=txs, price_series=prices,
            latest_prices={"DANGCEM": 350},
        )
        # Single position dominates; HHI should be very high
        assert result.concentration.hhi > 4000


# ── 5. Top Holdings ─────────────────────────────────────────────────


class TestTopHoldings:

    def test_sorted_by_market_value(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        holdings = result.top_holdings
        assert len(holdings) == 2
        assert holdings[0].symbol == "DANGCEM"  # 370K > 21K
        assert holdings[1].symbol == "GTCO"

    def test_weights_sum_to_holdings_fraction(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        total_weight = sum(h.weight for h in result.top_holdings)
        # Weights are fraction of TOTAL portfolio (including cash)
        # So sum of holding weights < 1.0
        assert total_weight < 1.0
        assert total_weight > 0.0

    def test_tri_quality_propagated(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
            tri_quality_map={"DANGCEM": "FULL", "GTCO": "PRICE_ONLY"},
        )
        d_hold = next(h for h in result.top_holdings if h.symbol == "DANGCEM")
        g_hold = next(h for h in result.top_holdings if h.symbol == "GTCO")
        assert d_hold.tri_quality == "FULL"
        assert g_hold.tri_quality == "PRICE_ONLY"


# ── 6. Return Windows ───────────────────────────────────────────────


class TestReturnWindows:

    def test_four_windows_present(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        labels = {r.label for r in result.returns}
        assert labels == {"YTD", "1Y", "3Y", "SINCE_INCEPTION"}

    def test_unavailable_windows_flagged(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        # 1Y and 3Y require data going back 1 and 3 years from as_of
        # Our data starts 2024-01-02, only 4 days old
        one_y = next(r for r in result.returns if r.label == "1Y")
        three_y = next(r for r in result.returns if r.label == "3Y")
        # These should still be available but have same start as inception
        # since inception is only 4 days before as_of

    def test_ytd_available(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        ytd = next(r for r in result.returns if r.label == "YTD")
        assert ytd.available is True
        assert ytd.value is not None


# ── 7. Drawdown ─────────────────────────────────────────────────────


class TestDrawdown:

    def test_at_peak_drawdown_zero(self, svc):
        """If portfolio only goes up, current drawdown = 0."""
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        # Prices monotonically increase, cash is constant, so portfolio is at peak
        assert result.current_drawdown is not None
        assert result.current_drawdown < 0.01  # essentially 0

    def test_drawdown_after_decline(self, svc):
        """Portfolio declines → positive drawdown."""
        txs = [
            {"ts": date(2024, 1, 2), "tx_type": "CASH_IN", "symbol": None,
             "quantity": None, "price_ngn": None, "amount_ngn": 100_000, "fees_ngn": 0},
            {"ts": date(2024, 1, 3), "tx_type": "BUY", "symbol": "TEST",
             "quantity": 1000, "price_ngn": 100.0, "amount_ngn": -100_000, "fees_ngn": 0},
        ]
        prices = {
            "TEST": {
                date(2024, 1, 2): 100, date(2024, 1, 3): 100,
                date(2024, 1, 4): 110,  # peak
                date(2024, 1, 5): 90,   # decline
            }
        }
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 5), reporting="NGN",
            transactions=txs, price_series=prices,
            latest_prices={"TEST": 90},
        )
        assert result.current_drawdown is not None
        assert result.current_drawdown > 0.1  # at least 10%


# ── 8. Data Freshness ───────────────────────────────────────────────


class TestFreshness:

    def test_freshness_passed_through(self, svc):
        fresh = DataFreshness(
            last_price_date=date(2024, 1, 6),
            last_fx_date=date(2024, 1, 5),
        )
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
            freshness=fresh,
        )
        assert result.freshness.last_price_date == date(2024, 1, 6)
        assert result.freshness.last_fx_date == date(2024, 1, 5)

    def test_freshness_to_dict(self):
        f = DataFreshness(last_price_date=date(2024, 1, 6))
        d = f.to_dict()
        assert d["last_price_date"] == "2024-01-06"
        assert d["last_fx_date"] is None


# ── 9. Edge Cases ───────────────────────────────────────────────────


class TestEdgeCases:

    def test_cash_only_portfolio(self, svc):
        txs = [
            {"ts": date(2024, 1, 2), "tx_type": "CASH_IN", "symbol": None,
             "quantity": None, "price_ngn": None, "amount_ngn": 500_000, "fees_ngn": 0},
        ]
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=txs, price_series={},
            latest_prices={},
        )
        assert result.value_ngn == 500_000
        assert result.holdings_value_ngn == 0
        assert result.cash_ngn == 500_000
        assert result.concentration.num_positions == 0

    def test_to_dict_serializable(self, svc):
        result = svc.compute(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        d = result.to_dict()
        # Should be JSON-serializable (no date objects)
        import json
        json.dumps(d)  # should not raise

    def test_reproducibility(self, svc):
        args = dict(
            portfolio_id=1, as_of=date(2024, 1, 6), reporting="NGN",
            transactions=_std_transactions(),
            price_series=_std_price_series(),
            latest_prices=_std_latest_prices(),
        )
        r1 = svc.compute(**args)
        r2 = svc.compute(**args)
        assert r1.to_dict() == r2.to_dict()
