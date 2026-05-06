"""Tests for TransactionCosts + SlippageModel and backtester cost integration."""

import pytest
import numpy as np
import pandas as pd
from app.services.backtester import TransactionCosts, SlippageModel, BacktestConfig


# ── TransactionCosts unit tests ───────────────────────────────────────────────

class TestTransactionCosts:

    def test_default_one_way_cost(self):
        tc = TransactionCosts()
        # brokerage 1.50 + SEC 0.30 + CSCS 0.30 + stamp 0.075 + VAT(1.50*7.5/100=0.1125)
        expected = 1.50 + 0.30 + 0.30 + 0.075 + 0.1125
        assert abs(tc.one_way_pct - expected) < 0.001

    def test_round_trip_is_double_one_way(self):
        tc = TransactionCosts()
        assert abs(tc.round_trip_pct - tc.one_way_pct * 2) < 0.0001

    def test_apply_buy_cost_increases_price(self):
        tc = TransactionCosts()
        price = 100.0
        adj = tc.apply_buy_cost(price)
        assert adj > price
        expected = price * (1 + tc.one_way_pct / 100)
        assert abs(adj - expected) < 0.01

    def test_apply_sell_cost_decreases_price(self):
        tc = TransactionCosts()
        price = 100.0
        adj = tc.apply_sell_cost(price)
        assert adj < price
        expected = price * (1 - tc.one_way_pct / 100)
        assert abs(adj - expected) < 0.01

    def test_disabled_costs_no_change(self):
        tc = TransactionCosts(enabled=False)
        assert tc.apply_buy_cost(100.0) == 100.0
        assert tc.apply_sell_cost(100.0) == 100.0

    def test_round_trip_return_impact(self):
        """A stock that doesn't move should lose approximately round_trip_pct."""
        tc = TransactionCosts(slippage=SlippageModel(enabled=False))
        entry = 100.0
        exit_price = 100.0  # flat
        adj_entry = tc.apply_buy_cost(entry, 0.0)
        adj_exit = tc.apply_sell_cost(exit_price, 0.0)
        net_return_pct = (adj_exit - adj_entry) / adj_entry * 100
        # Net return should be negative, approximately -round_trip_pct
        assert net_return_pct < 0
        # The exact loss is slightly less than round_trip_pct due to compounding
        assert abs(net_return_pct + tc.round_trip_pct) < 0.5

    def test_custom_brokerage(self):
        tc = TransactionCosts(brokerage_pct=0.50)
        # Lower brokerage → lower total cost
        default = TransactionCosts()
        assert tc.one_way_pct < default.one_way_pct

    def test_zero_costs(self):
        tc = TransactionCosts(
            brokerage_pct=0, sec_fee_pct=0, cscs_fee_pct=0,
            stamp_duty_pct=0, vat_on_commission_pct=0,
        )
        assert tc.one_way_pct == 0.0
        assert tc.apply_buy_cost(100.0, 0.0) == 100.0
        assert tc.apply_sell_cost(100.0, 0.0) == 100.0

    def test_slippage_adds_to_cost(self):
        tc = TransactionCosts()
        no_slip = tc.apply_buy_cost(100.0, 0.0)
        with_slip = tc.apply_buy_cost(100.0, 0.5)
        assert with_slip > no_slip


# ── BacktestConfig integration ────────────────────────────────────────────────

class TestBacktestConfigCosts:

    def test_default_config_has_costs_enabled(self):
        config = BacktestConfig()
        assert config.costs.enabled is True
        assert config.costs.one_way_pct > 0

    def test_config_with_disabled_costs(self):
        config = BacktestConfig(costs=TransactionCosts(enabled=False))
        assert config.costs.enabled is False

    def test_config_to_dict_includes_costs(self):
        from app.services.backtester import BacktestResults
        config = BacktestConfig()
        results = BacktestResults(config=config, snapshots=[])
        d = results.to_dict()
        assert "transaction_costs" in d
        assert d["transaction_costs"]["enabled"] is True
        assert d["transaction_costs"]["one_way_pct"] > 0
        assert d["transaction_costs"]["round_trip_pct"] > 0


# ── Cost impact on returns ────────────────────────────────────────────────────

