"""
Total Return Index (TRI) Computation Engine (Milestone A — PR2).

Computes two daily series per symbol:
  1. Adjusted Close — handles splits and bonus issues via a cumulative
     adjustment factor applied backwards from the most recent price.
  2. Total Return Index (TRI) — reinvests dividends into the adjusted
     price series, producing a wealth index (base = 1000.0 on day 0).

Algorithm (forward-fill, single pass over sorted dates):

    adj_factor[0] = 1.0 (start from earliest date, work forward)
    For each date t:
        # Check for split/bonus on this ex_date
        if split or bonus on t:
            adj_factor[t] = adj_factor[t-1] * (ratio_from / ratio_to)
        else:
            adj_factor[t] = adj_factor[t-1]

        adj_close[t] = close[t] * adj_factor[t]

        # TRI: reinvest dividends
        if dividend on t (ex_date):
            dividend_yield = dividend_amount * adj_factor[t] / adj_close[t-1]
            tri[t] = tri[t-1] * (1 + price_return + dividend_yield)
        else:
            tri[t] = tri[t-1] * (adj_close[t] / adj_close[t-1])

    daily_return_price[t] = adj_close[t] / adj_close[t-1] - 1
    daily_return_total[t] = tri[t] / tri[t-1] - 1

Design decisions:
  - Forward adjustment factor: factor starts at 1.0 on the earliest date
    and multiplicatively adjusts when events occur. This means historical
    adj_close values change when a new split occurs — standard practice.
  - Dividend reinvestment at ex_date close price (same-day reinvestment).
  - tri_quality = "FULL" when dividends exist for the symbol,
    "PRICE_ONLY" when no dividends found in the corporate_actions table.
  - The engine is pure computation — no DB access. Callers pass in data.

Usage::

    engine = TRIEngine()
    results = engine.compute(
        prices=[{"ts": date(2024,1,2), "close": 350.0}, ...],
        actions=[{"action_type": "CASH_DIVIDEND", "ex_date": ..., "amount": 20}, ...],
    )
    # results: list of AdjustedPriceRow
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TRI_BASE = 1000.0


@dataclass
class AdjustedPriceRow:
    """A single row of the adjusted price / TRI output."""
    symbol: str
    ts: date
    close_raw: float
    adj_factor: float
    adj_close: float
    tri: float
    daily_return_price: Optional[float]
    daily_return_total: Optional[float]
    tri_quality: str  # "FULL" or "PRICE_ONLY"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "ts": self.ts,
            "close_raw": self.close_raw,
            "adj_factor": round(self.adj_factor, 10),
            "adj_close": round(self.adj_close, 6),
            "tri": round(self.tri, 6),
            "daily_return_price": (
                round(self.daily_return_price, 8) if self.daily_return_price is not None else None
            ),
            "daily_return_total": (
                round(self.daily_return_total, 8) if self.daily_return_total is not None else None
            ),
            "tri_quality": self.tri_quality,
        }


@dataclass
class TRIComputeResult:
    """Full result of a TRI computation for one symbol."""
    symbol: str
    rows: List[AdjustedPriceRow] = field(default_factory=list)
    tri_quality: str = "PRICE_ONLY"
    splits_applied: int = 0
    bonuses_applied: int = 0
    dividends_applied: int = 0
    warnings: List[str] = field(default_factory=list)


class TRIEngine:
    """
    Pure computation engine for adjusted close + TRI.

    Stateless — all data passed in, no DB access.
    """

    def compute(
        self,
        symbol: str,
        prices: List[Dict[str, Any]],
        actions: List[Dict[str, Any]],
    ) -> TRIComputeResult:
        """
        Compute adjusted close + TRI for a symbol.

        Args:
            symbol: Stock ticker (e.g. "DANGCEM")
            prices: List of dicts with keys "ts" (date) and "close" (float),
                    sorted by ts ascending.
            actions: List of corporate action dicts with keys:
                     action_type, ex_date, amount, ratio_from, ratio_to

        Returns:
            TRIComputeResult with rows and metadata.
        """
        result = TRIComputeResult(symbol=symbol)

        if not prices:
            result.warnings.append("No price data provided")
            return result

        # Sort prices by date ascending
        prices_sorted = sorted(prices, key=lambda p: p["ts"])

        # Index actions by ex_date for O(1) lookup
        dividends_by_date: Dict[date, float] = {}
        splits_by_date: Dict[date, tuple] = {}  # (ratio_from, ratio_to)

        has_dividends = False
        for a in actions:
            ex = a["ex_date"]
            atype = a["action_type"]
            if atype == "CASH_DIVIDEND":
                amount = a.get("amount", 0) or 0
                if amount > 0:
                    # Accumulate if multiple dividends on same date
                    dividends_by_date[ex] = dividends_by_date.get(ex, 0) + amount
                    has_dividends = True
            elif atype in ("STOCK_SPLIT", "BONUS_ISSUE"):
                rf = a.get("ratio_from", 1) or 1
                rt = a.get("ratio_to", 1) or 1
                if rf > 0 and rt > 0 and rf != rt:
                    splits_by_date[ex] = (rf, rt)

        tri_quality = "FULL" if has_dividends else "PRICE_ONLY"
        result.tri_quality = tri_quality

        # ── Forward pass ─────────────────────────────────────────────

        rows: List[AdjustedPriceRow] = []
        prev_adj_close: Optional[float] = None
        prev_tri: Optional[float] = None
        adj_factor = 1.0

        for price in prices_sorted:
            ts = price["ts"]
            close_raw = float(price["close"])

            # Apply split/bonus adjustment
            if ts in splits_by_date:
                rf, rt = splits_by_date[ts]
                # After a split, each old share becomes (rt/rf) new shares,
                # so the post-split price drops by (rf/rt). To keep adj_close
                # continuous, we INFLATE post-split prices by (rt/rf).
                adj_factor *= (rt / rf)
                if rt > rf:
                    result.splits_applied += 1
                    logger.debug("Split on %s: %d→%d, adj_factor=%.6f", ts, rf, rt, adj_factor)
                else:
                    result.bonuses_applied += 1
                    logger.debug("Bonus on %s: %d→%d, adj_factor=%.6f", ts, rf, rt, adj_factor)

            adj_close = close_raw * adj_factor

            # Compute TRI
            if prev_adj_close is None:
                # First day: base TRI
                tri = TRI_BASE
                daily_return_price = None
                daily_return_total = None
            else:
                # Price return
                daily_return_price = (adj_close / prev_adj_close) - 1.0

                # Dividend reinvestment
                div_amount = dividends_by_date.get(ts, 0)
                if div_amount > 0:
                    # Dividend yield relative to previous day's adjusted close
                    # The dividend amount is per-share in original terms,
                    # so we adjust it by the current adj_factor.
                    adjusted_dividend = div_amount * adj_factor
                    dividend_yield = adjusted_dividend / prev_adj_close
                    daily_return_total = daily_return_price + dividend_yield
                    result.dividends_applied += 1
                    logger.debug(
                        "Dividend on %s: %.2f NGN, adj_div=%.4f, yield=%.4f%%",
                        ts, div_amount, adjusted_dividend, dividend_yield * 100,
                    )
                else:
                    daily_return_total = daily_return_price

                tri = prev_tri * (1.0 + daily_return_total)

            row = AdjustedPriceRow(
                symbol=symbol,
                ts=ts,
                close_raw=close_raw,
                adj_factor=adj_factor,
                adj_close=adj_close,
                tri=tri,
                daily_return_price=daily_return_price,
                daily_return_total=daily_return_total,
                tri_quality=tri_quality,
            )
            rows.append(row)

            prev_adj_close = adj_close
            prev_tri = tri

        result.rows = rows
        return result
