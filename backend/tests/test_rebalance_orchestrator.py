"""Tests for RebalanceOrchestrator — trade generation, defensive mode, cash-raising."""

import pytest
from app.services.rebalance_orchestrator import (
    RebalanceOrchestrator,
    RebalancePlan,
    Trade,
    TradeAction,
)
from app.services.portfolio_risk import PortfolioRiskManager, RiskLimits


@pytest.fixture
def orch():
    return RebalanceOrchestrator()


@pytest.fixture
def sample_recs():
    """Sample recommendations: 2 BUYs, 1 HOLD, 1 SELL."""
    return [
        {
            "symbol": "ZENITHBANK",
            "action": "BUY",
            "confidence": 75.0,
            "current_price": 35.0,
            "risk_level": "low",
            "composite_score": 0.20,
        },
        {
            "symbol": "GTCO",
            "action": "BUY",
            "confidence": 65.0,
            "current_price": 45.0,
            "risk_level": "moderate",
            "composite_score": 0.15,
        },
        {
            "symbol": "DANGCEM",
            "action": "HOLD",
            "confidence": 55.0,
            "current_price": 300.0,
            "risk_level": "moderate",
            "composite_score": 0.02,
        },
        {
            "symbol": "PRESCO",
            "action": "SELL",
            "confidence": 60.0,
            "current_price": 200.0,
            "risk_level": "high",
            "composite_score": -0.18,
        },
    ]


@pytest.fixture
def sample_positions():
    """Sample portfolio: 3 existing positions."""
    return [
        {"symbol": "DANGCEM", "shares": 100, "market_value_ngn": 30_000},
        {"symbol": "PRESCO", "shares": 50, "market_value_ngn": 10_000},
        {"symbol": "UBA", "shares": 500, "market_value_ngn": 5_000},
    ]


@pytest.fixture
def sector_lookup():
    return {
        "ZENITHBANK": "Financial Services",
        "GTCO": "Financial Services",
        "DANGCEM": "Industrial Goods",
        "PRESCO": "Agriculture",
        "UBA": "Financial Services",
    }


# ── Normal mode ──────────────────────────────────────────────────────────────

class TestNormalMode:

    def test_basic_rebalance_produces_trades(self, orch, sample_recs, sample_positions, sector_lookup):
        plan = orch.generate_rebalance_plan(
            recommendations=sample_recs,
            positions=sample_positions,
            cash_ngn=5_000_000,
            portfolio_value=10_000_000,
            peak_value=10_000_000,
            sector_lookup=sector_lookup,
        )
        assert plan.mode == "normal"
        assert len(plan.trades) > 0
        assert plan.buys_count > 0
        # PRESCO should be sold
        sells = [t for t in plan.trades if t.action == TradeAction.SELL]
        assert any(t.symbol == "PRESCO" for t in sells)

    def test_buys_sorted_by_score(self, orch, sample_recs, sector_lookup):
        plan = orch.generate_rebalance_plan(
            recommendations=sample_recs,
            positions=[],
            cash_ngn=5_000_000,
            portfolio_value=10_000_000,
            peak_value=10_000_000,
            sector_lookup=sector_lookup,
        )
        buys = [t for t in plan.trades if t.action == TradeAction.BUY]
        if len(buys) >= 2:
            # ZENITHBANK (score 0.20) should appear before GTCO (0.15)
            symbols = [t.symbol for t in buys]
            assert symbols.index("ZENITHBANK") < symbols.index("GTCO")

    def test_hold_not_traded(self, orch, sample_recs, sector_lookup):
        plan = orch.generate_rebalance_plan(
            recommendations=sample_recs,
            positions=[],
            cash_ngn=5_000_000,
            portfolio_value=10_000_000,
            peak_value=10_000_000,
            sector_lookup=sector_lookup,
        )
        traded_syms = {t.symbol for t in plan.trades}
        assert "DANGCEM" not in traded_syms

    def test_empty_recommendations(self, orch, sector_lookup):
        plan = orch.generate_rebalance_plan(
            recommendations=[],
            positions=[],
            cash_ngn=5_000_000,
            portfolio_value=10_000_000,
            peak_value=10_000_000,
            sector_lookup=sector_lookup,
        )
        assert len(plan.trades) == 0
        assert plan.mode == "normal"

    def test_zero_portfolio_value(self, orch, sample_recs, sector_lookup):
        plan = orch.generate_rebalance_plan(
            recommendations=sample_recs,
            positions=[],
            cash_ngn=0,
            portfolio_value=0,
            peak_value=0,
            sector_lookup=sector_lookup,
        )
        assert len(plan.trades) == 0
        assert len(plan.warnings) > 0


# ── Trim oversized positions ─────────────────────────────────────────────────

