"""
NGX Quality Scoring Engine v1 — Explainable, deterministic stock quality scoring.

Score breakdown (0–100):
  Profitability  (0–25):  ROE (0–15) + Operating Margin (0–10)
  Cash Quality   (0–25):  Cash Conversion (0–15) + FCF Positive (0–5) + OCF Positive (0–5)
  Balance Sheet  (0–25):  D/E low (0–15) + Cash/Debt high (0–10)
  Stability      (0–15):  Earnings stability (0–10) + Margin stability (0–5)
  Shareholder    (0–10):  Dividend consistency (0–5) + Dividend yield proxy (0–5)

Normalization:
  - Winsorize at 5th/95th percentile within the scored universe
  - Percentile rank → scale to sub-score max

Guardrails:
  - Negative equity → cap quality_score at 30, auto red flag
  - Net loss in latest period → cap profitability sub-score at 5
  - < 2 periods → cap total at 50, flag INSUFFICIENT_HISTORY
  - Stale data (> 540 days) → confidence penalty

Confidence penalty (separate from quality_score):
  - Missing fundamentals fields → proportional penalty
  - Stale data → penalty
  - Low liquidity → penalty
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.scanner.derived_metrics import DerivedMetrics

logger = logging.getLogger(__name__)


@dataclass
class QualityScore:
    """Full quality assessment for a single symbol."""
    symbol: str
    quality_score: float                          # 0-100 composite
    sub_scores: Dict[str, float]                  # per-category breakdown
    reasons: List[str]                            # human-readable explanations
    red_flags: List[str]                          # warning strings
    confidence_penalty: float = 0.0               # 0-1 (0=full confidence)
    data_quality: str = "FULL"                    # FULL | DEGRADED | INSUFFICIENT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quality_score": round(self.quality_score, 2),
            "sub_scores": {k: round(v, 2) for k, v in self.sub_scores.items()},
            "reasons": self.reasons,
            "red_flags": self.red_flags,
            "confidence_penalty": round(self.confidence_penalty, 4),
            "data_quality": self.data_quality,
        }


# ═══════════════════════════════════════════════════════════════════════
# Normalization utilities
# ═══════════════════════════════════════════════════════════════════════

def winsorize(values: List[Optional[float]], lower_pct: float = 0.05,
              upper_pct: float = 0.95) -> List[Optional[float]]:
    """
    Winsorize a list of values at given percentiles.
    None values are passed through unchanged.
    """
    valid = sorted([v for v in values if v is not None])
    if len(valid) < 2:
        return values

    lo_idx = max(0, int(len(valid) * lower_pct))
    hi_idx = min(len(valid) - 1, int(len(valid) * upper_pct))
    lo_val = valid[lo_idx]
    hi_val = valid[hi_idx]

    result = []
    for v in values:
        if v is None:
            result.append(None)
        else:
            result.append(max(lo_val, min(hi_val, v)))
    return result


def percentile_rank(value: Optional[float], all_values: List[Optional[float]],
                    higher_is_better: bool = True) -> float:
    """
    Compute percentile rank of value within all_values (0.0 to 1.0).
    None values are excluded from ranking. Returns 0.0 if value is None.
    """
    if value is None:
        return 0.0
    valid = [v for v in all_values if v is not None]
    if not valid:
        return 0.0
    if len(valid) == 1:
        return 0.5  # single item → median rank

    below = sum(1 for v in valid if v < value)
    equal = sum(1 for v in valid if v == value)
    rank = (below + 0.5 * equal) / len(valid)

    if not higher_is_better:
        rank = 1.0 - rank

    return max(0.0, min(1.0, rank))


# ═══════════════════════════════════════════════════════════════════════
# Scoring Engine
# ═══════════════════════════════════════════════════════════════════════

def score_universe(
    metrics_list: List[DerivedMetrics],
    dividend_history: Optional[Dict[str, int]] = None,
    liquidity_scores: Optional[Dict[str, float]] = None,
    liquidity_gate: float = 0.05,
) -> List[QualityScore]:
    """
    Score a universe of symbols based on their derived metrics.

    Args:
        metrics_list: list of DerivedMetrics (one per symbol)
        dividend_history: {symbol: years_with_dividends} from CorporateAction data
        liquidity_scores: {symbol: 0-1 liquidity score} from universe pipeline
        liquidity_gate: symbols below this score get confidence penalty

    Returns:
        List of QualityScore, sorted by quality_score descending.
    """
    if not metrics_list:
        return []

    dividend_history = dividend_history or {}
    liquidity_scores = liquidity_scores or {}

    # ── Step 1: Collect universe-wide values for normalization ────────

    all_roe = [m.roe for m in metrics_list]
    all_op_margin = [m.op_margin for m in metrics_list]
    all_de = [m.debt_to_equity for m in metrics_list]
    all_cash_debt = [m.cash_to_debt for m in metrics_list]
    all_ocf_ni = [m.ocf_to_net_income for m in metrics_list]
    all_earn_stab = [m.earnings_stability for m in metrics_list]
    all_margin_stab = [m.margin_stability for m in metrics_list]

    # Winsorize
    w_roe = winsorize(all_roe)
    w_op_margin = winsorize(all_op_margin)
    w_de = winsorize(all_de)
    w_cash_debt = winsorize(all_cash_debt)
    w_ocf_ni = winsorize(all_ocf_ni)

    # ── Step 2: Score each symbol ────────────────────────────────────

    results = []
    for i, m in enumerate(metrics_list):
        reasons: List[str] = []
        red_flags = list(m.red_flags)  # copy from derived metrics

        # ── Profitability (0–25) ─────────────────────────────────────
        roe_rank = percentile_rank(w_roe[i], w_roe, higher_is_better=True)
        roe_score = roe_rank * 15.0

        margin_rank = percentile_rank(w_op_margin[i], w_op_margin, higher_is_better=True)
        margin_score = margin_rank * 10.0

        profitability = roe_score + margin_score

        # Guardrail: net loss caps profitability
        if "NET_LOSS" in red_flags:
            profitability = min(profitability, 5.0)
            reasons.append("Profitability capped due to net loss in latest period")

        if m.roe is not None and m.roe > 0.15:
            reasons.append(f"Strong ROE of {m.roe:.1%}")
        elif m.roe is not None and m.roe > 0:
            reasons.append(f"Positive ROE of {m.roe:.1%}")

        if m.op_margin is not None and m.op_margin > 0.20:
            reasons.append(f"Healthy operating margin of {m.op_margin:.1%}")

        # ── Cash Quality (0–25) ──────────────────────────────────────
        ccr_rank = percentile_rank(w_ocf_ni[i], w_ocf_ni, higher_is_better=True)
        ccr_score = ccr_rank * 15.0

        fcf_positive_score = 5.0 if (m.fcf is not None and m.fcf > 0) else 0.0
        ocf_positive_score = 5.0 if (m.ocf_to_net_income is not None and
                                      m.ocf_to_net_income > 0) else 0.0
        # If OCF raw data is positive but ratio is weird, still give OCF credit
        # Actually check the flag — if NEGATIVE_OCF is flagged, 0 points
        if "NEGATIVE_OCF" in red_flags:
            ocf_positive_score = 0.0

        cash_quality = ccr_score + fcf_positive_score + ocf_positive_score

        if m.fcf is not None and m.fcf > 0:
            reasons.append(f"Positive free cash flow ({m.fcf:,.0f})")
        if m.ocf_to_net_income is not None and m.ocf_to_net_income > 1.0:
            reasons.append("Cash conversion exceeds net income (strong cash generation)")

        # ── Balance Sheet (0–25) ─────────────────────────────────────
        de_rank = percentile_rank(w_de[i], w_de, higher_is_better=False)  # lower D/E is better
        de_score = de_rank * 15.0

        cd_rank = percentile_rank(w_cash_debt[i], w_cash_debt, higher_is_better=True)
        cd_score = cd_rank * 10.0

        balance_sheet = de_score + cd_score

        if m.debt_to_equity is not None and m.debt_to_equity < 0.5:
            reasons.append(f"Conservative leverage (D/E = {m.debt_to_equity:.2f})")
        if m.cash_to_debt is not None and m.cash_to_debt > 1.0:
            reasons.append("Cash exceeds total debt")

        # ── Stability (0–15) ─────────────────────────────────────────
        earn_stab_rank = percentile_rank(
            all_earn_stab[i], all_earn_stab, higher_is_better=True)
        earn_stab_score = earn_stab_rank * 10.0

        margin_stab_rank = percentile_rank(
            all_margin_stab[i], all_margin_stab, higher_is_better=True)
        margin_stab_score = margin_stab_rank * 5.0

        stability = earn_stab_score + margin_stab_score

        if m.earnings_stability is not None and m.earnings_stability > 0.8:
            reasons.append("Highly stable earnings across periods")
        if m.margin_stability is not None and m.margin_stability > 0.8:
            reasons.append("Consistent operating margins")

        # ── Shareholder Return (0–10) ────────────────────────────────
        div_years = dividend_history.get(m.symbol, 0)
        # Assume max tracked = 5 years for scoring
        div_consistency = min(div_years / 5.0, 1.0) * 5.0

        # Dividend yield proxy: dividends_paid isn't in derived, but
        # we use the presence of dividend history as a quality signal
        div_yield_score = 0.0
        if div_years >= 3:
            div_yield_score = 5.0
            reasons.append(f"Consistent dividends ({div_years} years)")
        elif div_years >= 1:
            div_yield_score = 2.5
            reasons.append(f"Some dividend history ({div_years} years)")

        shareholder = div_consistency + div_yield_score

        # ── Composite ────────────────────────────────────────────────
        total = profitability + cash_quality + balance_sheet + stability + shareholder

        # Guardrails
        if "NEGATIVE_EQUITY" in red_flags:
            total = min(total, 30.0)
            reasons.append("Score capped at 30 due to negative equity")

        if "INSUFFICIENT_HISTORY" in red_flags:
            total = min(total, 50.0)
            reasons.append("Score capped at 50 due to insufficient history (< 2 periods)")

        # ── Confidence Penalty ───────────────────────────────────────
        penalty = 0.0

        # Missing fields penalty
        missing_count = sum(1 for v in [m.roe, m.op_margin, m.debt_to_equity,
                                         m.ocf_to_net_income, m.fcf]
                           if v is None)
        if missing_count > 0:
            penalty += missing_count * 0.05  # 5% per missing key metric

        # Stale data penalty
        if m.data_freshness_days is not None and m.data_freshness_days > 365:
            staleness_factor = min((m.data_freshness_days - 365) / 365, 1.0)
            penalty += staleness_factor * 0.2

        # Low liquidity penalty
        liq = liquidity_scores.get(m.symbol, 0.5)
        if liq < liquidity_gate:
            penalty += 0.3
            red_flags.append("LOW_LIQUIDITY")
            reasons.append("Significant liquidity concern — may be hard to trade")
        elif liq < 0.15:
            penalty += 0.1
            reasons.append("Below-average liquidity")

        penalty = min(penalty, 1.0)

        # Data quality label
        data_quality = "FULL"
        if "NO_FUNDAMENTALS_DATA" in red_flags:
            data_quality = "INSUFFICIENT"
        elif missing_count >= 3 or "STALE_FUNDAMENTALS" in red_flags:
            data_quality = "DEGRADED"

        results.append(QualityScore(
            symbol=m.symbol,
            quality_score=round(total, 2),
            sub_scores={
                "profitability": round(profitability, 2),
                "cash_quality": round(cash_quality, 2),
                "balance_sheet": round(balance_sheet, 2),
                "stability": round(stability, 2),
                "shareholder_return": round(shareholder, 2),
            },
            reasons=reasons,
            red_flags=red_flags,
            confidence_penalty=penalty,
            data_quality=data_quality,
        ))

    # Sort by quality_score descending
    results.sort(key=lambda x: x.quality_score, reverse=True)
    return results
