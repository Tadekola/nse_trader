"""
Explainability Engine — reconstructs the full scoring rationale for a single symbol.

Pure computation. Takes the same inputs as score_universe() but returns a
detailed breakdown for one symbol showing:
  - Raw metric values from DerivedMetrics
  - Winsorization bounds applied to the universe
  - Winsorized metric values
  - Percentile ranks per metric
  - Individual component scores (pre- and post-guardrail)
  - Guardrail triggers with caps applied
  - Confidence penalty decomposition
  - Scoring config version for reproducibility
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from app.scanner.derived_metrics import DerivedMetrics
from app.scanner.quality_scorer import (
    winsorize, percentile_rank, QualityScore,
)

SCORING_CONFIG_VERSION = "v1.0"

# Weights encoded as data so they can be hashed for reproducibility
SCORING_CONFIG = {
    "version": SCORING_CONFIG_VERSION,
    "max_scores": {
        "profitability": 25,
        "cash_quality": 25,
        "balance_sheet": 25,
        "stability": 15,
        "shareholder_return": 10,
    },
    "components": {
        "roe": {"max": 15, "direction": "higher_is_better"},
        "op_margin": {"max": 10, "direction": "higher_is_better"},
        "cash_conversion": {"max": 15, "direction": "higher_is_better"},
        "fcf_positive": {"max": 5, "type": "binary"},
        "ocf_positive": {"max": 5, "type": "binary"},
        "debt_to_equity": {"max": 15, "direction": "lower_is_better"},
        "cash_to_debt": {"max": 10, "direction": "higher_is_better"},
        "earnings_stability": {"max": 10, "direction": "higher_is_better"},
        "margin_stability": {"max": 5, "direction": "higher_is_better"},
        "dividend_consistency": {"max": 5, "type": "scaled"},
        "dividend_yield_proxy": {"max": 5, "type": "threshold"},
    },
    "guardrails": {
        "negative_equity_cap": 30,
        "net_loss_profitability_cap": 5,
        "insufficient_history_cap": 50,
    },
    "confidence_penalty": {
        "missing_field_rate": 0.05,
        "staleness_threshold_days": 365,
        "staleness_max_penalty": 0.20,
        "liquidity_gate": 0.05,
        "liquidity_gate_penalty": 0.30,
        "low_liquidity_threshold": 0.15,
        "low_liquidity_penalty": 0.10,
    },
    "winsorize": {"lower_pct": 0.05, "upper_pct": 0.95},
}


def get_scoring_config_hash() -> str:
    """Deterministic hash of the scoring configuration."""
    raw = json.dumps(SCORING_CONFIG, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class MetricExplanation:
    """Explanation for a single metric component."""
    metric_name: str
    raw_value: Optional[float]
    winsorized_value: Optional[float]
    percentile_rank: float
    component_score: float
    max_possible: float
    direction: str  # "higher_is_better" | "lower_is_better" | "binary" | "threshold"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "raw_value": _r(self.raw_value),
            "winsorized_value": _r(self.winsorized_value),
            "percentile_rank": round(self.percentile_rank, 4),
            "component_score": round(self.component_score, 2),
            "max_possible": self.max_possible,
            "direction": self.direction,
        }


@dataclass
class GuardrailTrigger:
    """Record of a guardrail being applied."""
    name: str
    triggered: bool
    cap_value: Optional[float]
    score_before: float
    score_after: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "triggered": self.triggered,
            "cap_value": self.cap_value,
            "score_before": round(self.score_before, 2),
            "score_after": round(self.score_after, 2),
            "reason": self.reason,
        }


@dataclass
class ConfidencePenaltyBreakdown:
    """Decomposition of the confidence penalty."""
    total: float
    missing_fields: List[str]
    missing_fields_penalty: float
    staleness_days: Optional[int]
    staleness_penalty: float
    liquidity_score: float
    liquidity_penalty: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": round(self.total, 4),
            "missing_fields": self.missing_fields,
            "missing_fields_penalty": round(self.missing_fields_penalty, 4),
            "staleness_days": self.staleness_days,
            "staleness_penalty": round(self.staleness_penalty, 4),
            "liquidity_score": round(self.liquidity_score, 4),
            "liquidity_penalty": round(self.liquidity_penalty, 4),
        }


@dataclass
class WinsorBounds:
    """Winsorization bounds applied to the universe."""
    metric_name: str
    lower_bound: Optional[float]
    upper_bound: Optional[float]
    universe_size: int
    non_null_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "lower_bound": _r(self.lower_bound),
            "upper_bound": _r(self.upper_bound),
            "universe_size": self.universe_size,
            "non_null_count": self.non_null_count,
        }


@dataclass
class ScoreExplanation:
    """Complete explanation for a single symbol's quality score."""
    symbol: str
    quality_score: float
    scoring_config_version: str
    scoring_config_hash: str

    # Detailed breakdowns
    metric_explanations: List[MetricExplanation]
    guardrail_triggers: List[GuardrailTrigger]
    confidence_breakdown: ConfidencePenaltyBreakdown
    winsor_bounds: List[WinsorBounds]

    # Inputs snapshot
    derived_metrics_snapshot: Dict[str, Any]
    dividend_years: int
    data_quality: str
    red_flags: List[str]
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quality_score": round(self.quality_score, 2),
            "scoring_config_version": self.scoring_config_version,
            "scoring_config_hash": self.scoring_config_hash,
            "metric_explanations": [m.to_dict() for m in self.metric_explanations],
            "guardrail_triggers": [g.to_dict() for g in self.guardrail_triggers],
            "confidence_breakdown": self.confidence_breakdown.to_dict(),
            "winsor_bounds": [w.to_dict() for w in self.winsor_bounds],
            "derived_metrics_snapshot": self.derived_metrics_snapshot,
            "dividend_years": self.dividend_years,
            "data_quality": self.data_quality,
            "red_flags": self.red_flags,
            "reasons": self.reasons,
        }


