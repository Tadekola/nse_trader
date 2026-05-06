"""
Portfolio Risk Manager — position sizing, concentration limits, drawdown protection.

Provides portfolio-level risk controls that sit between the recommendation engine
(which evaluates individual stocks) and trade execution. Ensures no single position,
sector, or drawdown event can disproportionately harm the portfolio.

Design:
  - Pure computation engine — no DB access. Callers pass in portfolio state.
  - Integrates with existing PortfolioService (holdings/valuation) and
    RiskMetrics (per-stock risk) from the recommendation engine.

Usage::

    mgr = PortfolioRiskManager()
    sizing = mgr.compute_position_size(
        symbol="ZENITHBANK",
        action="BUY",
        confidence=56.0,
        current_price=35.50,
        risk_level="very_high",
        sector="Financial Services",
        portfolio_value=10_000_000,
        cash_available=2_000_000,
        holdings={"GTCO": {...}, "UBA": {...}},
        sector_weights={"Financial Services": 0.45, ...},
        portfolio_drawdown_pct=3.2,
    )
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────────

@dataclass
class RiskLimits:
    """Portfolio-level risk limits. All weights are fractions (0.0–1.0)."""

    # Position limits
    max_position_weight: float = 0.10       # No single stock > 10% of portfolio
    max_position_weight_low_liq: float = 0.05  # Low liquidity stocks capped at 5%
    min_position_value_ngn: float = 50_000   # Don't bother with tiny positions

    # Sector limits
    max_sector_weight: float = 0.35          # No sector > 35% of portfolio

    # Drawdown circuit breaker
    drawdown_halt_threshold: float = 15.0    # Halt new BUYs if portfolio DD > 15%
    drawdown_reduce_threshold: float = 8.0   # Reduce position sizes if DD > 8%
    drawdown_reduce_factor: float = 0.50     # Cut sizes by 50% in reduce zone

    # Confidence scaling
    min_confidence_for_full_size: float = 70.0  # Below this, scale position linearly
    min_confidence_for_any_size: float = 50.0   # Below this, no position at all

    # Cash reserve
    min_cash_reserve_pct: float = 0.10       # Always keep 10% in cash

    # Correlation guard (simplified: same-sector penalty)
    correlation_sector_penalty: float = 0.70  # Reduce size 30% if sector already >20%


# ── Output dataclasses ───────────────────────────────────────────────────────

@dataclass
class PositionSizing:
    """Result of position sizing computation."""
    symbol: str
    action: str                    # BUY, SELL, HOLD, etc.
    approved: bool                 # Whether the trade is approved
    rejection_reason: Optional[str] = None

    # Sizing (only meaningful if approved and action is BUY)
    suggested_shares: int = 0
    suggested_value_ngn: float = 0.0
    position_weight_pct: float = 0.0  # % of portfolio this position would be

    # Risk context
    max_allowed_value_ngn: float = 0.0
    confidence_scale_factor: float = 1.0
    drawdown_scale_factor: float = 1.0
    sector_scale_factor: float = 1.0

    # Warnings
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "approved": self.approved,
            "rejection_reason": self.rejection_reason,
            "suggested_shares": self.suggested_shares,
            "suggested_value_ngn": round(self.suggested_value_ngn, 2),
            "position_weight_pct": round(self.position_weight_pct, 2),
            "max_allowed_value_ngn": round(self.max_allowed_value_ngn, 2),
            "confidence_scale_factor": round(self.confidence_scale_factor, 3),
            "drawdown_scale_factor": round(self.drawdown_scale_factor, 3),
            "sector_scale_factor": round(self.sector_scale_factor, 3),
            "warnings": self.warnings,
        }


@dataclass
class PortfolioRiskReport:
    """Aggregate risk report for the whole portfolio."""
    total_value_ngn: float
    cash_pct: float
    num_positions: int
    largest_position_pct: float
    largest_position_symbol: str
    sector_weights: Dict[str, float]       # sector -> weight
    largest_sector_pct: float
    largest_sector_name: str
    hhi: float                              # Herfindahl–Hirschman Index (0–10000)
    drawdown_pct: float
    risk_flags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_value_ngn": round(self.total_value_ngn, 2),
            "cash_pct": round(self.cash_pct, 2),
            "num_positions": self.num_positions,
            "largest_position_pct": round(self.largest_position_pct, 2),
            "largest_position_symbol": self.largest_position_symbol,
            "sector_weights": {k: round(v, 4) for k, v in self.sector_weights.items()},
            "largest_sector_pct": round(self.largest_sector_pct, 2),
            "largest_sector_name": self.largest_sector_name,
            "hhi": round(self.hhi, 1),
            "drawdown_pct": round(self.drawdown_pct, 2),
            "risk_flags": self.risk_flags,
        }


# ── Portfolio Risk Manager ───────────────────────────────────────────────────

class PortfolioRiskManager:
    """
    Portfolio-level risk management engine.

    Computes position sizes, enforces concentration limits, and provides
    a drawdown circuit breaker. Stateless — all data passed in.
    """

    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or RiskLimits()

    # ── Position Sizing ──────────────────────────────────────────────────

    def compute_position_size(
        self,
        symbol: str,
        action: str,
        confidence: float,
        current_price: float,
        risk_level: str,
        sector: Optional[str],
        portfolio_value: float,
        cash_available: float,
        existing_position_value: float = 0.0,
        sector_weights: Optional[Dict[str, float]] = None,
        portfolio_drawdown_pct: float = 0.0,
        liquidity_tier: str = "medium",
    ) -> PositionSizing:
        """
        Compute how many shares to buy/sell given portfolio constraints.

        Args:
            symbol: Stock ticker
            action: Recommendation action (BUY, STRONG_BUY, SELL, etc.)
            confidence: Signal confidence (0–100)
            current_price: Current share price in NGN
            risk_level: Per-stock risk level (low, moderate, high, very_high)
            sector: Stock's sector name
            portfolio_value: Total portfolio value (holdings + cash)
            cash_available: Available cash in NGN
            existing_position_value: Current value of existing position in this stock
            sector_weights: Current sector weights {sector_name: weight}
            portfolio_drawdown_pct: Current portfolio drawdown from peak (positive %)
            liquidity_tier: Stock liquidity tier (high, medium, low, very_low)

        Returns:
            PositionSizing with approved/rejected status and suggested shares
        """
        L = self.limits
        warnings: List[str] = []

        # Non-BUY actions don't need sizing
        if action not in ("BUY", "STRONG_BUY"):
            return PositionSizing(
                symbol=symbol, action=action, approved=True,
                warnings=["No sizing needed for non-BUY action"],
            )

        if portfolio_value <= 0 or current_price <= 0:
            return PositionSizing(
                symbol=symbol, action=action, approved=False,
                rejection_reason="Invalid portfolio value or price",
            )

        # ── 1. Drawdown circuit breaker ──────────────────────────────────
        if portfolio_drawdown_pct >= L.drawdown_halt_threshold:
            return PositionSizing(
                symbol=symbol, action=action, approved=False,
                rejection_reason=(
                    f"Portfolio drawdown {portfolio_drawdown_pct:.1f}% exceeds "
                    f"halt threshold ({L.drawdown_halt_threshold}%)"
                ),
            )

        drawdown_scale = 1.0
        if portfolio_drawdown_pct >= L.drawdown_reduce_threshold:
            drawdown_scale = L.drawdown_reduce_factor
            warnings.append(
                f"Position reduced {(1 - drawdown_scale)*100:.0f}% due to "
                f"portfolio drawdown ({portfolio_drawdown_pct:.1f}%)"
            )

        # ── 2. Confidence scaling ────────────────────────────────────────
        if confidence < L.min_confidence_for_any_size:
            return PositionSizing(
                symbol=symbol, action=action, approved=False,
                rejection_reason=(
                    f"Confidence {confidence:.0f}% below minimum "
                    f"({L.min_confidence_for_any_size:.0f}%)"
                ),
            )

        if confidence >= L.min_confidence_for_full_size:
            confidence_scale = 1.0
        else:
            # Linear scale between min and full
            span = L.min_confidence_for_full_size - L.min_confidence_for_any_size
            confidence_scale = (confidence - L.min_confidence_for_any_size) / span
            warnings.append(
                f"Position scaled to {confidence_scale*100:.0f}% due to "
                f"moderate confidence ({confidence:.0f}%)"
            )

        # ── 3. Base position size from risk level ────────────────────────
        max_weight = L.max_position_weight
        if liquidity_tier in ("low", "very_low"):
            max_weight = L.max_position_weight_low_liq

        # Risk-level adjustment
        risk_multipliers = {
            "low": 1.0,
            "moderate": 0.80,
            "high": 0.60,
            "very_high": 0.40,
        }
        risk_mult = risk_multipliers.get(risk_level, 0.50)
        base_max_value = portfolio_value * max_weight * risk_mult

        # ── 4. Sector concentration limit ────────────────────────────────
        sector_scale = 1.0
        if sector and sector_weights:
            current_sector_weight = sector_weights.get(sector, 0.0)
            if current_sector_weight >= L.max_sector_weight:
                return PositionSizing(
                    symbol=symbol, action=action, approved=False,
                    rejection_reason=(
                        f"Sector '{sector}' at {current_sector_weight*100:.1f}% "
                        f"exceeds limit ({L.max_sector_weight*100:.0f}%)"
                    ),
                    warnings=warnings,
                )
            elif current_sector_weight > 0.20:
                sector_scale = L.correlation_sector_penalty
                warnings.append(
                    f"Sector '{sector}' already at {current_sector_weight*100:.1f}% "
                    f"— position reduced {(1 - sector_scale)*100:.0f}%"
                )

        # ── 5. Account for existing position ─────────────────────────────
        remaining_capacity = base_max_value - existing_position_value
        if remaining_capacity <= 0:
            return PositionSizing(
                symbol=symbol, action=action, approved=False,
                rejection_reason=(
                    f"Existing position (₦{existing_position_value:,.0f}) already "
                    f"at or above max (₦{base_max_value:,.0f})"
                ),
                warnings=warnings,
            )

        # ── 6. Cash reserve enforcement ──────────────────────────────────
        min_cash = portfolio_value * L.min_cash_reserve_pct
        deployable_cash = max(0, cash_available - min_cash)
        if deployable_cash <= 0:
            return PositionSizing(
                symbol=symbol, action=action, approved=False,
                rejection_reason=(
                    f"Insufficient cash after reserve "
                    f"(available ₦{cash_available:,.0f}, "
                    f"reserve ₦{min_cash:,.0f})"
                ),
                warnings=warnings,
            )

        # ── 7. Final computation ─────────────────────────────────────────
        max_value = min(remaining_capacity, deployable_cash)
        scaled_value = max_value * confidence_scale * drawdown_scale * sector_scale

        # Minimum position check
        if scaled_value < L.min_position_value_ngn:
            return PositionSizing(
                symbol=symbol, action=action, approved=False,
                rejection_reason=(
                    f"Computed position ₦{scaled_value:,.0f} below minimum "
                    f"₦{L.min_position_value_ngn:,.0f}"
                ),
                warnings=warnings,
            )

        suggested_shares = int(scaled_value / current_price)
        if suggested_shares <= 0:
            return PositionSizing(
                symbol=symbol, action=action, approved=False,
                rejection_reason="Computed 0 shares",
                warnings=warnings,
            )

        actual_value = suggested_shares * current_price
        position_weight = (existing_position_value + actual_value) / portfolio_value * 100

        return PositionSizing(
            symbol=symbol,
            action=action,
            approved=True,
            suggested_shares=suggested_shares,
            suggested_value_ngn=actual_value,
            position_weight_pct=position_weight,
            max_allowed_value_ngn=base_max_value,
            confidence_scale_factor=confidence_scale,
            drawdown_scale_factor=drawdown_scale,
            sector_scale_factor=sector_scale,
            warnings=warnings,
        )

    # ── Portfolio Risk Report ────────────────────────────────────────────

    def compute_risk_report(
        self,
        positions: List[Dict[str, Any]],
        cash_ngn: float,
        portfolio_value: float,
        peak_value: float,
        sector_lookup: Dict[str, str],
    ) -> PortfolioRiskReport:
        """
        Compute portfolio-level risk report.

        Args:
            positions: List of {symbol, market_value_ngn, ...}
            cash_ngn: Current cash balance
            portfolio_value: Total portfolio value
            peak_value: All-time high portfolio value (for drawdown)
            sector_lookup: {symbol: sector_name}

        Returns:
            PortfolioRiskReport with concentration metrics and risk flags
        """
        L = self.limits
        flags: List[str] = []

        if portfolio_value <= 0:
            return PortfolioRiskReport(
                total_value_ngn=0, cash_pct=0, num_positions=0,
                largest_position_pct=0, largest_position_symbol="",
                sector_weights={}, largest_sector_pct=0,
                largest_sector_name="", hhi=0, drawdown_pct=0,
                risk_flags=["Portfolio has no value"],
            )

        # Cash percentage
        cash_pct = (cash_ngn / portfolio_value) * 100
        if cash_pct < L.min_cash_reserve_pct * 100:
            flags.append(
                f"Cash reserve low: {cash_pct:.1f}% "
                f"(minimum {L.min_cash_reserve_pct*100:.0f}%)"
            )

        # Position concentration
        largest_pos_val = 0.0
        largest_pos_sym = ""
        sector_values: Dict[str, float] = {}
        weights_squared_sum = 0.0

        for pos in positions:
            sym = pos.get("symbol", "")
            mv = pos.get("market_value_ngn", 0)
            weight = mv / portfolio_value if portfolio_value > 0 else 0

            if mv > largest_pos_val:
                largest_pos_val = mv
                largest_pos_sym = sym

            # Position weight check
            if weight > L.max_position_weight:
                flags.append(
                    f"{sym} is {weight*100:.1f}% of portfolio "
                    f"(limit {L.max_position_weight*100:.0f}%)"
                )

            weights_squared_sum += (weight * 100) ** 2

            # Sector aggregation
            sector = sector_lookup.get(sym, "Unknown")
            sector_values[sector] = sector_values.get(sector, 0) + mv

        # HHI
        hhi = weights_squared_sum

        # Sector weights
        sector_weights = {
            s: v / portfolio_value for s, v in sector_values.items()
        }
        largest_sector_name = max(sector_weights, key=sector_weights.get) if sector_weights else ""
        largest_sector_pct = sector_weights.get(largest_sector_name, 0) * 100

        if largest_sector_pct / 100 > L.max_sector_weight:
            flags.append(
                f"Sector '{largest_sector_name}' at {largest_sector_pct:.1f}% "
                f"(limit {L.max_sector_weight*100:.0f}%)"
            )

        # Drawdown
        drawdown_pct = 0.0
        if peak_value > 0 and portfolio_value < peak_value:
            drawdown_pct = (peak_value - portfolio_value) / peak_value * 100

        if drawdown_pct >= L.drawdown_halt_threshold:
            flags.append(
                f"CIRCUIT BREAKER: Drawdown {drawdown_pct:.1f}% "
                f"exceeds halt threshold ({L.drawdown_halt_threshold}%)"
            )
        elif drawdown_pct >= L.drawdown_reduce_threshold:
            flags.append(
                f"Drawdown warning: {drawdown_pct:.1f}% — "
                f"position sizes reduced"
            )

        largest_pos_pct = (largest_pos_val / portfolio_value * 100) if portfolio_value > 0 else 0

        return PortfolioRiskReport(
            total_value_ngn=portfolio_value,
            cash_pct=cash_pct,
            num_positions=len(positions),
            largest_position_pct=largest_pos_pct,
            largest_position_symbol=largest_pos_sym,
            sector_weights=sector_weights,
            largest_sector_pct=largest_sector_pct,
            largest_sector_name=largest_sector_name,
            hhi=hhi,
            drawdown_pct=drawdown_pct,
            risk_flags=flags,
        )


# ── Singleton accessor ───────────────────────────────────────────────────────

_instance: Optional[PortfolioRiskManager] = None


def get_portfolio_risk_manager(
    limits: Optional[RiskLimits] = None,
) -> PortfolioRiskManager:
    """Get or create the singleton PortfolioRiskManager."""
    global _instance
    if _instance is None:
        _instance = PortfolioRiskManager(limits)
    return _instance
