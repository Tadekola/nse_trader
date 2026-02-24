"""
Fundamentals Ingestion Tests (PR3).

Covers:
  1. CSV parsing: valid rows, missing fields, invalid dates, numeric handling
  2. Derived metrics: profitability, balance sheet, cash quality, stability
  3. Edge cases: negative equity, net loss, missing data, single period
  4. Red flags: all trigger conditions
  5. Deterministic: same input → same output
"""

import os
import sys
import pytest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scanner.fundamentals_csv import (
    parse_fundamentals_csv,
    FundamentalsParseResult,
)
from app.scanner.derived_metrics import (
    compute_derived_metrics,
    DerivedMetrics,
    _safe_div,
    _coefficient_of_variation,
)


# ═══════════════════════════════════════════════════════════════════════
# CSV Parsing Tests
# ═══════════════════════════════════════════════════════════════════════

VALID_CSV = """symbol,period_end_date,period_type,revenue,operating_profit,net_income,total_assets,total_equity,total_debt,cash,operating_cash_flow,capex,dividends_paid,shares_outstanding,source
DANGCEM,2024-12-31,ANNUAL,2000000,600000,400000,3000000,1500000,500000,200000,550000,150000,100000,17000,annual_report
GTCO,2024-12-31,ANNUAL,800000,300000,250000,5000000,600000,200000,1000000,280000,50000,80000,29000,annual_report
ZENITH,2024-12-31,ANNUAL,1200000,500000,350000,8000000,900000,400000,1500000,400000,80000,120000,31000,annual_report
"""


class TestCSVParsing:
    def test_valid_csv(self):
        """Valid CSV should parse all rows successfully."""
        result = parse_fundamentals_csv(VALID_CSV)
        assert result.rows_total == 3
        assert result.rows_accepted == 3
        assert result.rows_rejected == 0
        assert len(result.errors) == 0

    def test_symbols_uppercase(self):
        """Symbols should be normalized to uppercase."""
        csv = "symbol,period_end_date\ndangcem,2024-12-31\n"
        result = parse_fundamentals_csv(csv)
        assert result.records[0]["symbol"] == "DANGCEM"

    def test_missing_symbol_rejected(self):
        """Row with blank symbol should be rejected."""
        csv = "symbol,period_end_date\n,2024-12-31\n"
        result = parse_fundamentals_csv(csv)
        assert result.rows_rejected == 1
        assert any(e.field == "symbol" for e in result.errors)

    def test_missing_date_rejected(self):
        """Row with invalid date should be rejected."""
        csv = "symbol,period_end_date\nDAN,not-a-date\n"
        result = parse_fundamentals_csv(csv)
        assert result.rows_rejected == 1

    def test_missing_header_column(self):
        """CSV missing required header columns should error."""
        csv = "name,revenue\nDAN,1000\n"
        result = parse_fundamentals_csv(csv)
        assert any("Missing required columns" in e.message for e in result.errors)
        assert result.rows_accepted == 0

    def test_numeric_fields_nullable(self):
        """Blank numeric fields should parse as None."""
        csv = "symbol,period_end_date,revenue,net_income\nDAN,2024-12-31,,\n"
        result = parse_fundamentals_csv(csv)
        assert result.rows_accepted == 1
        assert result.records[0]["revenue"] is None
        assert result.records[0]["net_income"] is None

    def test_comma_in_numbers(self):
        """Numbers with commas should be parsed correctly."""
        csv = "symbol,period_end_date,revenue\nDAN,2024-12-31,\"1,500,000\"\n"
        result = parse_fundamentals_csv(csv)
        assert result.records[0]["revenue"] == 1_500_000

    def test_negative_values_allowed(self):
        """Negative numbers (losses) should be accepted."""
        csv = "symbol,period_end_date,net_income\nDAN,2024-12-31,-50000\n"
        result = parse_fundamentals_csv(csv)
        assert result.records[0]["net_income"] == -50000

    def test_na_values(self):
        """N/A and similar markers should parse as None."""
        csv = "symbol,period_end_date,revenue,cash\nDAN,2024-12-31,N/A,null\n"
        result = parse_fundamentals_csv(csv)
        assert result.records[0]["revenue"] is None
        assert result.records[0]["cash"] is None

    def test_default_period_type(self):
        """Missing period_type should default to ANNUAL."""
        csv = "symbol,period_end_date\nDAN,2024-12-31\n"
        result = parse_fundamentals_csv(csv)
        assert result.records[0]["period_type"] == "ANNUAL"

    def test_default_source(self):
        """Missing source should use default_source param."""
        csv = "symbol,period_end_date\nDAN,2024-12-31\n"
        result = parse_fundamentals_csv(csv, default_source="my_source")
        assert result.records[0]["source"] == "my_source"

    def test_csv_hash_computed(self):
        """Parse result should contain a CSV hash."""
        result = parse_fundamentals_csv(VALID_CSV)
        assert len(result.csv_hash) == 16

    def test_empty_csv(self):
        """Empty CSV should produce an error."""
        result = parse_fundamentals_csv("")
        assert result.rows_accepted == 0

    def test_alternate_date_format(self):
        """DD/MM/YYYY dates should also be accepted."""
        csv = "symbol,period_end_date\nDAN,31/12/2024\n"
        result = parse_fundamentals_csv(csv)
        assert result.rows_accepted == 1
        assert result.records[0]["period_end_date"] == date(2024, 12, 31)