def _r(v: Optional[float], digits: int = 6) -> Optional[float]:
    return round(v, digits) if v is not None else None


def _compute_winsor_bounds(
    raw_values: List[Optional[float]], metric_name: str
) -> WinsorBounds:
    """Compute and return the winsorization bounds for a metric."""
    valid = sorted([v for v in raw_values if v is not None])
    n = len(raw_values)
    non_null = len(valid)
    if non_null < 2:
        return WinsorBounds(metric_name, None, None, n, non_null)
    lo_idx = max(0, int(non_null * 0.05))
    hi_idx = min(non_null - 1, int(non_null * 0.95))
    return WinsorBounds(metric_name, valid[lo_idx], valid[hi_idx], n, non_null)


def explain_score(
    target_symbol: str,
    metrics_list: List[DerivedMetrics],
    dividend_history: Optional[Dict[str, int]] = None,
    liquidity_scores: Optional[Dict[str, float]] = None,
    liquidity_gate: float = 0.05,
) -> Optional[ScoreExplanation]:
    """
    Produce a full explanation for one symbol's quality score.

    This re-runs the scoring logic with instrumentation to capture every
    intermediate value. The final score must exactly match score_universe().

    Returns None if target_symbol is not in metrics_list.
    """
    if not metrics_list:
        return None

    dividend_history = dividend_history or {}
    liquidity_scores = liquidity_scores or {}

    # Find target
    target_idx = None
    target_m = None
    for i, m in enumerate(metrics_list):
        if m.symbol == target_symbol:
            target_idx = i
            target_m = m
            break
    if target_m is None:
        return None

    # ── Collect universe-wide values ─────────────────────────────────
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

    # ── Winsor bounds ────────────────────────────────────────────────
    winsor_bounds = [
        _compute_winsor_bounds(all_roe, "roe"),
        _compute_winsor_bounds(all_op_margin, "op_margin"),
        _compute_winsor_bounds(all_de, "debt_to_equity"),
        _compute_winsor_bounds(all_cash_debt, "cash_to_debt"),
        _compute_winsor_bounds(all_ocf_ni, "ocf_to_net_income"),
    ]

    # ── Score the target symbol with full instrumentation ────────────
    i = target_idx
    m = target_m
    red_flags = list(m.red_flags)
    reasons: List[str] = []
    metric_explanations: List[MetricExplanation] = []

    # Profitability
    roe_rank = percentile_rank(w_roe[i], w_roe, higher_is_better=True)
    roe_score = roe_rank * 15.0
    metric_explanations.append(MetricExplanation(
        "roe", m.roe, w_roe[i], roe_rank, roe_score, 15.0, "higher_is_better"))

    margin_rank = percentile_rank(w_op_margin[i], w_op_margin, higher_is_better=True)
    margin_score = margin_rank * 10.0
    metric_explanations.append(MetricExplanation(
        "op_margin", m.op_margin, w_op_margin[i], margin_rank, margin_score, 10.0,
        "higher_is_better"))

    profitability = roe_score + margin_score
    profitability_pre_guardrail = profitability

    if "NET_LOSS" in red_flags:
        profitability = min(profitability, 5.0)
        reasons.append("Profitability capped due to net loss in latest period")

    if m.roe is not None and m.roe > 0.15:
        reasons.append(f"Strong ROE of {m.roe:.1%}")
    elif m.roe is not None and m.roe > 0:
        reasons.append(f"Positive ROE of {m.roe:.1%}")
    if m.op_margin is not None and m.op_margin > 0.20:
        reasons.append(f"Healthy operating margin of {m.op_margin:.1%}")

    # Cash quality
    ccr_rank = percentile_rank(w_ocf_ni[i], w_ocf_ni, higher_is_better=True)
    ccr_score = ccr_rank * 15.0
    metric_explanations.append(MetricExplanation(
        "cash_conversion", m.ocf_to_net_income, w_ocf_ni[i], ccr_rank, ccr_score,
        15.0, "higher_is_better"))

    fcf_positive_score = 5.0 if (m.fcf is not None and m.fcf > 0) else 0.0
    metric_explanations.append(MetricExplanation(
        "fcf_positive", m.fcf, m.fcf, 1.0 if fcf_positive_score > 0 else 0.0,
        fcf_positive_score, 5.0, "binary"))

    ocf_positive_score = 5.0 if (m.ocf_to_net_income is not None and
                                  m.ocf_to_net_income > 0) else 0.0
    if "NEGATIVE_OCF" in red_flags:
        ocf_positive_score = 0.0
    metric_explanations.append(MetricExplanation(
        "ocf_positive", m.ocf_to_net_income, m.ocf_to_net_income,
        1.0 if ocf_positive_score > 0 else 0.0, ocf_positive_score, 5.0, "binary"))

    cash_quality = ccr_score + fcf_positive_score + ocf_positive_score

    if m.fcf is not None and m.fcf > 0:
        reasons.append(f"Positive free cash flow ({m.fcf:,.0f})")
    if m.ocf_to_net_income is not None and m.ocf_to_net_income > 1.0:
        reasons.append("Cash conversion exceeds net income (strong cash generation)")

    # Balance sheet
    de_rank = percentile_rank(w_de[i], w_de, higher_is_better=False)
    de_score = de_rank * 15.0
    metric_explanations.append(MetricExplanation(
        "debt_to_equity", m.debt_to_equity, w_de[i], de_rank, de_score, 15.0,
        "lower_is_better"))

    cd_rank = percentile_rank(w_cash_debt[i], w_cash_debt, higher_is_better=True)
    cd_score = cd_rank * 10.0
    metric_explanations.append(MetricExplanation(
        "cash_to_debt", m.cash_to_debt, w_cash_debt[i], cd_rank, cd_score, 10.0,
        "higher_is_better"))

    balance_sheet = de_score + cd_score

    if m.debt_to_equity is not None and m.debt_to_equity < 0.5:
        reasons.append(f"Conservative leverage (D/E = {m.debt_to_equity:.2f})")
    if m.cash_to_debt is not None and m.cash_to_debt > 1.0:
        reasons.append("Cash exceeds total debt")

    # Stability
    earn_stab_rank = percentile_rank(
        all_earn_stab[i], all_earn_stab, higher_is_better=True)
    earn_stab_score = earn_stab_rank * 10.0
    metric_explanations.append(MetricExplanation(
        "earnings_stability", m.earnings_stability, m.earnings_stability,
        earn_stab_rank, earn_stab_score, 10.0, "higher_is_better"))

    margin_stab_rank = percentile_rank(
        all_margin_stab[i], all_margin_stab, higher_is_better=True)
    margin_stab_score = margin_stab_rank * 5.0
    metric_explanations.append(MetricExplanation(
        "margin_stability", m.margin_stability, m.margin_stability,
        margin_stab_rank, margin_stab_score, 5.0, "higher_is_better"))

    stability = earn_stab_score + margin_stab_score

    if m.earnings_stability is not None and m.earnings_stability > 0.8:
        reasons.append("Highly stable earnings across periods")
    if m.margin_stability is not None and m.margin_stability > 0.8:
        reasons.append("Consistent operating margins")

    # Shareholder
    div_years = dividend_history.get(m.symbol, 0)
    div_consistency = min(div_years / 5.0, 1.0) * 5.0
    div_yield_score = 0.0
    if div_years >= 3:
        div_yield_score = 5.0
        reasons.append(f"Consistent dividends ({div_years} years)")
    elif div_years >= 1:
        div_yield_score = 2.5
        reasons.append(f"Some dividend history ({div_years} years)")
    shareholder = div_consistency + div_yield_score

    metric_explanations.append(MetricExplanation(
        "dividend_consistency", float(div_years), float(div_years),
        min(div_years / 5.0, 1.0), div_consistency, 5.0, "scaled"))
    metric_explanations.append(MetricExplanation(
        "dividend_yield_proxy", float(div_years), float(div_years),
        1.0 if div_years >= 3 else (0.5 if div_years >= 1 else 0.0),
        div_yield_score, 5.0, "threshold"))

    # ── Composite + guardrails ───────────────────────────────────────
    total = profitability + cash_quality + balance_sheet + stability + shareholder
    total_pre_guardrails = total

    guardrails: List[GuardrailTrigger] = []

    # Net loss guardrail (already applied to profitability above)
    guardrails.append(GuardrailTrigger(
        "net_loss_profitability_cap",
        triggered="NET_LOSS" in red_flags,
        cap_value=5.0,
        score_before=profitability_pre_guardrail,
        score_after=profitability,
        reason="Net loss in latest period caps profitability sub-score at 5",
    ))

    neg_eq_before = total
    if "NEGATIVE_EQUITY" in red_flags:
        total = min(total, 30.0)
        reasons.append("Score capped at 30 due to negative equity")
    guardrails.append(GuardrailTrigger(
        "negative_equity_cap",
        triggered="NEGATIVE_EQUITY" in red_flags,
        cap_value=30.0,
        score_before=neg_eq_before,
        score_after=total,
        reason="Negative equity caps total score at 30",
    ))

    insuf_before = total
    if "INSUFFICIENT_HISTORY" in red_flags:
        total = min(total, 50.0)
        reasons.append("Score capped at 50 due to insufficient history (< 2 periods)")
    guardrails.append(GuardrailTrigger(
        "insufficient_history_cap",
        triggered="INSUFFICIENT_HISTORY" in red_flags,
        cap_value=50.0,
        score_before=insuf_before,
        score_after=total,
        reason="Fewer than 2 reporting periods caps total score at 50",
    ))

    # ── Confidence penalty decomposition ─────────────────────────────
    penalty = 0.0
    missing_fields = []
    key_metrics = {
        "roe": m.roe, "op_margin": m.op_margin, "debt_to_equity": m.debt_to_equity,
        "ocf_to_net_income": m.ocf_to_net_income, "fcf": m.fcf,
    }
    for name, val in key_metrics.items():
        if val is None:
            missing_fields.append(name)
    missing_penalty = len(missing_fields) * 0.05

    staleness_penalty = 0.0
    if m.data_freshness_days is not None and m.data_freshness_days > 365:
        staleness_factor = min((m.data_freshness_days - 365) / 365, 1.0)
        staleness_penalty = staleness_factor * 0.2

    liq = liquidity_scores.get(m.symbol, 0.5)
    liq_penalty = 0.0
    if liq < liquidity_gate:
        liq_penalty = 0.3
        if "LOW_LIQUIDITY" not in red_flags:
            red_flags.append("LOW_LIQUIDITY")
        reasons.append("Significant liquidity concern — may be hard to trade")
    elif liq < 0.15:
        liq_penalty = 0.1
        reasons.append("Below-average liquidity")

    penalty = min(missing_penalty + staleness_penalty + liq_penalty, 1.0)

    confidence_breakdown = ConfidencePenaltyBreakdown(
        total=penalty,
        missing_fields=missing_fields,
        missing_fields_penalty=missing_penalty,
        staleness_days=m.data_freshness_days,
        staleness_penalty=staleness_penalty,
        liquidity_score=liq,
        liquidity_penalty=liq_penalty,
    )

    # Data quality
    missing_count = len(missing_fields)
    data_quality = "FULL"
    if "NO_FUNDAMENTALS_DATA" in red_flags:
        data_quality = "INSUFFICIENT"
    elif missing_count >= 3 or "STALE_FUNDAMENTALS" in red_flags:
        data_quality = "DEGRADED"

    return ScoreExplanation(
        symbol=target_symbol,
        quality_score=round(total, 2),
        scoring_config_version=SCORING_CONFIG_VERSION,
        scoring_config_hash=get_scoring_config_hash(),
        metric_explanations=metric_explanations,
        guardrail_triggers=guardrails,
        confidence_breakdown=confidence_breakdown,
        winsor_bounds=winsor_bounds,
        derived_metrics_snapshot=m.to_dict(),
        dividend_years=div_years,
        data_quality=data_quality,
        red_flags=red_flags,
        reasons=reasons,
    )