class TestTrimPositions:

    def test_oversized_position_trimmed(self, orch, sector_lookup):
        # One position is 60% of portfolio — should be trimmed to 10%
        positions = [
            {"symbol": "DANGCEM", "shares": 200, "market_value_ngn": 6_000_000},
        ]
        plan = orch.generate_rebalance_plan(
            recommendations=[],
            positions=positions,
            cash_ngn=4_000_000,
            portfolio_value=10_000_000,
            peak_value=10_000_000,
            sector_lookup=sector_lookup,
            prices={"DANGCEM": 30_000},
        )
        trims = [t for t in plan.trades if t.action == TradeAction.TRIM]
        assert len(trims) == 1
        assert trims[0].symbol == "DANGCEM"
        assert trims[0].shares > 0

    def test_normal_position_not_trimmed(self, orch, sector_lookup):
        positions = [
            {"symbol": "DANGCEM", "shares": 10, "market_value_ngn": 300_000},
        ]
        plan = orch.generate_rebalance_plan(
            recommendations=[],
            positions=positions,
            cash_ngn=9_700_000,
            portfolio_value=10_000_000,
            peak_value=10_000_000,
            sector_lookup=sector_lookup,
        )
        trims = [t for t in plan.trades if t.action == TradeAction.TRIM]
        assert len(trims) == 0


# ── Defensive mode ───────────────────────────────────────────────────────────

class TestDefensiveMode:

    def test_defensive_mode_triggers(self, orch, sample_recs, sample_positions, sector_lookup):
        plan = orch.generate_rebalance_plan(
            recommendations=sample_recs,
            positions=sample_positions,
            cash_ngn=500_000,
            portfolio_value=9_000_000,
            peak_value=10_000_000,  # 10% drawdown
            sector_lookup=sector_lookup,
        )
        assert plan.mode == "defensive"
        assert any("DEFENSIVE" in w for w in plan.warnings)

    def test_defensive_raises_cash(self, orch, sector_lookup):
        # Each position ~9% of portfolio (under 11% trim threshold), low cash
        positions = [
            {"symbol": "DANGCEM", "shares": 100, "market_value_ngn": 900_000},
            {"symbol": "UBA", "shares": 10000, "market_value_ngn": 900_000},
            {"symbol": "ZENITHBANK", "shares": 300, "market_value_ngn": 900_000},
            {"symbol": "GTCO", "shares": 200, "market_value_ngn": 900_000},
            {"symbol": "PRESCO", "shares": 50, "market_value_ngn": 900_000},
        ]
        pv = 10_000_000  # each position = 9%
        recs = [
            {"symbol": "DANGCEM", "action": "HOLD", "confidence": 50, "current_price": 9000, "risk_level": "moderate", "composite_score": 0.01},
            {"symbol": "UBA", "action": "HOLD", "confidence": 50, "current_price": 0.09, "risk_level": "moderate", "composite_score": -0.01},
        ]
        plan = orch.generate_rebalance_plan(
            recommendations=recs,
            positions=positions,
            cash_ngn=500_000,  # 5% cash, need 20% in defensive
            portfolio_value=pv,
            peak_value=pv / 0.90,  # ~10% DD
            sector_lookup=sector_lookup,
            prices={"DANGCEM": 9000, "UBA": 0.09, "ZENITHBANK": 3.0, "GTCO": 4.5, "PRESCO": 18000},
        )
        assert plan.mode == "defensive"
        raise_cash = [t for t in plan.trades if t.action == TradeAction.RAISE_CASH]
        assert len(raise_cash) > 0


# ── Halt mode (circuit breaker) ──────────────────────────────────────────────

