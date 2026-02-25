"""
Derived Metrics Engine — computes financial ratios from periodic fundamentals.

Pure computation: no DB access. Takes a list of periodic records (dicts)
and returns derived metrics for the latest period plus stability scores
across all available periods.

Usage:
    from app.scanner.derived_metrics import compute_derived_metrics
    derived = compute_derived_metrics(symbol="DANGCEM", periods=[...], as_of=date.today())
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DerivedMetrics:
    """Computed quality metrics for a single symbol."""
    symbol: str
    as_of_date: date

    # Profitability (from latest period)
    roe: Optional[float] = None
    roic_proxy: Optional[float] = None
    op_margin: Optional[float] = None
    net_margin: Optional[float] = None

    # Balance sheet (from latest period)
    debt_to_equity: Optional[float] = None
    cash_to_debt: Optional[float] = None

    # Cash quality (from latest period)
    ocf_to_net_income: Optional[float] = None
    fcf: Optional[float] = None

    # Stability (across multiple periods)
    earnings_stability: Optional[float] = None   # 1 - CoV(net_income)
    margin_stability: Optional[float] = None     # 1 - CoV(op_margin)

    # Metadata
    periods_available: int = 0
    data_freshness_days: Optional[int] = None
    red_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "as_of_date": self.as_of_date.isoformat(),
            "roe": _round(self.roe),
            "roic_proxy": _round(self.roic_proxy),
            "op_margin": _round(self.op_margin),
            "net_margin": _round(self.net_margin),
            "debt_to_equity": _round(self.debt_to_equity),
            "cash_to_debt": _round(self.cash_to_debt),
            "ocf_to_net_income": _round(self.ocf_to_net_income),
            "fcf": _round(self.fcf),
            "earnings_stability": _round(self.earnings_stability),
            "margin_stability": _round(self.margin_stability),
            "periods_available": self.periods_available,
            "data_freshness_days": self.data_freshness_days,
            "red_flags": self.red_flags,
        }


def _round(v: Optional[float], digits: int = 6) -> Optional[float]:
    return round(v, digits) if v is not None else None


def _safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    """Safe division: returns None if either operand is None or denominator is zero."""
    if num is None or den is None or den == 0:
        return None
    return num / den


def _coefficient_of_variation(values: List[float]) -> Optional[float]:
    """
    Coefficient of variation = std / |mean|.
    Returns None if fewer than 2 values or mean is zero.
    """
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    if mean == 0:
        return None
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    std = math.sqrt(variance)
    return std / abs(mean)


def compute_derived_metrics(
    symbol: str,
    periods: List[Dict[str, Any]],
    as_of: date,
) -> DerivedMetrics:
    """
    Compute derived financial metrics from periodic fundamentals.

    Args:
        symbol: stock ticker
        periods: list of dicts from FundamentalsPeriodic (sorted by period_end_date asc)
        as_of: reference date for freshness calculation

    Returns:
        DerivedMetrics with ratios, stability scores, and red flags.
    """
    result = DerivedMetrics(symbol=symbol, as_of_date=as_of)

    if not periods:
        result.red_flags.append("NO_FUNDAMENTALS_DATA")
        return result

    # Sort by period_end_date ascending (oldest first)
    sorted_periods = sorted(periods, key=lambda p: p["period_end_date"])
    result.periods_available = len(sorted_periods)

    # Latest period for point-in-time ratios
    latest = sorted_periods[-1]
    latest_date = latest["period_end_date"]
    if isinstance(latest_date, str):
        latest_date = date.fromisoformat(latest_date)
    result.data_freshness_days = (as_of - latest_date).days

    # ── Profitability ratios (from latest period) ────────────────────

    equity = latest.get("total_equity")
    debt = latest.get("total_debt")
    revenue = latest.get("revenue")
    op_profit = latest.get("operating_profit")
    net_income = latest.get("net_income")
    ocf = latest.get("operating_cash_flow")
    capex = latest.get("capex")
    cash = latest.get("cash")

    # For financial institutions (banks/insurers) operating_profit is often
    # unavailable. Fall back to net_income as an operating-profit proxy so
    # these stocks still get an op_margin score.
    effective_op_profit = op_profit if op_profit is not None else net_income

    # ROE
    result.roe = _safe_div(net_income, equity)

    # ROIC proxy = operating_profit / (equity + debt)
    invested = None
    if equity is not None and debt is not None:
        invested = equity + debt
    result.roic_proxy = _safe_div(effective_op_profit, invested)

    # Operating margin (uses net_income fallback for banks)
    result.op_margin = _safe_div(effective_op_profit, revenue)

    # Net margin
    result.net_margin = _safe_div(net_income, revenue)

    # ── Balance sheet ratios ─────────────────────────────────────────

    # Debt / Equity
    result.debt_to_equity = _safe_div(debt, equity)

    # Cash / Debt
    result.cash_to_debt = _safe_div(cash, debt)

    # ── Cash quality ─────────────────────────────────────────────────

    # Cash conversion ratio = OCF / net_income
    # Special handling: if both are negative, set to None (not meaningful)
    if net_income is not None and ocf is not None:
        if net_income < 0 and ocf < 0:
            result.ocf_to_net_income = None
        elif net_income == 0:
            result.ocf_to_net_income = None
        else:
            result.ocf_to_net_income = ocf / net_income

    # FCF = OCF - capex (capex is typically negative in some conventions, positive in others)
    if ocf is not None and capex is not None:
        # We treat capex as a positive number (expenditure), so FCF = OCF - |capex|
        result.fcf = ocf - abs(capex)
    elif ocf is not None:
        result.fcf = ocf  # No capex data → FCF ≈ OCF

    # ── Stability metrics (across all periods) ───────────────────────

    # Earnings stability = 1 - CoV(net_income)
    ni_values = [p["net_income"] for p in sorted_periods
                 if p.get("net_income") is not None]
    cov_ni = _coefficient_of_variation(ni_values)
    if cov_ni is not None:
        # Clamp to [0, 1]: CoV > 1 means very unstable → stability = 0
        result.earnings_stability = max(0.0, min(1.0, 1.0 - cov_ni))

    # Margin stability = 1 - CoV(operating_margin)
    # Falls back to net_income / revenue for banks where operating_profit is null
    margin_values = []
    for p in sorted_periods:
        rev = p.get("revenue")
        op = p.get("operating_profit")
        ni = p.get("net_income")
        eff_op = op if op is not None else ni
        if rev and eff_op and rev != 0:
            margin_values.append(eff_op / rev)
    cov_margin = _coefficient_of_variation(margin_values)
    if cov_margin is not None:
        result.margin_stability = max(0.0, min(1.0, 1.0 - cov_margin))

    # ── Red flags ────────────────────────────────────────────────────

    if equity is not None and equity < 0:
        result.red_flags.append("NEGATIVE_EQUITY")

    if net_income is not None and net_income < 0:
        result.red_flags.append("NET_LOSS")

    if ocf is not None and ocf < 0:
        result.red_flags.append("NEGATIVE_OCF")
        # Check for consecutive negative OCF
        neg_ocf_count = sum(
            1 for p in sorted_periods
            if p.get("operating_cash_flow") is not None and p["operating_cash_flow"] < 0
        )
        if neg_ocf_count >= 2:
            result.red_flags.append("CONSECUTIVE_NEGATIVE_OCF")

    if result.data_freshness_days is not None and result.data_freshness_days > 540:
        result.red_flags.append("STALE_FUNDAMENTALS")

    if result.periods_available < 2:
        result.red_flags.append("INSUFFICIENT_HISTORY")

    if debt is not None and equity is not None and equity > 0 and debt / equity > 2.0:
        result.red_flags.append("HIGH_LEVERAGE")

    return result
