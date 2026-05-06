"""Tests for PortfolioRiskManager — position sizing, concentration limits, drawdown protection."""

import pytest
from app.services.portfolio_risk import (
    PortfolioRiskManager,
    RiskLimits,
    PositionSizing,
    PortfolioRiskReport,
)


@pytest.fixture
def mgr():
    return PortfolioRiskManager()


@pytest.fixture
def custom_mgr():
    return PortfolioRiskManager(RiskLimits(
        max_position_weight=0.05,
        max_sector_weight=0.25,
        drawdown_halt_threshold=10.0,
        drawdown_reduce_threshold=5.0,
    ))


# ── Position Sizing: basic cases ─────────────────────────────────────────────

class TestPositionSizingBasic:

    def test_buy_low_risk_full_confidence(self, mgr):
        result = mgr.compute_position_size(
            symbol="ZENITHBANK", action="BUY", confidence=80.0,
            current_price=35.0, risk_level="low", sector="Financial Services",
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        assert result.approved is True
        assert result.suggested_shares > 0
        assert result.suggested_value_ngn > 0
        assert result.position_weight_pct > 0

    def test_strong_buy_approved(self, mgr):
        result = mgr.compute_position_size(
            symbol="SEPLAT", action="STRONG_BUY", confidence=85.0,
            current_price=4500.0, risk_level="moderate", sector="Oil & Gas",
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        assert result.approved is True
        assert result.suggested_shares > 0

    def test_non_buy_action_always_approved(self, mgr):
        for action in ("HOLD", "SELL", "STRONG_SELL", "AVOID"):
            result = mgr.compute_position_size(
                symbol="X", action=action, confidence=10.0,
                current_price=100.0, risk_level="very_high", sector=None,
                portfolio_value=10_000_000, cash_available=0,
            )
            assert result.approved is True
            assert result.suggested_shares == 0

    def test_zero_portfolio_value_rejected(self, mgr):
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=0, cash_available=0,
        )
        assert result.approved is False
        assert "Invalid" in result.rejection_reason

    def test_zero_price_rejected(self, mgr):
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        assert result.approved is False


# ── Confidence Scaling ────────────────────────────────────────────────────────

class TestConfidenceScaling:

    def test_below_minimum_confidence_rejected(self, mgr):
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=40.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        assert result.approved is False
        assert "Confidence" in result.rejection_reason

    def test_borderline_confidence_approved(self, mgr):
        # 51% is just above min_confidence_for_any_size (50%)
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=51.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        assert result.approved is True
        assert result.confidence_scale_factor < 1.0  # scaled down

    def test_full_confidence_no_scaling(self, mgr):
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        assert result.approved is True
        assert result.confidence_scale_factor == 1.0

    def test_higher_confidence_gives_larger_position(self, mgr):
        low = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=55.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        high = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        assert high.suggested_shares > low.suggested_shares


# ── Risk Level Scaling ────────────────────────────────────────────────────────

class TestRiskLevelScaling:

    def test_very_high_risk_smaller_than_low_risk(self, mgr):
        low_risk = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        very_high = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="very_high", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        assert very_high.suggested_shares < low_risk.suggested_shares

    def test_low_liquidity_caps_position(self, mgr):
        normal = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
            liquidity_tier="high",
        )
        low_liq = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
            liquidity_tier="low",
        )
        assert low_liq.suggested_shares < normal.suggested_shares


# ── Drawdown Circuit Breaker ──────────────────────────────────────────────────

class TestDrawdownProtection:

    def test_drawdown_below_threshold_normal(self, mgr):
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
            portfolio_drawdown_pct=3.0,
        )
        assert result.approved is True
        assert result.drawdown_scale_factor == 1.0

    def test_drawdown_reduce_zone(self, mgr):
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
            portfolio_drawdown_pct=10.0,
        )
        assert result.approved is True
        assert result.drawdown_scale_factor < 1.0

    def test_drawdown_halt_rejects(self, mgr):
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
            portfolio_drawdown_pct=16.0,
        )
        assert result.approved is False
        assert "drawdown" in result.rejection_reason.lower()

    def test_custom_drawdown_thresholds(self, custom_mgr):
        result = custom_mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
            portfolio_drawdown_pct=11.0,
        )
        assert result.approved is False  # Custom halt at 10%


# ── Sector Concentration ──────────────────────────────────────────────────────

class TestSectorConcentration:

    def test_sector_at_limit_rejected(self, mgr):
        result = mgr.compute_position_size(
            symbol="UBA", action="BUY", confidence=80.0,
            current_price=20.0, risk_level="low", sector="Financial Services",
            portfolio_value=10_000_000, cash_available=5_000_000,
            sector_weights={"Financial Services": 0.36},
        )
        assert result.approved is False
        assert "Sector" in result.rejection_reason

    def test_sector_above_20_pct_penalty(self, mgr):
        no_sector = mgr.compute_position_size(
            symbol="UBA", action="BUY", confidence=80.0,
            current_price=20.0, risk_level="low", sector="Financial Services",
            portfolio_value=10_000_000, cash_available=5_000_000,
            sector_weights={"Financial Services": 0.10},
        )
        heavy_sector = mgr.compute_position_size(
            symbol="UBA", action="BUY", confidence=80.0,
            current_price=20.0, risk_level="low", sector="Financial Services",
            portfolio_value=10_000_000, cash_available=5_000_000,
            sector_weights={"Financial Services": 0.25},
        )
        assert heavy_sector.suggested_shares < no_sector.suggested_shares

    def test_no_sector_info_no_penalty(self, mgr):
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        assert result.approved is True
        assert result.sector_scale_factor == 1.0


