"""
Valuation Engine — computes fair value and financial health scores.

Replaces Simply Wall St by computing metrics internally from our own
FundamentalsPeriodic and FundamentalsDerived data.

Two primary outputs:
1. Fair Value estimate (earnings-based + asset-based blend)
2. Financial Health score (6-factor: profitability, leverage, liquidity,
   growth, stability, cash quality)

Pure computation: takes fundamentals data dicts, returns results.
No DB access — caller is responsible for fetching data.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Data classes ─────────────────────────────────────────────────────

@dataclass
class FairValueResult:
    """Fair value estimate for a stock."""
    symbol: str
    current_price: float

    # Estimates
    earnings_value: Optional[float] = None      # P/E-based
    asset_value: Optional[float] = None          # Book value-based
    blended_value: Optional[float] = None        # Weighted blend

    # Discount/premium
    discount_pct: Optional[float] = None         # Negative = undervalued
    verdict: str = "UNKNOWN"                     # UNDERVALUED | FAIR | OVERVALUED

    # Inputs used
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    book_value_per_share: Optional[float] = None
    sector_avg_pe: Optional[float] = None

    confidence: str = "LOW"                      # LOW | MEDIUM | HIGH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "current_price": _r(self.current_price),
            "earnings_value": _r(self.earnings_value),
            "asset_value": _r(self.asset_value),
            "blended_value": _r(self.blended_value),
            "discount_pct": _r(self.discount_pct),
            "verdict": self.verdict,
            "pe_ratio": _r(self.pe_ratio),
            "eps": _r(self.eps),
            "book_value_per_share": _r(self.book_value_per_share),
            "sector_avg_pe": _r(self.sector_avg_pe),
            "confidence": self.confidence,
        }


@dataclass
class HealthFactor:
    """A single factor in the health score."""
    name: str
    score: float          # 0-100
    weight: float         # 0-1
    reasoning: str = ""


@dataclass
class HealthResult:
    """Financial health assessment for a stock."""
    symbol: str
    overall_score: float = 0.0          # 0-100
    grade: str = "F"                    # A, B, C, D, F
    factors: List[HealthFactor] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "overall_score": _r(self.overall_score),
            "grade": self.grade,
            "factors": [
                {"name": f.name, "score": _r(f.score), "weight": f.weight, "reasoning": f.reasoning}
                for f in self.factors
            ],
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
        }


def _r(v, digits=2):
    if v is None:
        return None
    return round(v, digits)


def _safe_div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


# ── Sector average P/E ratios for NGX ────────────────────────────────
# These are approximate sector averages for Nigerian equities.
# Updated periodically from market data.

SECTOR_PE_AVERAGES = {
    "Financial Services": 5.0,
    "Consumer Goods": 18.0,
    "Industrial Goods": 12.0,
    "Oil & Gas": 8.0,
    "ICT": 14.0,
    "Healthcare": 10.0,
    "Agriculture": 7.0,
    "Conglomerates": 8.0,
    "Construction": 10.0,
    "Services": 9.0,
    "Natural Resources": 8.0,
}

# Default P/E if sector unknown
DEFAULT_SECTOR_PE = 10.0


# ── Fair Value Engine ────────────────────────────────────────────────

class ValuationEngine:
    """
    Computes fair value estimates and financial health scores.

    Replaces Simply Wall St's proprietary metrics with transparent,
    auditable calculations from our own fundamentals data.
    """

    # Weights for blended fair value
    EARNINGS_WEIGHT = 0.65
    ASSET_WEIGHT = 0.35

    # Discount/premium thresholds
    UNDERVALUED_THRESHOLD = -0.15   # 15% below fair value
    OVERVALUED_THRESHOLD = 0.15     # 15% above fair value

    # Health factor weights (sum to 1.0)
    HEALTH_WEIGHTS = {
        "profitability": 0.25,
        "leverage": 0.20,
        "liquidity": 0.15,
        "growth": 0.15,
        "stability": 0.15,
        "cash_quality": 0.10,
    }

    def compute_fair_value(
        self,
        symbol: str,
        current_price: float,
        latest_period: Dict[str, Any],
        sector: Optional[str] = None,
        shares_outstanding: Optional[float] = None,
    ) -> FairValueResult:
        """
        Compute fair value estimate using earnings-based and asset-based methods.

        Args:
            symbol: Stock symbol
            current_price: Current market price per share
            latest_period: Dict with fundamentals (net_income, total_equity, etc.)
            sector: Sector name for P/E comparison
            shares_outstanding: Number of shares (for per-share calculations)
        """
        result = FairValueResult(symbol=symbol, current_price=current_price)

        net_income = latest_period.get("net_income")
        total_equity = latest_period.get("total_equity")
        shares = shares_outstanding or latest_period.get("shares_outstanding")

        # ── Earnings-based value (P/E method) ────────────────────────
        sector_pe = SECTOR_PE_AVERAGES.get(sector, DEFAULT_SECTOR_PE) if sector else DEFAULT_SECTOR_PE
        result.sector_avg_pe = sector_pe

        if net_income is not None and shares and shares > 0:
            eps = net_income / shares
            result.eps = eps
            if eps > 0:
                result.earnings_value = eps * sector_pe
                # Also compute actual P/E
                result.pe_ratio = current_price / eps if eps > 0 else None

        # ── Asset-based value (book value method) ────────────────────
        if total_equity is not None and shares and shares > 0:
            bvps = total_equity / shares
            result.book_value_per_share = bvps
            if bvps > 0:
                # For NGX, book value is often a floor value
                # Apply a modest premium for profitable companies
                premium = 1.2 if (net_income and net_income > 0) else 1.0
                result.asset_value = bvps * premium

        # ── Blended estimate ─────────────────────────────────────────
        if result.earnings_value and result.asset_value:
            result.blended_value = (
                result.earnings_value * self.EARNINGS_WEIGHT
                + result.asset_value * self.ASSET_WEIGHT
            )
            result.confidence = "HIGH"
        elif result.earnings_value:
            result.blended_value = result.earnings_value
            result.confidence = "MEDIUM"
        elif result.asset_value:
            result.blended_value = result.asset_value
            result.confidence = "MEDIUM"
        else:
            result.confidence = "LOW"
            result.verdict = "UNKNOWN"
            return result

        # ── Discount/premium ─────────────────────────────────────────
        if result.blended_value and result.blended_value > 0:
            result.discount_pct = (
                (current_price - result.blended_value) / result.blended_value
            )

            if result.discount_pct < self.UNDERVALUED_THRESHOLD:
                result.verdict = "UNDERVALUED"
            elif result.discount_pct > self.OVERVALUED_THRESHOLD:
                result.verdict = "OVERVALUED"
            else:
                result.verdict = "FAIR"

        return result

    def compute_health(
        self,
        symbol: str,
        periods: List[Dict[str, Any]],
    ) -> HealthResult:
        """
        Compute multi-factor financial health score.

        6 factors:
        1. Profitability (ROE, margins)
        2. Leverage (debt/equity, cash/debt)
        3. Liquidity (cash position, OCF coverage)
        4. Growth (revenue and earnings trends)
        5. Stability (earnings and margin consistency)
        6. Cash Quality (OCF vs net income, FCF)

        Args:
            symbol: Stock symbol
            periods: List of period dicts (newest first), at least 1 required
        """
        result = HealthResult(symbol=symbol)

        if not periods:
            result.grade = "F"
            result.weaknesses.append("No financial data available")
            return result

        latest = periods[0]

        # ── Factor 1: Profitability ──────────────────────────────────
        prof_score, prof_reason = self._score_profitability(latest)
        result.factors.append(HealthFactor(
            name="profitability", score=prof_score,
            weight=self.HEALTH_WEIGHTS["profitability"],
            reasoning=prof_reason,
        ))

        # ── Factor 2: Leverage ───────────────────────────────────────
        lev_score, lev_reason = self._score_leverage(latest)
        result.factors.append(HealthFactor(
            name="leverage", score=lev_score,
            weight=self.HEALTH_WEIGHTS["leverage"],
            reasoning=lev_reason,
        ))

        # ── Factor 3: Liquidity ──────────────────────────────────────
        liq_score, liq_reason = self._score_liquidity(latest)
        result.factors.append(HealthFactor(
            name="liquidity", score=liq_score,
            weight=self.HEALTH_WEIGHTS["liquidity"],
            reasoning=liq_reason,
        ))

        # ── Factor 4: Growth ─────────────────────────────────────────
        grow_score, grow_reason = self._score_growth(periods)
        result.factors.append(HealthFactor(
            name="growth", score=grow_score,
            weight=self.HEALTH_WEIGHTS["growth"],
            reasoning=grow_reason,
        ))

        # ── Factor 5: Stability ──────────────────────────────────────
        stab_score, stab_reason = self._score_stability(periods)
        result.factors.append(HealthFactor(
            name="stability", score=stab_score,
            weight=self.HEALTH_WEIGHTS["stability"],
            reasoning=stab_reason,
        ))

        # ── Factor 6: Cash Quality ───────────────────────────────────
        cash_score, cash_reason = self._score_cash_quality(latest)
        result.factors.append(HealthFactor(
            name="cash_quality", score=cash_score,
            weight=self.HEALTH_WEIGHTS["cash_quality"],
            reasoning=cash_reason,
        ))

        # ── Aggregate ────────────────────────────────────────────────
        total_weight = sum(f.weight for f in result.factors)
        if total_weight > 0:
            result.overall_score = sum(
                f.score * f.weight for f in result.factors
            ) / total_weight

        # Grade
        result.grade = self._score_to_grade(result.overall_score)

        # Strengths and weaknesses
        for f in result.factors:
            if f.score >= 70:
                result.strengths.append(f"{f.name}: {f.reasoning}")
            elif f.score <= 30:
                result.weaknesses.append(f"{f.name}: {f.reasoning}")

        return result

    # ── Factor scorers ───────────────────────────────────────────────

    def _score_profitability(self, p: Dict) -> tuple:
        """Score profitability (0-100) based on ROE and margins."""
        scores = []

        net_income = p.get("net_income")
        equity = p.get("total_equity")
        revenue = p.get("revenue")
        op_profit = p.get("operating_profit")

        # ROE
        roe = _safe_div(net_income, equity)
        if roe is not None:
            if roe >= 0.20:
                scores.append(100)
            elif roe >= 0.15:
                scores.append(80)
            elif roe >= 0.10:
                scores.append(60)
            elif roe >= 0.05:
                scores.append(40)
            elif roe > 0:
                scores.append(20)
            else:
                scores.append(0)

        # Net margin
        nm = _safe_div(net_income, revenue)
        if nm is not None:
            if nm >= 0.20:
                scores.append(100)
            elif nm >= 0.10:
                scores.append(75)
            elif nm >= 0.05:
                scores.append(50)
            elif nm > 0:
                scores.append(25)
            else:
                scores.append(0)

        # Operating margin (fall back to net margin if no operating_profit)
        om = _safe_div(op_profit, revenue)
        if om is None:
            om = _safe_div(net_income, revenue)
        if om is not None:
            if om >= 0.25:
                scores.append(100)
            elif om >= 0.15:
                scores.append(75)
            elif om >= 0.08:
                scores.append(50)
            elif om > 0:
                scores.append(25)
            else:
                scores.append(0)

        if not scores:
            return 50.0, "Insufficient profitability data"

        avg = sum(scores) / len(scores)
        if avg >= 70:
            reason = f"Strong profitability (ROE={_r(roe)}, margin={_r(nm)})"
        elif avg >= 40:
            reason = f"Moderate profitability (ROE={_r(roe)}, margin={_r(nm)})"
        else:
            reason = f"Weak profitability (ROE={_r(roe)}, margin={_r(nm)})"
        return avg, reason

    def _score_leverage(self, p: Dict) -> tuple:
        """Score leverage (0-100). Lower debt = higher score."""
        equity = p.get("total_equity")
        debt = p.get("total_debt")
        cash = p.get("cash")

        scores = []

        # Debt-to-equity
        de = _safe_div(debt, equity)
        if de is not None:
            if de <= 0.3:
                scores.append(100)
            elif de <= 0.6:
                scores.append(80)
            elif de <= 1.0:
                scores.append(60)
            elif de <= 2.0:
                scores.append(30)
            else:
                scores.append(10)

        # Cash-to-debt
        cd = _safe_div(cash, debt)
        if cd is not None:
            if cd >= 1.0:
                scores.append(100)
            elif cd >= 0.5:
                scores.append(70)
            elif cd >= 0.2:
                scores.append(40)
            else:
                scores.append(15)

        if not scores:
            return 50.0, "Insufficient balance sheet data"

        avg = sum(scores) / len(scores)
        if avg >= 70:
            reason = f"Conservative leverage (D/E={_r(de)})"
        elif avg >= 40:
            reason = f"Moderate leverage (D/E={_r(de)})"
        else:
            reason = f"High leverage (D/E={_r(de)})"
        return avg, reason

    def _score_liquidity(self, p: Dict) -> tuple:
        """Score liquidity (0-100) based on cash and OCF."""
        cash = p.get("cash")
        debt = p.get("total_debt")
        ocf = p.get("operating_cash_flow")
        assets = p.get("total_assets")

        scores = []

        # Cash / total assets ratio
        ca = _safe_div(cash, assets)
        if ca is not None:
            if ca >= 0.20:
                scores.append(100)
            elif ca >= 0.10:
                scores.append(70)
            elif ca >= 0.05:
                scores.append(40)
            else:
                scores.append(15)

        # OCF can cover debt service
        if ocf is not None and debt is not None and debt > 0:
            coverage = ocf / debt
            if coverage >= 0.5:
                scores.append(100)
            elif coverage >= 0.2:
                scores.append(60)
            else:
                scores.append(20)

        if not scores:
            return 50.0, "Insufficient liquidity data"

        avg = sum(scores) / len(scores)
        reason = f"Cash ratio={_r(ca)}" if ca else "Limited data"
        return avg, reason

    def _score_growth(self, periods: List[Dict]) -> tuple:
        """Score growth (0-100) based on revenue and earnings trends."""
        if len(periods) < 2:
            return 50.0, "Insufficient history for growth analysis"

        scores = []

        # Revenue growth (latest vs prior)
        rev_latest = periods[0].get("revenue")
        rev_prior = periods[1].get("revenue")
        rev_growth = _safe_div(
            (rev_latest - rev_prior) if (rev_latest and rev_prior) else None,
            abs(rev_prior) if rev_prior else None,
        )
        if rev_growth is not None:
            if rev_growth >= 0.15:
                scores.append(100)
            elif rev_growth >= 0.05:
                scores.append(70)
            elif rev_growth >= 0:
                scores.append(50)
            elif rev_growth >= -0.10:
                scores.append(25)
            else:
                scores.append(0)

        # Earnings growth
        ni_latest = periods[0].get("net_income")
        ni_prior = periods[1].get("net_income")
        ni_growth = _safe_div(
            (ni_latest - ni_prior) if (ni_latest and ni_prior) else None,
            abs(ni_prior) if ni_prior else None,
        )
        if ni_growth is not None:
            if ni_growth >= 0.20:
                scores.append(100)
            elif ni_growth >= 0.05:
                scores.append(70)
            elif ni_growth >= 0:
                scores.append(50)
            elif ni_growth >= -0.15:
                scores.append(25)
            else:
                scores.append(0)

        if not scores:
            return 50.0, "No growth data available"

        avg = sum(scores) / len(scores)
        if avg >= 70:
            reason = f"Strong growth (rev={_r(rev_growth)}, earnings={_r(ni_growth)})"
        elif avg >= 40:
            reason = f"Moderate growth (rev={_r(rev_growth)}, earnings={_r(ni_growth)})"
        else:
            reason = f"Declining (rev={_r(rev_growth)}, earnings={_r(ni_growth)})"
        return avg, reason

    def _score_stability(self, periods: List[Dict]) -> tuple:
        """Score stability (0-100) based on consistency of earnings/margins."""
        if len(periods) < 2:
            return 50.0, "Insufficient history for stability analysis"

        scores = []

        # Earnings stability: coefficient of variation
        ni_values = [p.get("net_income") for p in periods if p.get("net_income") is not None]
        if len(ni_values) >= 2:
            mean = sum(ni_values) / len(ni_values)
            if mean != 0:
                variance = sum((x - mean) ** 2 for x in ni_values) / len(ni_values)
                cov = math.sqrt(variance) / abs(mean)
                stability = max(0, 1 - cov)  # 1 = perfectly stable
                scores.append(stability * 100)

        # All positive earnings?
        if ni_values:
            all_positive = all(x > 0 for x in ni_values)
            scores.append(100 if all_positive else 30)

        # Revenue consistency
        rev_values = [p.get("revenue") for p in periods if p.get("revenue") is not None]
        if len(rev_values) >= 2:
            # Check if revenue is consistently growing or flat
            diffs = [rev_values[i] - rev_values[i + 1] for i in range(len(rev_values) - 1)]
            growing = sum(1 for d in diffs if d >= 0) / len(diffs)
            scores.append(growing * 100)

        if not scores:
            return 50.0, "No stability data"

        avg = sum(scores) / len(scores)
        reason = f"Based on {len(periods)} periods"
        if avg >= 70:
            reason = f"Consistent earnings across {len(periods)} periods"
        elif avg < 40:
            reason = f"Volatile earnings across {len(periods)} periods"
        return avg, reason

    def _score_cash_quality(self, p: Dict) -> tuple:
        """Score cash quality (0-100): OCF vs earnings, FCF generation."""
        scores = []

        ni = p.get("net_income")
        ocf = p.get("operating_cash_flow")
        capex = p.get("capex")

        # Cash conversion: OCF / net income
        if ocf is not None and ni is not None and ni > 0:
            ratio = ocf / ni
            if ratio >= 1.2:
                scores.append(100)
            elif ratio >= 0.8:
                scores.append(75)
            elif ratio >= 0.5:
                scores.append(40)
            else:
                scores.append(10)

        # FCF positive?
        if ocf is not None and capex is not None:
            fcf = ocf - abs(capex)
            scores.append(100 if fcf > 0 else 20)

        # OCF positive?
        if ocf is not None:
            scores.append(100 if ocf > 0 else 10)

        if not scores:
            return 50.0, "No cash flow data"

        avg = sum(scores) / len(scores)
        if avg >= 70:
            reason = "Strong cash generation"
        elif avg >= 40:
            reason = "Adequate cash flow"
        else:
            reason = "Weak cash flow quality"
        return avg, reason

    @staticmethod
    def _score_to_grade(score: float) -> str:
        if score >= 80:
            return "A"
        elif score >= 65:
            return "B"
        elif score >= 50:
            return "C"
        elif score >= 35:
            return "D"
        return "F"
