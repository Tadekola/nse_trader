"""
Portfolio Rebalance Orchestrator.

Connects recommendations → risk manager → concrete trade list.
Turns the advisory system into an actionable portfolio manager.

Design:
  - Pure computation engine — no DB access. Callers pass in portfolio state.
  - Integrates PortfolioRiskManager for position sizing + limits.
  - Produces a prioritised trade list with BUY / SELL / TRIM / RAISE_CASH actions.
  - Defensive mode: when drawdown breaker triggers, actively sells weakest
    holdings and parks cash (money-market recommendation).

Usage::

    orch = RebalanceOrchestrator()
    plan = orch.generate_rebalance_plan(
        recommendations=[...],
        positions=[...],
        cash_ngn=2_000_000,
        portfolio_value=10_000_000,
        peak_value=10_500_000,
        sector_lookup={"GTCO": "Financial Services", ...},
    )
    for trade in plan.trades:
        print(trade)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.services.portfolio_risk import PortfolioRiskManager, RiskLimits

logger = logging.getLogger(__name__)


# ── Trade types ──────────────────────────────────────────────────────────────

class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    TRIM = "TRIM"            # Reduce an oversized position
    RAISE_CASH = "RAISE_CASH"  # Sell weakest to raise cash reserve


# ── Output dataclasses ───────────────────────────────────────────────────────

@dataclass
class Trade:
    """A single actionable trade."""
    symbol: str
    action: TradeAction
    shares: int
    estimated_value_ngn: float
    price: float
    reason: str
    priority: int = 0  # Lower = higher priority (execute first)
    confidence: float = 0.0
    risk_level: str = "moderate"
    sector: str = "Unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action.value,
            "shares": self.shares,
            "estimated_value_ngn": round(self.estimated_value_ngn, 2),
            "price": round(self.price, 2),
            "reason": self.reason,
            "priority": self.priority,
            "confidence": round(self.confidence, 1),
            "risk_level": self.risk_level,
            "sector": self.sector,
        }


@dataclass
class RebalancePlan:
    """Complete rebalance plan with trades and diagnostics."""
    trades: List[Trade] = field(default_factory=list)
    mode: str = "normal"  # normal, defensive, halt

    # Pre-rebalance state
    portfolio_value: float = 0.0
    cash_before: float = 0.0
    cash_after_estimate: float = 0.0
    drawdown_pct: float = 0.0

    # Diagnostics
    buys_count: int = 0
    sells_count: int = 0
    trims_count: int = 0
    raise_cash_count: int = 0
    total_buy_value: float = 0.0
    total_sell_value: float = 0.0
    skipped_symbols: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "portfolio_value": round(self.portfolio_value, 2),
            "drawdown_pct": round(self.drawdown_pct, 2),
            "cash_before": round(self.cash_before, 2),
            "cash_after_estimate": round(self.cash_after_estimate, 2),
            "summary": {
                "buys": self.buys_count,
                "sells": self.sells_count,
                "trims": self.trims_count,
                "raise_cash": self.raise_cash_count,
                "total_buy_value": round(self.total_buy_value, 2),
                "total_sell_value": round(self.total_sell_value, 2),
            },
            "trades": [t.to_dict() for t in self.trades],
            "skipped_symbols": self.skipped_symbols,
            "warnings": self.warnings,
        }


# ── Money-market recommendation ─────────────────────────────────────────────

# Nigerian money-market / T-bill proxies (annualised yields as of 2025-2026)
MONEY_MARKET_OPTIONS = [
    {
        "instrument": "Nigerian Treasury Bills (NTB)",
        "ticker": None,
        "estimated_yield_pct": 10.0,
        "min_investment_ngn": 50_000,
        "liquidity": "high",
        "note": "Auctioned bi-weekly by CBN. Buy via primary dealers.",
    },
    {
        "instrument": "Money Market Fund (e.g. Stanbic IBTC MMF)",
        "ticker": None,
        "estimated_yield_pct": 9.0,
        "min_investment_ngn": 5_000,
        "liquidity": "high",
        "note": "Same-day or T+1 redemption. No brokerage fees.",
    },
]


# ── Orchestrator ─────────────────────────────────────────────────────────────

class RebalanceOrchestrator:
    """
    Generates a concrete, prioritised rebalance plan.

    Modes:
    - **normal**: Generate BUYs for strong recommendations, SELLs for weak
      holdings, TRIMs for oversized positions.
    - **defensive**: Drawdown > reduce threshold. Halve new BUY sizes,
      actively sell weakest holdings to raise cash.
    - **halt**: Drawdown > halt threshold. No new BUYs. Sell weakest
      positions and recommend money-market parking.
    """

    def __init__(
        self,
        risk_mgr: Optional[PortfolioRiskManager] = None,
        max_trades_per_rebalance: int = 10,
    ):
        self.risk_mgr = risk_mgr or PortfolioRiskManager()
        self.max_trades = max_trades_per_rebalance
        self.limits = self.risk_mgr.limits

    def generate_rebalance_plan(
        self,
        recommendations: List[Dict[str, Any]],
        positions: List[Dict[str, Any]],
        cash_ngn: float,
        portfolio_value: float,
        peak_value: float,
        sector_lookup: Dict[str, str],
        prices: Optional[Dict[str, float]] = None,
    ) -> RebalancePlan:
        """
        Generate a rebalance plan.

        Args:
            recommendations: List of recommendation dicts with keys:
                symbol, action, confidence, current_price, risk_level,
                composite_score (optional)
            positions: List of position dicts with keys:
                symbol, shares, market_value_ngn
            cash_ngn: Available cash
            portfolio_value: Total portfolio value
            peak_value: All-time high portfolio value
            sector_lookup: {symbol: sector_name}
            prices: {symbol: current_price} (optional, falls back to rec prices)

        Returns:
            RebalancePlan with prioritised trades
        """
        plan = RebalancePlan(
            portfolio_value=portfolio_value,
            cash_before=cash_ngn,
            cash_after_estimate=cash_ngn,
        )

        if portfolio_value <= 0:
            plan.warnings.append("Portfolio has no value — cannot rebalance")
            return plan

        # Determine drawdown and mode
        drawdown_pct = 0.0
        if peak_value > 0 and portfolio_value < peak_value:
            drawdown_pct = (peak_value - portfolio_value) / peak_value * 100
        plan.drawdown_pct = drawdown_pct

        if drawdown_pct >= self.limits.drawdown_halt_threshold:
            plan.mode = "halt"
        elif drawdown_pct >= self.limits.drawdown_reduce_threshold:
            plan.mode = "defensive"
        else:
            plan.mode = "normal"

        # Build lookup maps
        pos_map = {p["symbol"]: p for p in positions}
        rec_map = {r["symbol"]: r for r in recommendations}
        price_map = prices or {}
        # Fill price_map from recommendations
        for r in recommendations:
            if r["symbol"] not in price_map and "current_price" in r:
                price_map[r["symbol"]] = r["current_price"]
        # Fill from positions
        for p in positions:
            sym = p["symbol"]
            if sym not in price_map and p.get("shares", 0) > 0 and p.get("market_value_ngn", 0) > 0:
                price_map[sym] = p["market_value_ngn"] / p["shares"]

        # Compute sector weights
        sector_values: Dict[str, float] = {}
        for p in positions:
            sec = sector_lookup.get(p["symbol"], "Unknown")
            sector_values[sec] = sector_values.get(sec, 0) + p.get("market_value_ngn", 0)
        sector_weights = {
            s: v / portfolio_value for s, v in sector_values.items()
        } if portfolio_value > 0 else {}

        trades: List[Trade] = []
        running_cash = cash_ngn

        # ── Phase 1: TRIMs (oversized positions) ─────────────────────────
        for p in positions:
            sym = p["symbol"]
            mv = p.get("market_value_ngn", 0)
            weight = mv / portfolio_value if portfolio_value > 0 else 0
            price = price_map.get(sym, 0)
            shares = p.get("shares", 0)

            max_weight = self.limits.max_position_weight
            if weight > max_weight * 1.1 and price > 0 and shares > 0:
                # Trim to target weight
                target_value = portfolio_value * max_weight
                excess_value = mv - target_value
                trim_shares = int(excess_value / price)
                if trim_shares > 0:
                    trade = Trade(
                        symbol=sym,
                        action=TradeAction.TRIM,
                        shares=trim_shares,
                        estimated_value_ngn=trim_shares * price,
                        price=price,
                        reason=f"Position {weight*100:.1f}% exceeds {max_weight*100:.0f}% limit",
                        priority=1,
                        sector=sector_lookup.get(sym, "Unknown"),
                    )
                    trades.append(trade)
                    running_cash += trade.estimated_value_ngn

        # ── Phase 2: SELLs (recommendations say SELL/STRONG_SELL) ────────
        sell_recs = [
            r for r in recommendations
            if r.get("action") in ("SELL", "STRONG_SELL")
            and r["symbol"] in pos_map
        ]
        # Sort by score ascending (worst first)
        sell_recs.sort(key=lambda r: r.get("composite_score", 0))

        for r in sell_recs:
            sym = r["symbol"]
            pos = pos_map[sym]
            shares = pos.get("shares", 0)
            price = price_map.get(sym, 0)
            if shares > 0 and price > 0:
                trade = Trade(
                    symbol=sym,
                    action=TradeAction.SELL,
                    shares=shares,
                    estimated_value_ngn=shares * price,
                    price=price,
                    reason=f"Engine recommends {r['action']} (score {r.get('composite_score', 0):.2f})",
                    priority=2,
                    confidence=r.get("confidence", 0),
                    risk_level=r.get("risk_level", "moderate"),
                    sector=sector_lookup.get(sym, "Unknown"),
                )
                trades.append(trade)
                running_cash += trade.estimated_value_ngn

        # ── Phase 3: Defensive cash-raising (halt/defensive mode) ────────
        if plan.mode in ("halt", "defensive"):
            target_cash_pct = 0.30 if plan.mode == "halt" else 0.20
            target_cash = portfolio_value * target_cash_pct
            cash_needed = target_cash - running_cash

            if cash_needed > 0:
                # Rank existing positions by weakness (prefer selling weak ones)
                holdable = []
                for p in positions:
                    sym = p["symbol"]
                    # Skip if already being sold
                    already_selling = any(
                        t.symbol == sym and t.action in (TradeAction.SELL, TradeAction.TRIM)
                        for t in trades
                    )
                    if already_selling:
                        continue
                    rec = rec_map.get(sym, {})
                    score = rec.get("composite_score", 0)
                    holdable.append((p, score))

                # Sell weakest first
                holdable.sort(key=lambda x: x[1])

                for p, score in holdable:
                    if cash_needed <= 0:
                        break
                    sym = p["symbol"]
                    price = price_map.get(sym, 0)
                    shares = p.get("shares", 0)
                    mv = p.get("market_value_ngn", 0)
                    if price <= 0 or shares <= 0:
                        continue

                    # Sell enough to cover cash need (or all shares)
                    sell_value = min(mv, cash_needed)
                    sell_shares = min(int(sell_value / price), shares)
                    if sell_shares <= 0:
                        continue

                    trade = Trade(
                        symbol=sym,
                        action=TradeAction.RAISE_CASH,
                        shares=sell_shares,
                        estimated_value_ngn=sell_shares * price,
                        price=price,
                        reason=f"Raise cash ({plan.mode} mode, DD {drawdown_pct:.1f}%)",
                        priority=3,
                        confidence=0,
                        risk_level=p.get("risk_level", "moderate"),
                        sector=sector_lookup.get(sym, "Unknown"),
                    )
                    trades.append(trade)
                    running_cash += trade.estimated_value_ngn
                    cash_needed -= trade.estimated_value_ngn

                if plan.mode == "halt":
                    plan.warnings.append(
                        f"CIRCUIT BREAKER ACTIVE: Drawdown {drawdown_pct:.1f}%. "
                        f"No new BUYs. Raising cash to {target_cash_pct*100:.0f}%. "
                        f"Consider parking excess cash in: "
                        + ", ".join(m["instrument"] for m in MONEY_MARKET_OPTIONS)
                    )
                else:
                    plan.warnings.append(
                        f"DEFENSIVE MODE: Drawdown {drawdown_pct:.1f}%. "
                        f"BUY sizes halved. Raising cash to {target_cash_pct*100:.0f}%."
                    )

        # ── Phase 4: BUYs (normal and defensive modes, not halt) ─────────
        if plan.mode != "halt":
            buy_recs = [
                r for r in recommendations
                if r.get("action") in ("BUY", "STRONG_BUY")
            ]
            # Sort by composite_score descending (best first)
            buy_recs.sort(key=lambda r: r.get("composite_score", 0), reverse=True)

            for r in buy_recs:
                sym = r["symbol"]
                price = price_map.get(sym, r.get("current_price", 0))
                if price <= 0:
                    plan.skipped_symbols.append(sym)
                    continue

                existing_value = pos_map.get(sym, {}).get("market_value_ngn", 0)
                sector = sector_lookup.get(sym, r.get("sector", "Unknown"))

                sizing = self.risk_mgr.compute_position_size(
                    symbol=sym,
                    action=r["action"],
                    confidence=r.get("confidence", 0),
                    current_price=price,
                    risk_level=r.get("risk_level", "moderate"),
                    sector=sector,
                    portfolio_value=portfolio_value,
                    cash_available=running_cash,
                    existing_position_value=existing_value,
                    sector_weights=sector_weights,
                    portfolio_drawdown_pct=drawdown_pct,
                    liquidity_tier=r.get("liquidity_tier", "medium"),
                )

                if not sizing.approved:
                    plan.skipped_symbols.append(sym)
                    plan.warnings.append(
                        f"Skipped {sym}: {sizing.rejection_reason}"
                    )
                    continue

                if sizing.suggested_shares <= 0:
                    plan.skipped_symbols.append(sym)
                    continue

                trade = Trade(
                    symbol=sym,
                    action=TradeAction.BUY,
                    shares=sizing.suggested_shares,
                    estimated_value_ngn=sizing.suggested_value_ngn,
                    price=price,
                    reason=f"Engine: {r['action']} (score {r.get('composite_score', 0):.2f}, conf {r.get('confidence', 0):.0f}%)",
                    priority=5,
                    confidence=r.get("confidence", 0),
                    risk_level=r.get("risk_level", "moderate"),
                    sector=sector,
                )
                trades.append(trade)
                running_cash -= trade.estimated_value_ngn

                # Update sector weights for next iteration
                if sector in sector_weights:
                    sector_weights[sector] += trade.estimated_value_ngn / portfolio_value
                else:
                    sector_weights[sector] = trade.estimated_value_ngn / portfolio_value

        # ── Finalise plan ────────────────────────────────────────────────
        # Sort by priority, limit total trades
        trades.sort(key=lambda t: t.priority)
        plan.trades = trades[:self.max_trades]

        # Aggregate stats
        plan.buys_count = sum(1 for t in plan.trades if t.action == TradeAction.BUY)
        plan.sells_count = sum(1 for t in plan.trades if t.action == TradeAction.SELL)
        plan.trims_count = sum(1 for t in plan.trades if t.action == TradeAction.TRIM)
        plan.raise_cash_count = sum(1 for t in plan.trades if t.action == TradeAction.RAISE_CASH)
        plan.total_buy_value = sum(t.estimated_value_ngn for t in plan.trades if t.action == TradeAction.BUY)
        plan.total_sell_value = sum(
            t.estimated_value_ngn for t in plan.trades
            if t.action in (TradeAction.SELL, TradeAction.TRIM, TradeAction.RAISE_CASH)
        )
        plan.cash_after_estimate = running_cash

        # Money-market recommendation if excess cash
        if plan.cash_after_estimate > portfolio_value * 0.20:
            excess = plan.cash_after_estimate - portfolio_value * 0.10
            plan.warnings.append(
                f"Excess cash ₦{excess:,.0f} available. "
                f"Consider parking in: "
                + " | ".join(
                    f"{m['instrument']} (~{m['estimated_yield_pct']}% p.a.)"
                    for m in MONEY_MARKET_OPTIONS
                )
            )

        return plan