# ── Cash Reserve ──────────────────────────────────────────────────────────────

class TestCashReserve:

    def test_insufficient_cash_after_reserve(self, mgr):
        # Portfolio worth 10M, cash 900K (< 10% reserve of 1M)
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=900_000,
        )
        assert result.approved is False
        assert "cash" in result.rejection_reason.lower() or "reserve" in result.rejection_reason.lower()

    def test_cash_above_reserve_approved(self, mgr):
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=2_000_000,
        )
        assert result.approved is True


# ── Existing Position ─────────────────────────────────────────────────────────

class TestExistingPosition:

    def test_existing_position_at_max_rejected(self, mgr):
        # max for low risk = 10% of 10M = 1M. Existing = 1M.
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
            existing_position_value=1_000_000,
        )
        assert result.approved is False
        assert "Existing" in result.rejection_reason

    def test_existing_position_partial_room(self, mgr):
        result = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
            existing_position_value=500_000,
        )
        assert result.approved is True
        # Should suggest less than if no existing position
        fresh = mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
            existing_position_value=0,
        )
        assert result.suggested_shares < fresh.suggested_shares


# ── Serialization ─────────────────────────────────────────────────────────────

class TestSerialization:

    def test_position_sizing_to_dict(self, mgr):
        result = mgr.compute_position_size(
            symbol="ZENITHBANK", action="BUY", confidence=80.0,
            current_price=35.0, risk_level="low", sector="Financial Services",
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        d = result.to_dict()
        assert d["symbol"] == "ZENITHBANK"
        assert d["approved"] is True
        assert isinstance(d["suggested_shares"], int)
        assert isinstance(d["warnings"], list)


# ── Portfolio Risk Report ─────────────────────────────────────────────────────

class TestPortfolioRiskReport:

    def test_empty_portfolio(self, mgr):
        report = mgr.compute_risk_report(
            positions=[], cash_ngn=1_000_000,
            portfolio_value=1_000_000, peak_value=1_000_000,
            sector_lookup={},
        )
        assert report.num_positions == 0
        assert report.cash_pct == 100.0
        assert report.drawdown_pct == 0.0

    def test_concentrated_portfolio_flagged(self, mgr):
        positions = [
            {"symbol": "GTCO", "market_value_ngn": 6_000_000},
            {"symbol": "UBA", "market_value_ngn": 3_000_000},
        ]
        report = mgr.compute_risk_report(
            positions=positions, cash_ngn=1_000_000,
            portfolio_value=10_000_000, peak_value=10_000_000,
            sector_lookup={"GTCO": "Financial Services", "UBA": "Financial Services"},
        )
        assert report.largest_position_pct == 60.0
        assert report.largest_position_symbol == "GTCO"
        assert len(report.risk_flags) > 0  # Over 10% limit
        assert report.largest_sector_pct == 90.0

    def test_drawdown_flagged(self, mgr):
        report = mgr.compute_risk_report(
            positions=[{"symbol": "X", "market_value_ngn": 7_000_000}],
            cash_ngn=1_000_000,
            portfolio_value=8_000_000, peak_value=10_000_000,
            sector_lookup={"X": "Tech"},
        )
        assert report.drawdown_pct == 20.0
        assert any("CIRCUIT BREAKER" in f for f in report.risk_flags)

    def test_hhi_calculation(self, mgr):
        # 2 equal positions of 40% each + 20% cash
        positions = [
            {"symbol": "A", "market_value_ngn": 4_000_000},
            {"symbol": "B", "market_value_ngn": 4_000_000},
        ]
        report = mgr.compute_risk_report(
            positions=positions, cash_ngn=2_000_000,
            portfolio_value=10_000_000, peak_value=10_000_000,
            sector_lookup={"A": "Sector1", "B": "Sector2"},
        )
        # HHI = 40^2 + 40^2 = 3200
        assert abs(report.hhi - 3200.0) < 1.0

    def test_zero_portfolio_value(self, mgr):
        report = mgr.compute_risk_report(
            positions=[], cash_ngn=0,
            portfolio_value=0, peak_value=0,
            sector_lookup={},
        )
        assert report.num_positions == 0
        assert "no value" in report.risk_flags[0].lower()

    def test_report_to_dict(self, mgr):
        report = mgr.compute_risk_report(
            positions=[{"symbol": "X", "market_value_ngn": 5_000_000}],
            cash_ngn=5_000_000,
            portfolio_value=10_000_000, peak_value=10_000_000,
            sector_lookup={"X": "Banking"},
        )
        d = report.to_dict()
        assert "total_value_ngn" in d
        assert "hhi" in d
        assert "risk_flags" in d
        assert isinstance(d["sector_weights"], dict)


# ── Custom Limits ─────────────────────────────────────────────────────────────

class TestCustomLimits:

    def test_stricter_position_limit(self, custom_mgr):
        # Custom max is 5%, so max value = 5% of 10M = 500K
        result = custom_mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector=None,
            portfolio_value=10_000_000, cash_available=5_000_000,
        )
        assert result.approved is True
        assert result.suggested_value_ngn <= 500_000 + 100  # +100 for rounding

    def test_stricter_sector_limit(self, custom_mgr):
        # Custom sector max is 25%
        result = custom_mgr.compute_position_size(
            symbol="X", action="BUY", confidence=80.0,
            current_price=100.0, risk_level="low", sector="Financial Services",
            portfolio_value=10_000_000, cash_available=5_000_000,
            sector_weights={"Financial Services": 0.26},
        )
        assert result.approved is False