# ═══════════════════════════════════════════════════════════════════════
# Derived Metrics Tests
# ═══════════════════════════════════════════════════════════════════════

def _period(end_date, revenue=1000, op_profit=300, net_income=200,
            total_assets=5000, total_equity=1000, total_debt=500,
            cash=300, ocf=250, capex=100, div_paid=50, shares=100):
    """Helper to build a period dict."""
    return {
        "period_end_date": end_date,
        "revenue": revenue,
        "operating_profit": op_profit,
        "net_income": net_income,
        "total_assets": total_assets,
        "total_equity": total_equity,
        "total_debt": total_debt,
        "cash": cash,
        "operating_cash_flow": ocf,
        "capex": capex,
        "dividends_paid": div_paid,
        "shares_outstanding": shares,
    }


AS_OF = date(2025, 6, 15)


class TestDerivedMetrics:
    def test_basic_profitability(self):
        """ROE and margins should be correctly computed."""
        periods = [_period(date(2024, 12, 31))]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert abs(m.roe - 0.2) < 0.001         # 200/1000
        assert abs(m.op_margin - 0.3) < 0.001   # 300/1000
        assert abs(m.net_margin - 0.2) < 0.001  # 200/1000

    def test_roic_proxy(self):
        """ROIC proxy = operating_profit / (equity + debt)."""
        periods = [_period(date(2024, 12, 31))]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert abs(m.roic_proxy - 0.2) < 0.001  # 300/1500

    def test_balance_sheet_ratios(self):
        """D/E and Cash/Debt should be computed."""
        periods = [_period(date(2024, 12, 31))]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert abs(m.debt_to_equity - 0.5) < 0.001   # 500/1000
        assert abs(m.cash_to_debt - 0.6) < 0.001     # 300/500

    def test_cash_conversion(self):
        """OCF/NI should be correctly computed."""
        periods = [_period(date(2024, 12, 31))]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert abs(m.ocf_to_net_income - 1.25) < 0.001  # 250/200

    def test_fcf_calculation(self):
        """FCF = OCF - |capex|."""
        periods = [_period(date(2024, 12, 31), ocf=250, capex=100)]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert abs(m.fcf - 150) < 0.001  # 250 - 100

    def test_fcf_no_capex(self):
        """If capex is None, FCF = OCF."""
        periods = [_period(date(2024, 12, 31), ocf=250, capex=None)]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert abs(m.fcf - 250) < 0.001

    def test_earnings_stability_stable(self):
        """Stable earnings across periods should yield high stability."""
        periods = [
            _period(date(2022, 12, 31), net_income=200),
            _period(date(2023, 12, 31), net_income=210),
            _period(date(2024, 12, 31), net_income=205),
        ]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert m.earnings_stability is not None
        assert m.earnings_stability > 0.9  # very stable

    def test_earnings_stability_volatile(self):
        """Volatile earnings should yield lower stability."""
        periods = [
            _period(date(2022, 12, 31), net_income=100),
            _period(date(2023, 12, 31), net_income=500),
            _period(date(2024, 12, 31), net_income=50),
        ]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert m.earnings_stability is not None
        assert m.earnings_stability < 0.5

    def test_margin_stability(self):
        """Margin stability uses operating margin across periods."""
        periods = [
            _period(date(2022, 12, 31), revenue=1000, op_profit=300),
            _period(date(2023, 12, 31), revenue=1000, op_profit=310),
            _period(date(2024, 12, 31), revenue=1000, op_profit=295),
        ]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert m.margin_stability is not None
        assert m.margin_stability > 0.9

    def test_no_data(self):
        """Empty periods list should flag NO_FUNDAMENTALS_DATA."""
        m = compute_derived_metrics("TEST", [], AS_OF)
        assert "NO_FUNDAMENTALS_DATA" in m.red_flags
        assert m.periods_available == 0

    def test_single_period_no_stability(self):
        """Single period can't compute stability (needs >= 2)."""
        periods = [_period(date(2024, 12, 31))]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert m.earnings_stability is None
        assert "INSUFFICIENT_HISTORY" in m.red_flags

    def test_negative_equity_flag(self):
        """Negative equity should trigger NEGATIVE_EQUITY red flag."""
        periods = [_period(date(2024, 12, 31), total_equity=-100)]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert "NEGATIVE_EQUITY" in m.red_flags

    def test_net_loss_flag(self):
        """Negative net income should trigger NET_LOSS flag."""
        periods = [_period(date(2024, 12, 31), net_income=-50)]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert "NET_LOSS" in m.red_flags

    def test_negative_ocf_flag(self):
        """Negative OCF should trigger NEGATIVE_OCF flag."""
        periods = [_period(date(2024, 12, 31), ocf=-20)]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert "NEGATIVE_OCF" in m.red_flags

    def test_consecutive_negative_ocf(self):
        """Two periods with negative OCF should flag CONSECUTIVE_NEGATIVE_OCF."""
        periods = [
            _period(date(2023, 12, 31), ocf=-10),
            _period(date(2024, 12, 31), ocf=-20),
        ]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert "CONSECUTIVE_NEGATIVE_OCF" in m.red_flags

    def test_stale_fundamentals_flag(self):
        """Old data (> 540 days) should flag STALE_FUNDAMENTALS."""
        old_date = date(2022, 1, 1)
        periods = [_period(old_date)]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert "STALE_FUNDAMENTALS" in m.red_flags

    def test_high_leverage_flag(self):
        """D/E > 2.0 should flag HIGH_LEVERAGE."""
        periods = [_period(date(2024, 12, 31), total_debt=2500, total_equity=1000)]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert "HIGH_LEVERAGE" in m.red_flags

    def test_cash_conversion_both_negative(self):
        """Both NI and OCF negative → cash conversion should be None."""
        periods = [_period(date(2024, 12, 31), net_income=-100, ocf=-50)]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert m.ocf_to_net_income is None

    def test_zero_revenue(self):
        """Zero revenue → margins should be None."""
        periods = [_period(date(2024, 12, 31), revenue=0)]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert m.op_margin is None
        assert m.net_margin is None

    def test_zero_equity(self):
        """Zero equity → ROE should be None."""
        periods = [_period(date(2024, 12, 31), total_equity=0)]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert m.roe is None

    def test_zero_debt(self):
        """Zero debt → D/E should be None, Cash/Debt should be None."""
        periods = [_period(date(2024, 12, 31), total_debt=0)]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        assert m.debt_to_equity == 0.0  # 0/1000 = 0
        assert m.cash_to_debt is None   # can't divide by 0

    def test_data_freshness(self):
        """Freshness days should be computed from latest period to as_of."""
        periods = [_period(date(2024, 12, 31))]
        as_of = date(2025, 3, 15)
        m = compute_derived_metrics("TEST", periods, as_of)
        assert m.data_freshness_days == (as_of - date(2024, 12, 31)).days

    def test_to_dict(self):
        """to_dict should return all expected keys."""
        periods = [_period(date(2024, 12, 31))]
        m = compute_derived_metrics("TEST", periods, AS_OF)
        d = m.to_dict()
        assert "roe" in d
        assert "op_margin" in d
        assert "fcf" in d
        assert "red_flags" in d
        assert "periods_available" in d

    def test_deterministic(self):
        """Same input should produce identical output."""
        periods = [
            _period(date(2023, 12, 31)),
            _period(date(2024, 12, 31)),
        ]
        m1 = compute_derived_metrics("TEST", periods, AS_OF)
        m2 = compute_derived_metrics("TEST", periods, AS_OF)
        assert m1.roe == m2.roe
        assert m1.earnings_stability == m2.earnings_stability
        assert m1.red_flags == m2.red_flags


# ═══════════════════════════════════════════════════════════════════════
# Helper function tests
# ═══════════════════════════════════════════════════════════════════════

class TestHelpers:
    def test_safe_div_normal(self):
        assert _safe_div(10, 5) == 2.0

    def test_safe_div_zero_denom(self):
        assert _safe_div(10, 0) is None

    def test_safe_div_none_inputs(self):
        assert _safe_div(None, 5) is None
        assert _safe_div(10, None) is None

    def test_cov_stable(self):
        cov = _coefficient_of_variation([100, 101, 99, 100])
        assert cov is not None
        assert cov < 0.02

    def test_cov_volatile(self):
        cov = _coefficient_of_variation([10, 100, 500])
        assert cov is not None
        assert cov > 1.0

    def test_cov_single_value(self):
        assert _coefficient_of_variation([42]) is None

    def test_cov_zero_mean(self):
        assert _coefficient_of_variation([0, 0, 0]) is None
