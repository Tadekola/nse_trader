"""
Tests for the Nigeria Growth Potential Scorer.

Validates:
1. Growth rate computation (YoY, CAGR)
2. Sector macro alignment mapping
3. Growth potential composite scoring
4. GrowthProfile construction from mock data
5. Edge cases (missing data, negative growth, single period)
"""
import pytest
from datetime import date
from app.services.growth_scorer import (
    GrowthProfile,
    SECTOR_MACRO_ALIGNMENT,
    compute_yoy_growth,
    compute_cagr,
    compute_growth_potential,
    _score_growth_rate,
    _score_roe,
    _score_quality,
    _score_balance_sheet,
    _score_valuation,
)


# ═══════════════════════════════════════════════════════════════════════
# Growth rate computation
# ═══════════════════════════════════════════════════════════════════════


class TestYoYGrowth:
    """Year-over-year growth from periodic fundamentals."""

    def test_positive_revenue_growth(self):
        periods = [
            {"period_end_date": date(2022, 12, 31), "period_type": "ANNUAL", "revenue": 100_000},
            {"period_end_date": date(2023, 12, 31), "period_type": "ANNUAL", "revenue": 130_000},
        ]
        growth = compute_yoy_growth(periods, "revenue")
        assert growth == pytest.approx(0.30, abs=0.001)

    def test_negative_earnings_growth(self):
        periods = [
            {"period_end_date": date(2022, 12, 31), "period_type": "ANNUAL", "net_income": 50_000},
            {"period_end_date": date(2023, 12, 31), "period_type": "ANNUAL", "net_income": 35_000},
        ]
        growth = compute_yoy_growth(periods, "net_income")
        assert growth == pytest.approx(-0.30, abs=0.001)

    def test_single_period_returns_none(self):
        periods = [
            {"period_end_date": date(2023, 12, 31), "period_type": "ANNUAL", "revenue": 100_000},
        ]
        assert compute_yoy_growth(periods, "revenue") is None

    def test_zero_base_returns_none(self):
        periods = [
            {"period_end_date": date(2022, 12, 31), "period_type": "ANNUAL", "revenue": 0},
            {"period_end_date": date(2023, 12, 31), "period_type": "ANNUAL", "revenue": 50_000},
        ]
        assert compute_yoy_growth(periods, "revenue") is None

    def test_missing_field_returns_none(self):
        periods = [
            {"period_end_date": date(2022, 12, 31), "period_type": "ANNUAL"},
            {"period_end_date": date(2023, 12, 31), "period_type": "ANNUAL"},
        ]
        assert compute_yoy_growth(periods, "revenue") is None

    def test_ignores_interim_periods(self):
        periods = [
            {"period_end_date": date(2022, 12, 31), "period_type": "ANNUAL", "revenue": 100_000},
            {"period_end_date": date(2023, 6, 30), "period_type": "INTERIM", "revenue": 60_000},
            {"period_end_date": date(2023, 12, 31), "period_type": "ANNUAL", "revenue": 120_000},
        ]
        growth = compute_yoy_growth(periods, "revenue")
        assert growth == pytest.approx(0.20, abs=0.001)

    def test_uses_latest_two_annual(self):
        """With 3 annual periods, should use most recent two."""
        periods = [
            {"period_end_date": date(2021, 12, 31), "period_type": "ANNUAL", "revenue": 80_000},
            {"period_end_date": date(2022, 12, 31), "period_type": "ANNUAL", "revenue": 100_000},
            {"period_end_date": date(2023, 12, 31), "period_type": "ANNUAL", "revenue": 150_000},
        ]
        growth = compute_yoy_growth(periods, "revenue")
        assert growth == pytest.approx(0.50, abs=0.001)


class TestCAGR:
    """Compound annual growth rate across all periods."""

    def test_two_year_cagr(self):
        periods = [
            {"period_end_date": date(2021, 12, 31), "period_type": "ANNUAL", "revenue": 100_000},
            {"period_end_date": date(2023, 12, 31), "period_type": "ANNUAL", "revenue": 144_000},
        ]
        cagr = compute_cagr(periods, "revenue")
        # (144000/100000)^(1/2) - 1 = 0.2
        assert cagr == pytest.approx(0.20, abs=0.01)

    def test_single_period_returns_none(self):
        periods = [
            {"period_end_date": date(2023, 12, 31), "period_type": "ANNUAL", "revenue": 100_000},
        ]
        assert compute_cagr(periods, "revenue") is None

    def test_negative_values_returns_none(self):
        periods = [
            {"period_end_date": date(2022, 12, 31), "period_type": "ANNUAL", "revenue": -10_000},
            {"period_end_date": date(2023, 12, 31), "period_type": "ANNUAL", "revenue": 50_000},
        ]
        assert compute_cagr(periods, "revenue") is None


