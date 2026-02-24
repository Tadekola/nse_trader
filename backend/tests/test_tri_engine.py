"""
Deterministic tests for TRI Computation Engine (Milestone A — PR2).

Covers:
  1. Price-only series (no corporate actions) — adj_close == close, TRI tracks price return
  2. Stock split — adj_factor halves, adj_close is continuous, TRI unaffected by split
  3. Bonus issue — similar to split, adj_factor adjusts by ratio
  4. Cash dividend — TRI increases vs price-only (reinvestment effect)
  5. Combined: split + dividend on same symbol
  6. Multiple dividends on same date (accumulated)
  7. Edge cases: single day, empty prices, zero close guard
  8. Reproducibility: same inputs → same outputs
  9. tri_quality labeling: FULL vs PRICE_ONLY
"""

import os
import sys
import pytest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.tri_engine import TRIEngine, TRI_BASE, AdjustedPriceRow


@pytest.fixture
def engine():
    return TRIEngine()


# ── Helper ───────────────────────────────────────────────────────────

def make_prices(symbol, data):
    """data: list of (date, close) tuples."""
    return [{"ts": d, "close": c} for d, c in data]


# ── 1. Price-only (no actions) ───────────────────────────────────────


class TestPriceOnly:

    def test_adj_close_equals_close(self, engine):
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 102.0),
            (date(2024, 1, 4), 101.0),
        ])
        result = engine.compute("TEST", prices, [])
        for row in result.rows:
            assert row.adj_close == row.close_raw
            assert row.adj_factor == 1.0

    def test_tri_tracks_price_return(self, engine):
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 110.0),  # +10%
            (date(2024, 1, 4), 99.0),   # -10%
        ])
        result = engine.compute("TEST", prices, [])
        assert result.rows[0].tri == TRI_BASE
        assert abs(result.rows[1].tri - TRI_BASE * 1.10) < 0.001
        assert abs(result.rows[2].tri - TRI_BASE * 1.10 * (99.0 / 110.0)) < 0.001

    def test_tri_quality_price_only(self, engine):
        prices = make_prices("TEST", [(date(2024, 1, 2), 100.0)])
        result = engine.compute("TEST", prices, [])
        assert result.tri_quality == "PRICE_ONLY"
        assert result.rows[0].tri_quality == "PRICE_ONLY"

    def test_daily_returns_correct(self, engine):
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 105.0),
        ])
        result = engine.compute("TEST", prices, [])
        assert result.rows[0].daily_return_price is None  # first day
        assert abs(result.rows[1].daily_return_price - 0.05) < 1e-8

    def test_first_day_has_no_return(self, engine):
        prices = make_prices("TEST", [(date(2024, 1, 2), 100.0)])
        result = engine.compute("TEST", prices, [])
        assert result.rows[0].daily_return_price is None
        assert result.rows[0].daily_return_total is None
        assert result.rows[0].tri == TRI_BASE


# ── 2. Stock split ───────────────────────────────────────────────────