class TestCostImpactOnReturns:

    def test_positive_gross_return_reduced_by_costs(self):
        """A 5% gross return should be reduced by ~4.58% round-trip costs."""
        tc = TransactionCosts(slippage=SlippageModel(enabled=False))
        entry = 100.0
        exit_price = 105.0  # 5% gross return

        gross_ret = (exit_price - entry) / entry * 100
        assert abs(gross_ret - 5.0) < 0.01

        adj_entry = tc.apply_buy_cost(entry, 0.0)
        adj_exit = tc.apply_sell_cost(exit_price, 0.0)
        net_ret = (adj_exit - adj_entry) / adj_entry * 100

        assert net_ret < gross_ret
        assert net_ret > 0  # 5% gross should still be positive after ~4.58% costs

    def test_small_gain_becomes_loss_with_costs(self):
        """A 2% gross return should become a loss after ~4.58% round-trip costs."""
        tc = TransactionCosts(slippage=SlippageModel(enabled=False))
        entry = 100.0
        exit_price = 102.0  # 2% gross return

        adj_entry = tc.apply_buy_cost(entry, 0.0)
        adj_exit = tc.apply_sell_cost(exit_price, 0.0)
        net_ret = (adj_exit - adj_entry) / adj_entry * 100

        assert net_ret < 0  # Costs exceed the gain

    def test_no_costs_preserves_gross_return(self):
        tc = TransactionCosts(enabled=False)
        entry = 100.0
        exit_price = 110.0

        adj_entry = tc.apply_buy_cost(entry, 0.0)
        adj_exit = tc.apply_sell_cost(exit_price, 0.0)
        net_ret = (adj_exit - adj_entry) / adj_entry * 100
        gross_ret = (exit_price - entry) / entry * 100

        assert abs(net_ret - gross_ret) < 0.001


# ── SlippageModel tests ───────────────────────────────────────────────────────

class TestSlippageModel:

    def _make_ohlcv(self, n=30, avg_volume=100_000, spread_pct=2.0):
        """Create synthetic OHLCV data."""
        dates = pd.date_range("2025-01-01", periods=n, freq="B")
        close = 100.0 + np.random.randn(n).cumsum() * 0.5
        close = np.maximum(close, 10)  # floor
        half_spread = close * (spread_pct / 100) / 2
        return pd.DataFrame({
            "Open": close + np.random.randn(n) * 0.1,
            "High": close + half_spread,
            "Low": close - half_spread,
            "Close": close,
            "Volume": np.random.poisson(avg_volume, n).astype(float),
        }, index=dates)

    def test_disabled_returns_zero(self):
        sm = SlippageModel(enabled=False)
        assert sm.estimate_slippage_pct() == 0.0

    def test_no_data_returns_default(self):
        sm = SlippageModel()
        assert sm.estimate_slippage_pct(price_data=None) == 0.5

    def test_insufficient_data_returns_default(self):
        sm = SlippageModel()
        short_df = self._make_ohlcv(n=3)
        assert sm.estimate_slippage_pct(price_data=short_df) == 0.5

    def test_high_volume_less_slippage(self):
        sm = SlippageModel()
        high_vol = self._make_ohlcv(avg_volume=10_000_000)
        low_vol = self._make_ohlcv(avg_volume=1_000)
        slip_high = sm.estimate_slippage_pct(price_data=high_vol)
        slip_low = sm.estimate_slippage_pct(price_data=low_vol)
        assert slip_high < slip_low

    def test_wider_spread_more_slippage(self):
        sm = SlippageModel()
        narrow = self._make_ohlcv(spread_pct=0.5, avg_volume=100_000)
        wide = self._make_ohlcv(spread_pct=5.0, avg_volume=100_000)
        slip_narrow = sm.estimate_slippage_pct(price_data=narrow)
        slip_wide = sm.estimate_slippage_pct(price_data=wide)
        assert slip_wide > slip_narrow

    def test_larger_order_more_impact(self):
        sm = SlippageModel()
        df = self._make_ohlcv(avg_volume=10_000)
        small = sm.estimate_slippage_pct(price_data=df, order_shares=100)
        large = sm.estimate_slippage_pct(price_data=df, order_shares=9_000)
        assert large > small

    def test_slippage_always_positive(self):
        sm = SlippageModel()
        df = self._make_ohlcv()
        slip = sm.estimate_slippage_pct(price_data=df)
        assert slip > 0
