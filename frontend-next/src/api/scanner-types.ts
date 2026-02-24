/**
 * TypeScript types mirroring backend Pydantic schemas for the NGX Quality Scanner.
 * 
 * These match the response contracts from:
 *   GET /api/v1/scanner/dashboard
 *   GET /api/v1/scanner/table
 *   GET /api/v1/scanner/explain/{symbol}
 *   GET /api/v1/scanner/runs
 *   GET /api/v1/scanner/runs/{id}
 *   GET /api/v1/scanner/runs/{id}/results
 *   GET /api/v1/scanner/health
 */

// ── Trailing Returns ────────────────────────────────────────────────

export interface TrailingReturns {
  tri_1y_ngn: number | null;
  tri_3y_ngn: number | null;
  tri_1y_usd: number | null;
  tri_3y_usd: number | null;
  tri_1y_real: number | null;
  tri_3y_real: number | null;
}

// ── Scan Result (base) ─────────────────────────────────────────────

export interface ScanResultResponse {
  symbol: string;
  rank: number;
  quality_score: number;
  sub_scores: Record<string, number> | null;
  reasons: string[] | null;
  red_flags: string[] | null;
  flags: Record<string, unknown> | null;
  liquidity_score: number | null;
  confidence_penalty: number | null;
  trailing_returns: TrailingReturns | null;
}

// ── Dashboard ───────────────────────────────────────────────────────

export interface ScoreDistribution {
  bucket: string;
  count: number;
}

export interface QualityTierSummary {
  tier: string;
  min_score: number;
  max_score: number;
  count: number;
  symbols: string[];
}

export interface ScannerDashboardResponse {
  last_scan_date: string | null;
  last_scan_run_id: number | null;
  universe_name: string;
  universe_size: number;
  avg_quality_score: number;
  median_quality_score: number;
  health_status: string;
  score_distribution: ScoreDistribution[];
  quality_tiers: QualityTierSummary[];
  total_red_flags: number;
  degraded_count: number;
  insufficient_count: number;
  fundamentals_coverage_pct: number;
  top_5: ScanResultResponse[];
  bottom_5: ScanResultResponse[];
  scoring_config_version: string | null;
  scoring_config_hash: string | null;
}

// ── Table (Sortable) ────────────────────────────────────────────────

export interface ScanResultSortable {
  symbol: string;
  rank: number;
  quality_score: number;
  quality_tier: string;
  data_quality: string;
  profitability: number;
  cash_quality: number;
  balance_sheet: number;
  stability: number;
  shareholder_return: number;
  liquidity_score: number | null;
  confidence_penalty: number | null;
  red_flag_count: number;
  top_red_flag: string | null;
  trailing_returns: TrailingReturns;
  top_reason: string | null;
}

export interface ScanResultTableResponse {
  run_id: number;
  as_of_date: string;
  universe_name: string;
  total: number;
  page: number;
  page_size: number;
  sort_by: string;
  sort_dir: string;
  results: ScanResultSortable[];
}

// ── Explain ─────────────────────────────────────────────────────────

export interface MetricExplanation {
  metric_name: string;
  raw_value: number | null;
  winsorized_value: number | null;
  percentile_rank: number;
  component_score: number;
  max_possible: number;
  direction: string;
}

export interface GuardrailTrigger {
  name: string;
  triggered: boolean;
  cap_value: number | null;
  score_before: number;
  score_after: number;
  reason: string;
}

export interface ConfidencePenaltyBreakdown {
  total: number;
  missing_fields: string[];
  missing_fields_penalty: number;
  staleness_days: number | null;
  staleness_penalty: number;
  liquidity_score: number;
  liquidity_penalty: number;
}

export interface WinsorBounds {
  metric_name: string;
  lower_bound: number | null;
  upper_bound: number | null;
  universe_size: number;
  non_null_count: number;
}

export interface ScoreExplanationResponse {
  symbol: string;
  quality_score: number;
  scoring_config_version: string;
  scoring_config_hash: string;
  metric_explanations: MetricExplanation[];
  guardrail_triggers: GuardrailTrigger[];
  confidence_breakdown: ConfidencePenaltyBreakdown;
  winsor_bounds: WinsorBounds[];
  derived_metrics_snapshot: Record<string, unknown>;
  dividend_years: number;
  data_quality: string;
  red_flags: string[];
  reasons: string[];
}

// ── Runs ────────────────────────────────────────────────────────────

export interface ScanRunResponse {
  id: number;
  as_of_date: string;
  universe_name: string;
  symbols_scanned: number;
  symbols_ranked: number;
  created_at: string;
  summary: Record<string, unknown> | null;
}

export interface ScanRunListResponse {
  total: number;
  runs: ScanRunResponse[];
}

export interface ScanResultListResponse {
  run_id: number;
  as_of_date: string;
  universe_name: string;
  total: number;
  results: ScanResultResponse[];
}

// ── Health ──────────────────────────────────────────────────────────

export interface DataCoverage {
  total_universe: number;
  with_fundamentals: number;
  with_tri: number;
  with_fx: boolean;
  with_cpi: boolean;
  fundamentals_coverage_pct: number;
  tri_coverage_pct: number;
}

export interface Staleness {
  last_scan_ts: string | null;
  last_scan_age_hours: number | null;
  last_fundamentals_import_ts: string | null;
  fx_latest_date: string | null;
  cpi_latest_date: string | null;
  fx_staleness_days: number | null;
  cpi_staleness_days: number | null;
}

export interface Anomaly {
  anomaly_type: string;
  description: string;
  severity: string;
}

export interface ScannerHealthResponse {
  status: string;
  last_scan_ts: string | null;
  data_coverage: DataCoverage;
  staleness: Staleness;
  anomalies: Anomaly[];
  recommendations: string[];
}