class TestStockSplit:

    def test_2_for_1_split(self, engine):
        """
        Day 1: close=200, no split
        Day 2: close=100, 1:2 split (ex_date)
        Day 3: close=105

        After split, adj_factor = 1 * (1/2) = 0.5
        adj_close[1] = 200 * 1.0 = 200
        adj_close[2] = 100 * 0.5 = 50  ← but this is wrong for forward adjustment

        Wait — for FORWARD factor starting at 1.0, when a split occurs
        the post-split prices are naturally lower. The adj_factor adjusts
        the post-split prices to be comparable to pre-split.

        Actually: the standard approach is BACKWARD adjustment:
        - Apply factor retroactively to historical prices.

        Our engine uses FORWARD pass. On the ex_date of a 1:2 split,
        the raw close drops by ~50%. adj_factor *= (1/2) = 0.5.
        adj_close = 100 * 0.5 = 50 — that makes day 2 adj_close = 50 vs day 1 adj_close = 200.
        That's a -75% return which is wrong!

        The correct behavior: on the ex_date, the price halves but value is preserved.
        We need to adjust HISTORICAL prices downward OR adjust FUTURE prices upward.

        Standard practice (Yahoo Finance style): adjust all historical prices backward.
        For a forward-pass engine: on ex_date, we should multiply adj_factor by
        (ratio_to / ratio_from) to INFLATE post-split prices back to pre-split level.

        Let me verify: 1:2 split means 1 old share → 2 new shares.
        Post-split price ≈ pre-split price / 2.
        To make post-split comparable: adj_close = post_close * (2/1) = original level.
        So adj_factor should *= (ratio_to / ratio_from) on the ex_date.

        But our engine does adj_factor *= (ratio_from / ratio_to) = (1/2).
        That's the BACKWARD adjustment convention where you're adjusting
        historical prices DOWN, not future prices UP.

        For our forward-pass: the adj_factor applied to ALL dates should
        ultimately produce a continuous adj_close series. With the backward
        convention, the final adj_close is the actual market price,
        and historical adj_close is adjusted down.

        Let's verify:
        Day 1: adj_factor=1.0, adj_close = 200*1.0 = 200
        Day 2 (split 1:2): adj_factor = 1.0 * (1/2) = 0.5
            But we apply this to Day 2's close: adj_close = 100 * 0.5 = 50
            Day 1 adj_close was 200, Day 2 is 50 — that's -75%, wrong.

        The issue is that in a forward pass, the factor should only apply
        to dates BEFORE the split. In our current code, it applies to
        the ex_date and after.

        The CORRECT forward-pass approach for backward adjustment:
        - Process dates in reverse order
        - Or: change the factor to ratio_to/ratio_from for forward pass

        Actually, I think the engine code has the right idea but the
        direction is inverted. Let me reconsider.

        In a FORWARD pass that produces BACKWARD-adjusted prices:
        - Start with adj_factor = 1.0 at the LATEST date
        - Work backward: when encountering a split, multiply by ratio_to/ratio_from
        - This adjusts old prices down to be comparable to new prices

        But we're iterating forward (earliest to latest). So:
        - We should NOT change the factor going forward
        - Instead, all prices from the BEGINNING until the split get a factor
          that's different from prices AFTER the split.

        The simplest correct approach for a forward-iterating engine:
        - adj_factor starts at product of ALL historical split adjustments
        - As we pass each split ex_date, we "undo" that split from the factor

        OR: just iterate backward.

        Actually, the simplest correct approach that matches industry standard
        (Yahoo/Bloomberg) and iterates forward:
        - Accumulate a CUMULATIVE adjustment factor
        - On each ex_date, the factor changes
        - Apply factor to close to get adj_close
        - The factor is computed such that adj_close is continuous

        For a 1:2 split on day 2:
        - Day 1 close=200, Day 2 close=100 (post-split)
        - We want adj_close to be continuous
        - adj_close[2] should equal adj_close[1] (no economic change)
        - adj_close[1] = 200 * f1
        - adj_close[2] = 100 * f2
        - For continuity: 200 * f1 = 100 * f2 → f2 = 2 * f1

        So on the ex_date, adj_factor should MULTIPLY by (ratio_to / ratio_from) = 2/1 = 2.

        *** This means our engine code has the formula inverted. ***
        It currently does adj_factor *= (ratio_from / ratio_to) but should
        do adj_factor *= (ratio_to / ratio_from).

        Let me write the test to assert correct behavior, then we'll fix the engine.
        """
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 200.0),  # pre-split
            (date(2024, 1, 3), 100.0),  # ex-date: 1:2 split, price halves
            (date(2024, 1, 4), 105.0),  # post-split
        ])
        actions = [
            {"action_type": "STOCK_SPLIT", "ex_date": date(2024, 1, 3),
             "ratio_from": 1, "ratio_to": 2, "amount": None},
        ]
        result = engine.compute("TEST", prices, actions)

        # Before split: adj_factor starts at 1.0
        assert result.rows[0].adj_factor == 1.0
        assert result.rows[0].adj_close == 200.0

        # On ex_date: adj_factor should be 2.0 (ratio_to/ratio_from)
        # adj_close = 100 * 2.0 = 200.0 (continuous!)
        assert result.rows[1].adj_factor == 2.0
        assert abs(result.rows[1].adj_close - 200.0) < 0.01

        # Post-split: adj_close = 105 * 2.0 = 210.0
        assert abs(result.rows[2].adj_close - 210.0) < 0.01

        # Price return on split day should be ~0% (no economic change)
        assert abs(result.rows[1].daily_return_price) < 0.01

        # Price return on day after: (210 - 200) / 200 = 5%
        assert abs(result.rows[2].daily_return_price - 0.05) < 0.001

        # TRI should be unaffected by split (pure accounting)
        assert result.rows[0].tri == TRI_BASE
        assert abs(result.rows[1].tri - TRI_BASE) < 0.5  # ~0% return
        assert abs(result.rows[2].tri - TRI_BASE * 1.05) < 0.5

    def test_split_preserves_tri_continuity(self, engine):
        """Split should not cause a jump in TRI."""
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 1000.0),
            (date(2024, 1, 3), 500.0),   # 1:2 split
            (date(2024, 1, 4), 500.0),   # flat
        ])
        actions = [
            {"action_type": "STOCK_SPLIT", "ex_date": date(2024, 1, 3),
             "ratio_from": 1, "ratio_to": 2, "amount": None},
        ]
        result = engine.compute("TEST", prices, actions)
        # TRI should be flat: 1000→500 is offset by 2x factor
        assert abs(result.rows[1].tri - TRI_BASE) < 0.5
        assert abs(result.rows[2].tri - TRI_BASE) < 0.5