# ═══════════════════════════════════════════════════════════════════════
# Sub-score functions
# ═══════════════════════════════════════════════════════════════════════


class TestSubScores:

    def test_growth_rate_high(self):
        assert _score_growth_rate(0.35) == 1.0

    def test_growth_rate_moderate(self):
        score = _score_growth_rate(0.15)
        assert 0.4 < score < 0.6

    def test_growth_rate_negative(self):
        assert _score_growth_rate(-0.15) == 0.0

    def test_growth_rate_none(self):
        assert _score_growth_rate(None) == 0.3

    def test_roe_excellent(self):
        assert _score_roe(0.30) == 1.0

    def test_roe_good(self):
        assert _score_roe(0.16) == 0.8

    def test_roe_weak(self):
        assert _score_roe(0.02) == 0.2

    def test_roe_negative(self):
        assert _score_roe(-0.05) == 0.0

    def test_quality_high(self):
        assert _score_quality(85) == pytest.approx(1.0, abs=0.05)

    def test_quality_low(self):
        assert _score_quality(20) == pytest.approx(0.25, abs=0.01)

    def test_balance_sheet_conservative(self):
        assert _score_balance_sheet(0.2) == 1.0

    def test_balance_sheet_high_leverage(self):
        assert _score_balance_sheet(4.0) == 0.2

    def test_valuation_low_peg(self):
        """Low P/E with good growth → high score."""
        assert _score_valuation(8.0, 0.25) >= 0.8

    def test_valuation_high_peg(self):
        """High P/E with low growth → low score."""
        assert _score_valuation(30.0, 0.05) <= 0.5

    def test_valuation_no_growth(self):
        """No growth data → use absolute P/E."""
        assert _score_valuation(4.0, None) >= 0.8


# ═══════════════════════════════════════════════════════════════════════
# Sector macro alignment
# ═══════════════════════════════════════════════════════════════════════


class TestSectorAlignment:

    def test_financial_services_highest(self):
        assert SECTOR_MACRO_ALIGNMENT["Financial Services"] >= 0.90

    def test_ict_high(self):
        assert SECTOR_MACRO_ALIGNMENT["ICT"] >= 0.85

    def test_conglomerates_lowest(self):
        assert SECTOR_MACRO_ALIGNMENT["Conglomerates"] <= 0.60

    def test_all_sectors_present(self):
        """All Sector enum values have an alignment score."""
        from app.data.sources.ngx_stocks import Sector
        for s in Sector:
            assert s.value in SECTOR_MACRO_ALIGNMENT, f"Missing: {s.value}"


# ═══════════════════════════════════════════════════════════════════════
# Composite growth potential
# ═══════════════════════════════════════════════════════════════════════


class TestGrowthPotential:

    def test_high_growth_stock(self):
        """Stock with strong fundamentals scores high."""
        p = GrowthProfile(
            symbol="TEST",
            revenue_growth=0.30,
            earnings_growth=0.40,
            quality_score=70,
            roe=0.25,
            sector="Financial Services",
            sector_macro_alignment=0.95,
            debt_to_equity=0.5,
            pe_ratio=8.0,
        )
        p.growth_potential = compute_growth_potential(p)
        assert p.growth_potential >= 70

    def test_weak_stock(self):
        """Stock with declining fundamentals scores low."""
        p = GrowthProfile(
            symbol="WEAK",
            revenue_growth=-0.15,
            earnings_growth=-0.20,
            quality_score=20,
            roe=0.02,
            sector="Conglomerates",
            sector_macro_alignment=0.55,
            debt_to_equity=3.5,
            pe_ratio=30.0,
        )
        p.growth_potential = compute_growth_potential(p)
        assert p.growth_potential <= 30

    def test_missing_data_degrades_gracefully(self):
        """Stock with no data gets a neutral score, not zero."""
        p = GrowthProfile(symbol="NODATA")
        p.growth_potential = compute_growth_potential(p)
        assert 20 <= p.growth_potential <= 50

    def test_growth_factors_populated(self):
        """Growth factors list is populated for high-growth stocks."""
        p = GrowthProfile(
            symbol="GROW",
            revenue_growth=0.25,
            earnings_growth=0.35,
            quality_score=65,
            roe=0.20,
            sector="ICT",
            sector_macro_alignment=0.90,
        )
        p.growth_potential = compute_growth_potential(p)
        assert len(p.growth_factors) >= 3

    def test_risk_factors_populated(self):
        """Risk factors list is populated for risky stocks."""
        p = GrowthProfile(
            symbol="RISKY",
            revenue_growth=-0.10,
            debt_to_equity=3.0,
            earnings_stability=0.2,
            quality_score=15,
        )
        p.growth_potential = compute_growth_potential(p)
        assert len(p.risk_factors) >= 2
