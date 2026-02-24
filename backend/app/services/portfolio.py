"""
Portfolio Service — holdings computation + transaction validation (Milestone B — PR2).

Core logic:
  1. Transaction validation (type-specific rules)
  2. Holdings computation as-of any date (replay transactions)
  3. Cash balance tracking (from CASH_IN/OUT + trade proceeds + dividends - fees)
  4. Portfolio valuation using AdjustedPrice (preferred) or raw OHLCV close

Design:
  - Pure computation engine — no DB access. Callers pass in data.
  - Deterministic: same transactions + same prices → same holdings + valuation.
  - Holdings are REPLAYED from transactions, not cached. Caching is a
    separate optimization layer (portfolio_positions table, future PR).

Usage::

    service = PortfolioService()
    holdings = service.compute_holdings(transactions, as_of=date(2024, 6, 15))
    valuation = service.compute_valuation(holdings, prices)
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

VALID_TX_TYPES = {"BUY", "SELL", "DIVIDEND", "CASH_IN", "CASH_OUT", "FEE"}
SECURITY_TX_TYPES = {"BUY", "SELL"}
CASH_TX_TYPES = {"DIVIDEND", "CASH_IN", "CASH_OUT", "FEE"}


@dataclass
class TxValidationError:
    field: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"field": self.field, "message": self.message}


@dataclass
class Holding:
    """A single stock holding as-of a date."""
    symbol: str
    quantity: float
    avg_cost_ngn: float  # weighted average cost per share
    total_cost_ngn: float  # total cost basis

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": round(self.quantity, 6),
            "avg_cost_ngn": round(self.avg_cost_ngn, 4),
            "total_cost_ngn": round(self.total_cost_ngn, 4),
        }


@dataclass
class PortfolioSnapshot:
    """Portfolio state as-of a date."""
    as_of: date
    holdings: Dict[str, Holding]  # symbol -> Holding
    cash_ngn: float
    total_invested_ngn: float  # sum of all CASH_IN minus CASH_OUT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "holdings": {s: h.to_dict() for s, h in self.holdings.items()},
            "cash_ngn": round(self.cash_ngn, 4),
            "total_invested_ngn": round(self.total_invested_ngn, 4),
            "symbols": sorted(self.holdings.keys()),
            "num_positions": len(self.holdings),
        }


@dataclass
class Valuation:
    """Portfolio valuation at a point in time."""
    as_of: date
    holdings_value_ngn: float  # market value of all stock holdings
    cash_ngn: float
    total_value_ngn: float  # holdings + cash
    positions: List[Dict[str, Any]]  # per-position detail
    data_quality: str  # "FULL", "PARTIAL", "PRICE_MISSING"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "holdings_value_ngn": round(self.holdings_value_ngn, 4),
            "cash_ngn": round(self.cash_ngn, 4),
            "total_value_ngn": round(self.total_value_ngn, 4),
            "positions": self.positions,
            "data_quality": self.data_quality,
        }


class PortfolioService:
    """
    Pure computation engine for portfolio holdings and valuation.

    Stateless — all data passed in, no DB access.
    """

    # ── Transaction Validation ────────────────────────────────────────

    @staticmethod
    def validate_transaction(tx: Dict[str, Any]) -> List[TxValidationError]:
        """Validate a single transaction dict. Returns list of errors (empty = valid)."""
        errors: List[TxValidationError] = []

        tx_type = tx.get("tx_type", "").upper()
        if tx_type not in VALID_TX_TYPES:
            errors.append(TxValidationError("tx_type",
                f"invalid: '{tx_type}' (expected one of {sorted(VALID_TX_TYPES)})"))
            return errors  # can't validate further without type

        ts = tx.get("ts")
        if ts is None:
            errors.append(TxValidationError("ts", "missing"))

        # Security transactions require symbol + quantity + price
        if tx_type in SECURITY_TX_TYPES:
            if not tx.get("symbol"):
                errors.append(TxValidationError("symbol",
                    f"{tx_type} requires symbol"))
            qty = tx.get("quantity")
            if qty is None or qty <= 0:
                errors.append(TxValidationError("quantity",
                    f"{tx_type} requires positive quantity"))
            price = tx.get("price_ngn")
            if price is None or price <= 0:
                errors.append(TxValidationError("price_ngn",
                    f"{tx_type} requires positive price_ngn"))

        # DIVIDEND requires symbol + amount
        if tx_type == "DIVIDEND":
            if not tx.get("symbol"):
                errors.append(TxValidationError("symbol",
                    "DIVIDEND requires symbol"))
            amount = tx.get("amount_ngn")
            if amount is None or amount <= 0:
                errors.append(TxValidationError("amount_ngn",
                    "DIVIDEND requires positive amount_ngn"))

        # CASH_IN/OUT require amount
        if tx_type in ("CASH_IN", "CASH_OUT"):
            amount = tx.get("amount_ngn")
            if amount is None or amount <= 0:
                errors.append(TxValidationError("amount_ngn",
                    f"{tx_type} requires positive amount_ngn"))

        # FEE requires amount
        if tx_type == "FEE":
            amount = tx.get("amount_ngn")
            if amount is None or amount <= 0:
                errors.append(TxValidationError("amount_ngn",
                    "FEE requires positive amount_ngn"))

        return errors

    # ── Holdings Computation ──────────────────────────────────────────

    def compute_holdings(
        self,
        transactions: List[Dict[str, Any]],
        as_of: Optional[date] = None,
    ) -> PortfolioSnapshot:
        """
        Replay transactions to compute holdings as-of a date.

        Transactions should be dicts with keys:
            ts, tx_type, symbol (optional), quantity (optional),
            price_ngn (optional), amount_ngn, fees_ngn

        Uses weighted average cost for cost basis tracking.
        """
        # Sort by date, then by a stable order
        sorted_txs = sorted(transactions, key=lambda t: t["ts"])

        holdings: Dict[str, Holding] = {}
        cash_ngn = 0.0
        total_invested = 0.0

        for tx in sorted_txs:
            tx_date = tx["ts"]
            if as_of is not None and tx_date > as_of:
                break

            tx_type = tx["tx_type"].upper()
            symbol = (tx.get("symbol") or "").upper()
            quantity = tx.get("quantity") or 0.0
            price = tx.get("price_ngn") or 0.0
            amount = tx.get("amount_ngn") or 0.0
            fees = tx.get("fees_ngn") or 0.0

            if tx_type == "BUY":
                cost = quantity * price + fees
                if symbol in holdings:
                    h = holdings[symbol]
                    new_qty = h.quantity + quantity
                    new_total_cost = h.total_cost_ngn + cost
                    h.quantity = new_qty
                    h.total_cost_ngn = new_total_cost
                    h.avg_cost_ngn = new_total_cost / new_qty if new_qty > 0 else 0
                else:
                    holdings[symbol] = Holding(
                        symbol=symbol,
                        quantity=quantity,
                        avg_cost_ngn=cost / quantity if quantity > 0 else 0,
                        total_cost_ngn=cost,
                    )
                cash_ngn -= cost

            elif tx_type == "SELL":
                proceeds = quantity * price - fees
                if symbol in holdings:
                    h = holdings[symbol]
                    # Reduce cost basis proportionally
                    if h.quantity > 0:
                        cost_fraction = quantity / h.quantity
                        h.total_cost_ngn -= h.total_cost_ngn * cost_fraction
                    h.quantity -= quantity
                    if h.quantity <= 1e-9:
                        # Position fully closed
                        del holdings[symbol]
                cash_ngn += proceeds

            elif tx_type == "DIVIDEND":
                cash_ngn += amount

            elif tx_type == "CASH_IN":
                cash_ngn += amount
                total_invested += amount

            elif tx_type == "CASH_OUT":
                cash_ngn -= amount
                total_invested -= amount

            elif tx_type == "FEE":
                cash_ngn -= amount

        return PortfolioSnapshot(
            as_of=as_of or date.today(),
            holdings=holdings,
            cash_ngn=cash_ngn,
            total_invested_ngn=total_invested,
        )

    # ── Valuation ─────────────────────────────────────────────────────

    def compute_valuation(
        self,
        snapshot: PortfolioSnapshot,
        prices: Dict[str, float],  # symbol -> current price (adj_close preferred)
    ) -> Valuation:
        """
        Value a portfolio snapshot using provided prices.

        Args:
            snapshot: PortfolioSnapshot from compute_holdings
            prices: dict mapping symbol -> price in NGN

        Returns:
            Valuation with per-position detail and quality flag
        """
        positions: List[Dict[str, Any]] = []
        total_holdings_value = 0.0
        missing_prices = 0

        for symbol, holding in sorted(snapshot.holdings.items()):
            price = prices.get(symbol)
            if price is not None:
                market_value = holding.quantity * price
                gain_loss = market_value - holding.total_cost_ngn
                gain_pct = (gain_loss / holding.total_cost_ngn * 100
                           if holding.total_cost_ngn > 0 else 0.0)
            else:
                market_value = 0.0
                gain_loss = 0.0
                gain_pct = 0.0
                missing_prices += 1

            positions.append({
                "symbol": symbol,
                "quantity": round(holding.quantity, 6),
                "avg_cost_ngn": round(holding.avg_cost_ngn, 4),
                "total_cost_ngn": round(holding.total_cost_ngn, 4),
                "price_ngn": round(price, 4) if price is not None else None,
                "market_value_ngn": round(market_value, 4),
                "gain_loss_ngn": round(gain_loss, 4),
                "gain_loss_pct": round(gain_pct, 2),
                "price_available": price is not None,
            })
            total_holdings_value += market_value

        # Quality flag
        if missing_prices == 0:
            quality = "FULL"
        elif missing_prices < len(snapshot.holdings):
            quality = "PARTIAL"
        else:
            quality = "PRICE_MISSING"

        return Valuation(
            as_of=snapshot.as_of,
            holdings_value_ngn=total_holdings_value,
            cash_ngn=snapshot.cash_ngn,
            total_value_ngn=total_holdings_value + snapshot.cash_ngn,
            positions=positions,
            data_quality=quality,
        )

    # ── Daily Value Series ────────────────────────────────────────────

    def compute_daily_values(
        self,
        transactions: List[Dict[str, Any]],
        price_series: Dict[str, Dict[date, float]],  # symbol -> {date -> price}
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """
        Compute daily portfolio value series for a date range.

        Returns list of {date, value_ngn, cash_ngn, holdings_ngn} for each
        trading day in range where at least some prices exist.

        This is used by the Performance Engine for return calculations.
        """
        from datetime import timedelta

        # Collect all dates in range where we have any price data
        all_dates = set()
        for sym_prices in price_series.values():
            for d in sym_prices:
                if start_date <= d <= end_date:
                    all_dates.add(d)
        all_dates = sorted(all_dates)

        if not all_dates:
            return []

        daily_values: List[Dict[str, Any]] = []

        for d in all_dates:
            snapshot = self.compute_holdings(transactions, as_of=d)
            prices_today = {}
            for sym in snapshot.holdings:
                if sym in price_series and d in price_series[sym]:
                    prices_today[sym] = price_series[sym][d]

            val = self.compute_valuation(snapshot, prices_today)
            daily_values.append({
                "date": d,
                "value_ngn": val.total_value_ngn,
                "cash_ngn": val.cash_ngn,
                "holdings_ngn": val.holdings_value_ngn,
                "data_quality": val.data_quality,
            })

        return daily_values