# ── 3. Bonus issue ──────────────────────────────────────────────────


class TestBonusIssue:

    def test_1_for_10_bonus(self, engine):
        """
        1:10 bonus = every 10 shares get 1 bonus share.
        Effective ratio: 10 old → 11 new (ratio_from=10, ratio_to=11).
        Price should drop by ~1/11 ≈ 9.1%.
        """
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 110.0),
            (date(2024, 1, 3), 100.0),   # bonus ex_date
            (date(2024, 1, 4), 102.0),
        ])
        actions = [
            {"action_type": "BONUS_ISSUE", "ex_date": date(2024, 1, 3),
             "ratio_from": 10, "ratio_to": 11, "amount": None},
        ]
        result = engine.compute("TEST", prices, actions)

        # adj_factor on ex_date = 1.0 * (11/10) = 1.1
        assert abs(result.rows[1].adj_factor - 1.1) < 0.001
        # adj_close = 100 * 1.1 = 110.0 (continuous!)
        assert abs(result.rows[1].adj_close - 110.0) < 0.01
        # Price return on bonus day ≈ 0%
        assert abs(result.rows[1].daily_return_price) < 0.01


# ── 4. Cash dividend ────────────────────────────────────────────────


class TestCashDividend:

    def test_dividend_increases_tri_vs_price_only(self, engine):
        """TRI with dividend should exceed price-only TRI."""
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 98.0),    # ex-dividend: price drops ~2
            (date(2024, 1, 4), 99.0),
        ])
        actions_with_div = [
            {"action_type": "CASH_DIVIDEND", "ex_date": date(2024, 1, 3),
             "amount": 2.0, "ratio_from": None, "ratio_to": None},
        ]

        result_with_div = engine.compute("TEST", prices, actions_with_div)
        result_price_only = engine.compute("TEST", prices, [])

        # With dividend, TRI on day 2 should be higher than price-only
        tri_with = result_with_div.rows[1].tri
        tri_without = result_price_only.rows[1].tri
        assert tri_with > tri_without

        # The difference should be approximately the dividend yield
        # div_yield = 2.0 / 100.0 = 2%, so TRI_with ≈ TRI_without + 2%*TRI_BASE
        expected_diff = TRI_BASE * (2.0 / 100.0)
        actual_diff = tri_with - tri_without
        assert abs(actual_diff - expected_diff) < 0.1

    def test_dividend_tri_quality_full(self, engine):
        prices = make_prices("TEST", [(date(2024, 1, 2), 100.0)])
        actions = [
            {"action_type": "CASH_DIVIDEND", "ex_date": date(2024, 1, 5),
             "amount": 5.0, "ratio_from": None, "ratio_to": None},
        ]
        result = engine.compute("TEST", prices, actions)
        assert result.tri_quality == "FULL"

    def test_dividend_yield_calculation(self, engine):
        """Verify exact math for dividend reinvestment."""
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 200.0),
            (date(2024, 1, 3), 195.0),  # ex-div, price drops 5
        ])
        actions = [
            {"action_type": "CASH_DIVIDEND", "ex_date": date(2024, 1, 3),
             "amount": 10.0, "ratio_from": None, "ratio_to": None},
        ]
        result = engine.compute("TEST", prices, actions)

        # Price return = (195 - 200) / 200 = -2.5%
        assert abs(result.rows[1].daily_return_price - (-0.025)) < 1e-8

        # Dividend yield = 10 * 1.0 / 200 = 5%
        # Total return = -2.5% + 5% = 2.5%
        assert abs(result.rows[1].daily_return_total - 0.025) < 1e-8

        # TRI = 1000 * 1.025 = 1025
        assert abs(result.rows[1].tri - 1025.0) < 0.01


# ── 5. Combined: split + dividend ───────────────────────────────────


