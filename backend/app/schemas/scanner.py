"""
Pydantic schemas for NGX Quality Scanner API responses.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


# ── Universe ─────────────────────────────────────────────────────────

class UniverseMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    universe_name: str
    as_of_date: date
    rank: int
    liquidity_score: float
    avg_daily_value: Optional[float] = None
    zero_volume_days: Optional[int] = None


class UniverseResponse(BaseModel):
    universe_name: str
    as_of_date: date
    member_count: int
    members: List[UniverseMemberResponse]


# ── Scan Run ─────────────────────────────────────────────────────────

class ScanRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    as_of_date: date
    universe_name: str
    symbols_scanned: int
    symbols_ranked: int
    created_at: datetime
    summary: Optional[Dict[str, Any]] = None


class ScanRunListResponse(BaseModel):
    total: int
    runs: List[ScanRunResponse]


# ── Scan Result ──────────────────────────────────────────────────────

class TrailingReturns(BaseModel):
    tri_1y_ngn: Optional[float] = None
    tri_3y_ngn: Optional[float] = None
    tri_1y_usd: Optional[float] = None
    tri_3y_usd: Optional[float] = None
    tri_1y_real: Optional[float] = None
    tri_3y_real: Optional[float] = None


class ScanResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    rank: int
    quality_score: float
    sub_scores: Optional[Dict[str, float]] = None
    reasons: Optional[List[str]] = None
    red_flags: Optional[List[str]] = None
    flags: Optional[Dict[str, Any]] = None
    liquidity_score: Optional[float] = None
    confidence_penalty: Optional[float] = None
    trailing_returns: Optional[TrailingReturns] = None


class ScanResultListResponse(BaseModel):
    run_id: int
    as_of_date: date
    universe_name: str
    total: int
    results: List[ScanResultResponse]


# ── Buylist ──────────────────────────────────────────────────────────

class BuylistEntry(BaseModel):
    rank: int
    symbol: str
    quality_score: float
    data_quality: str
    confidence_penalty: float
    sub_scores: Optional[Dict[str, float]] = None
    top_reasons: List[str]
    red_flags: List[str]
    trailing_returns: TrailingReturns


class BuylistResponse(BaseModel):
    as_of_date: date
    universe_name: str
    run_id: int
    currency_note: str
    total: int
    buylist: List[BuylistEntry]


# ── Explainability ───────────────────────────────────────────────────

class MetricExplanationResponse(BaseModel):
    metric_name: str
    raw_value: Optional[float] = None
    winsorized_value: Optional[float] = None
    percentile_rank: float
    component_score: float
    max_possible: float
    direction: str


class GuardrailTriggerResponse(BaseModel):
    name: str
    triggered: bool
    cap_value: Optional[float] = None
    score_before: float
    score_after: float
    reason: str


class ConfidencePenaltyResponse(BaseModel):
    total: float
    missing_fields: List[str]
    missing_fields_penalty: float
    staleness_days: Optional[int] = None
    staleness_penalty: float
    liquidity_score: float
    liquidity_penalty: float


class WinsorBoundsResponse(BaseModel):
    metric_name: str
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    universe_size: int
    non_null_count: int


class ScoreExplanationResponse(BaseModel):
    symbol: str
    quality_score: float
    scoring_config_version: str
    scoring_config_hash: str
    metric_explanations: List[MetricExplanationResponse]
    guardrail_triggers: List[GuardrailTriggerResponse]
    confidence_breakdown: ConfidencePenaltyResponse
    winsor_bounds: List[WinsorBoundsResponse]
    derived_metrics_snapshot: Dict[str, Any]
    dividend_years: int
    data_quality: str
    red_flags: List[str]
    reasons: List[str]


# ── Scanner Health ───────────────────────────────────────────────────

class DataCoverageResponse(BaseModel):
    total_universe: int
    with_fundamentals: int
    with_tri: int
    with_fx: bool
    with_cpi: bool
    fundamentals_coverage_pct: float
    tri_coverage_pct: float


class StalenessResponse(BaseModel):
    last_scan_ts: Optional[datetime] = None
    last_scan_age_hours: Optional[float] = None
    last_fundamentals_import_ts: Optional[datetime] = None
    fx_latest_date: Optional[date] = None
    cpi_latest_date: Optional[date] = None
    fx_staleness_days: Optional[int] = None
    cpi_staleness_days: Optional[int] = None


class AnomalyResponse(BaseModel):
    anomaly_type: str
    description: str
    severity: str  # WARNING | CRITICAL


class ScannerHealthResponse(BaseModel):
    status: str  # HEALTHY | DEGRADED | CRITICAL
    last_scan_ts: Optional[datetime] = None
    data_coverage: DataCoverageResponse
    staleness: StalenessResponse
    anomalies: List[AnomalyResponse]
    recommendations: List[str]


# ── UI Dashboard ─────────────────────────────────────────────────────

class ScoreDistribution(BaseModel):
    """Histogram bucket for quality score distribution chart."""
    bucket: str       # e.g. "0-20", "20-40", "40-60", "60-80", "80-100"
    count: int


class QualityTierSummary(BaseModel):
    """Tier breakdown for the scanner dashboard."""
    tier: str         # HIGH / MEDIUM / LOW / INSUFFICIENT
    min_score: float
    max_score: float
    count: int
    symbols: List[str]


class ScannerDashboardResponse(BaseModel):
    """
    Dashboard summary card for the Next.js frontend.

    Designed to power:
      - Hero card: latest scan date, universe size, avg score, health status
      - Score distribution chart (5 buckets)
      - Quality tier breakdown
      - Top movers (biggest rank changes vs previous scan)
      - Quick stats: red flags count, degraded count, coverage %
    """
    # Hero card
    last_scan_date: Optional[date] = None
    last_scan_run_id: Optional[int] = None
    universe_name: str
    universe_size: int
    avg_quality_score: float
    median_quality_score: float
    health_status: str  # HEALTHY | DEGRADED | CRITICAL

    # Distribution
    score_distribution: List[ScoreDistribution]
    quality_tiers: List[QualityTierSummary]

    # Quick stats
    total_red_flags: int
    degraded_count: int
    insufficient_count: int
    fundamentals_coverage_pct: float

    # Top/bottom
    top_5: List[ScanResultResponse]
    bottom_5: List[ScanResultResponse]

    # Provenance
    scoring_config_version: Optional[str] = None
    scoring_config_hash: Optional[str] = None


class ScanResultSortableResponse(BaseModel):
    """
    Extended scan result with sort-friendly fields for the screener table.

    All fields the Next.js DataTable needs for client-side sorting/filtering.
    """
    symbol: str
    rank: int
    quality_score: float
    quality_tier: str               # HIGH / MEDIUM / LOW / INSUFFICIENT
    data_quality: str               # FULL / DEGRADED / INSUFFICIENT

    # Sub-scores (flat for table columns)
    profitability: float
    cash_quality: float
    balance_sheet: float
    stability: float
    shareholder_return: float

    # Risk
    liquidity_score: Optional[float] = None
    confidence_penalty: Optional[float] = None
    red_flag_count: int = 0
    top_red_flag: Optional[str] = None

    # Returns
    trailing_returns: TrailingReturns

    # Reasons (truncated for table)
    top_reason: Optional[str] = None


class ScanResultTableResponse(BaseModel):
    """Paginated, sortable scan results for the screener table."""
    run_id: int
    as_of_date: date
    universe_name: str
    total: int
    page: int
    page_size: int
    sort_by: str
    sort_dir: str
    results: List[ScanResultSortableResponse]