class TestHaltMode:

    def test_halt_mode_no_buys(self, orch, sample_recs, sample_positions, sector_lookup):
        plan = orch.generate_rebalance_plan(
            recommendations=sample_recs,
            positions=sample_positions,
            cash_ngn=500_000,
            portfolio_value=8_000_000,
            peak_value=10_000_000,  # 20% drawdown
            sector_lookup=sector_lookup,
        )
        assert plan.mode == "halt"
        assert plan.buys_count == 0
        assert any("CIRCUIT BREAKER" in w for w in plan.warnings)

    def test_halt_mode_raises_cash_aggressively(self, orch, sector_lookup):
        # Each position ~9% of portfolio (under 11% trim), low cash, 25% DD
        positions = [
            {"symbol": "DANGCEM", "shares": 10, "market_value_ngn": 900_000},
            {"symbol": "UBA", "shares": 10000, "market_value_ngn": 900_000},
            {"symbol": "ZENITHBANK", "shares": 300, "market_value_ngn": 900_000},
            {"symbol": "GTCO", "shares": 200, "market_value_ngn": 900_000},
            {"symbol": "PRESCO", "shares": 50, "market_value_ngn": 900_000},
        ]
        pv = 10_000_000  # each position = 9%
        recs = [
            {"symbol": "DANGCEM", "action": "HOLD", "confidence": 50, "current_price": 90000, "risk_level": "moderate", "composite_score": 0.01},
        ]
        plan = orch.generate_rebalance_plan(
            recommendations=recs,
            positions=positions,
            cash_ngn=500_000,  # 5% cash, need 30% in halt
            portfolio_value=pv,
            peak_value=pv / 0.75,  # 25% DD
            sector_lookup=sector_lookup,
            prices={"DANGCEM": 90000, "UBA": 0.09, "ZENITHBANK": 3.0, "GTCO": 4.5, "PRESCO": 18000},
        )
        assert plan.mode == "halt"
        raise_cash = [t for t in plan.trades if t.action == TradeAction.RAISE_CASH]
        total_raised = sum(t.estimated_value_ngn for t in raise_cash)
        assert total_raised > 0

    def test_halt_mentions_money_market(self, orch, sample_recs, sector_lookup):
        plan = orch.generate_rebalance_plan(
            recommendations=sample_recs,
            positions=[{"symbol": "X", "shares": 100, "market_value_ngn": 5_000_000}],
            cash_ngn=500_000,
            portfolio_value=5_500_000,
            peak_value=10_000_000,  # >45% DD
            sector_lookup={"X": "Tech"},
            prices={"X": 50_000},
        )
        assert plan.mode == "halt"
        assert any("Treasury" in w or "Money Market" in w for w in plan.warnings)


# ── Sells ────────────────────────────────────────────────────────────────────

class TestSellLogic:

    def test_sell_only_if_position_exists(self, orch, sector_lookup):
        recs = [{"symbol": "GHOST", "action": "SELL", "confidence": 50, "current_price": 10, "risk_level": "high", "composite_score": -0.2}]
        plan = orch.generate_rebalance_plan(
            recommendations=recs,
            positions=[],  # No position in GHOST
            cash_ngn=5_000_000,
            portfolio_value=10_000_000,
            peak_value=10_000_000,
            sector_lookup=sector_lookup,
        )
        sells = [t for t in plan.trades if t.action == TradeAction.SELL]
        assert len(sells) == 0  # Can't sell what you don't own


# ── Serialization ────────────────────────────────────────────────────────────

class TestSerialization:

    def test_plan_to_dict(self, orch, sample_recs, sample_positions, sector_lookup):
        plan = orch.generate_rebalance_plan(
            recommendations=sample_recs,
            positions=sample_positions,
            cash_ngn=5_000_000,
            portfolio_value=10_000_000,
            peak_value=10_000_000,
            sector_lookup=sector_lookup,
        )
        d = plan.to_dict()
        assert "mode" in d
        assert "trades" in d
        assert "summary" in d
        assert isinstance(d["trades"], list)
        if d["trades"]:
            t = d["trades"][0]
            assert "symbol" in t
            assert "action" in t
            assert "shares" in t

    def test_trade_to_dict(self):
        trade = Trade(
            symbol="TEST", action=TradeAction.BUY, shares=100,
            estimated_value_ngn=50_000, price=500.0,
            reason="test", priority=1,
        )
        d = trade.to_dict()
        assert d["action"] == "BUY"
        assert d["shares"] == 100


# ── Money market recommendation ──────────────────────────────────────────────

class TestMoneyMarketRecommendation:

    def test_excess_cash_recommends_parking(self, orch, sector_lookup):
        # All cash, no positions — should recommend money market
        plan = orch.generate_rebalance_plan(
            recommendations=[],
            positions=[],
            cash_ngn=10_000_000,
            portfolio_value=10_000_000,
            peak_value=10_000_000,
            sector_lookup=sector_lookup,
        )
        assert any("parking" in w.lower() or "treasury" in w.lower() or "money market" in w.lower()
                    for w in plan.warnings)


# ── Trade limits ─────────────────────────────────────────────────────────────

class TestTradeLimits:

    def test_max_trades_respected(self, sector_lookup):
        orch = RebalanceOrchestrator(max_trades_per_rebalance=2)
        # Many BUY recommendations
        recs = [
            {"symbol": f"STOCK{i}", "action": "BUY", "confidence": 80,
             "current_price": 50, "risk_level": "low", "composite_score": 0.2 - i*0.01}
            for i in range(10)
        ]
        plan = orch.generate_rebalance_plan(
            recommendations=recs,
            positions=[],
            cash_ngn=5_000_000,
            portfolio_value=10_000_000,
            peak_value=10_000_000,
            sector_lookup=sector_lookup,
        )
        assert len(plan.trades) <= 2