class TestCombined:

    def test_split_then_dividend(self, engine):
        """
        Day 1: close=200
        Day 2: close=100, 1:2 split
        Day 3: close=98, dividend=1.0 NGN (post-split per-share)
        """
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 200.0),
            (date(2024, 1, 3), 100.0),  # split
            (date(2024, 1, 4), 98.0),   # dividend
        ])
        actions = [
            {"action_type": "STOCK_SPLIT", "ex_date": date(2024, 1, 3),
             "ratio_from": 1, "ratio_to": 2, "amount": None},
            {"action_type": "CASH_DIVIDEND", "ex_date": date(2024, 1, 4),
             "amount": 1.0, "ratio_from": None, "ratio_to": None},
        ]
        result = engine.compute("TEST", prices, actions)

        # Day 2: split, adj_factor = 2.0, adj_close = 200.0
        assert abs(result.rows[1].adj_close - 200.0) < 0.01

        # Day 3: adj_close = 98 * 2.0 = 196.0
        assert abs(result.rows[2].adj_close - 196.0) < 0.01

        # Price return day 3: (196 - 200) / 200 = -2%
        assert abs(result.rows[2].daily_return_price - (-0.02)) < 0.001

        # Dividend yield: 1.0 * 2.0 / 200.0 = 1%
        # Total return: -2% + 1% = -1%
        assert abs(result.rows[2].daily_return_total - (-0.01)) < 0.001

        assert result.tri_quality == "FULL"
        assert result.splits_applied == 1
        assert result.dividends_applied == 1


# ── 6. Multiple dividends same date ─────────────────────────────────


class TestMultipleDividends:

    def test_two_dividends_same_date_accumulated(self, engine):
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 95.0),
        ])
        actions = [
            {"action_type": "CASH_DIVIDEND", "ex_date": date(2024, 1, 3),
             "amount": 3.0, "ratio_from": None, "ratio_to": None},
            {"action_type": "CASH_DIVIDEND", "ex_date": date(2024, 1, 3),
             "amount": 2.0, "ratio_from": None, "ratio_to": None},
        ]
        result = engine.compute("TEST", prices, actions)

        # Total dividend = 5.0, yield = 5/100 = 5%
        # Price return = (95-100)/100 = -5%
        # Total return = 0%
        assert abs(result.rows[1].daily_return_total) < 1e-8
        assert abs(result.rows[1].tri - TRI_BASE) < 0.01


# ── 7. Edge cases ───────────────────────────────────────────────────


class TestEdgeCases:

    def test_empty_prices(self, engine):
        result = engine.compute("TEST", [], [])
        assert len(result.rows) == 0
        assert "No price data" in result.warnings[0]

    def test_single_day(self, engine):
        prices = make_prices("TEST", [(date(2024, 1, 2), 100.0)])
        result = engine.compute("TEST", prices, [])
        assert len(result.rows) == 1
        assert result.rows[0].tri == TRI_BASE
        assert result.rows[0].daily_return_price is None

    def test_unsorted_prices_sorted_automatically(self, engine):
        prices = make_prices("TEST", [
            (date(2024, 1, 4), 103.0),
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 102.0),
        ])
        result = engine.compute("TEST", prices, [])
        assert result.rows[0].ts == date(2024, 1, 2)
        assert result.rows[1].ts == date(2024, 1, 3)
        assert result.rows[2].ts == date(2024, 1, 4)

    def test_action_on_date_without_price(self, engine):
        """Action on a non-trading date should be ignored gracefully."""
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 4), 102.0),  # skip Jan 3
        ])
        actions = [
            {"action_type": "CASH_DIVIDEND", "ex_date": date(2024, 1, 3),
             "amount": 5.0, "ratio_from": None, "ratio_to": None},
        ]
        result = engine.compute("TEST", prices, actions)
        # Dividend on Jan 3 is not applied (no price on that date)
        assert result.dividends_applied == 0
        # TRI should just track price return
        assert result.rows[1].daily_return_total == result.rows[1].daily_return_price


# ── 8. Reproducibility ──────────────────────────────────────────────


class TestReproducibility:

    def test_identical_inputs_produce_identical_outputs(self, engine):
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 98.0),
            (date(2024, 1, 4), 102.0),
        ])
        actions = [
            {"action_type": "CASH_DIVIDEND", "ex_date": date(2024, 1, 3),
             "amount": 2.0, "ratio_from": None, "ratio_to": None},
        ]

        r1 = engine.compute("TEST", prices, actions)
        r2 = engine.compute("TEST", prices, actions)

        for row1, row2 in zip(r1.rows, r2.rows):
            assert row1.to_dict() == row2.to_dict()


# ── 9. to_dict serialization ────────────────────────────────────────


class TestSerialization:

    def test_adjusted_price_row_to_dict(self, engine):
        prices = make_prices("TEST", [
            (date(2024, 1, 2), 100.0),
            (date(2024, 1, 3), 105.0),
        ])
        result = engine.compute("TEST", prices, [])
        d = result.rows[1].to_dict()

        assert d["symbol"] == "TEST"
        assert d["ts"] == date(2024, 1, 3)
        assert d["close_raw"] == 105.0
        assert d["adj_factor"] == 1.0
        assert d["adj_close"] == 105.0
        assert isinstance(d["daily_return_price"], float)
        assert d["tri_quality"] == "PRICE_ONLY"
