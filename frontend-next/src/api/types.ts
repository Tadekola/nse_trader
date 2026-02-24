/**
 * TypeScript interfaces matching backend API response contracts.
 * Every type here corresponds to a tested backend endpoint.
 */

// ── Quality Flags ───────────────────────────────────────────────────

export type DataMode = "TRI_FULL" | "PRICE_ONLY";
export type FxMode = "FX_FULL" | "FX_MISSING" | "FX_NOT_REQUESTED";
export type InflationMode = "CPI_FULL" | "CPI_MISSING" | "CPI_NOT_REQUESTED";
export type OverallQuality = "FULL" | "DEGRADED";
export type ReportingMode = "NGN" | "USD" | "REAL_NGN";

export interface QualityFlags {
  data_mode: DataMode;
  fx_mode: FxMode;
  inflation_mode: InflationMode;
  overall_quality: OverallQuality;
}

// ── Health ──────────────────────────────────────────────────────────

export type HealthStatus = "OK" | "RECOVERING" | "DEGRADED" | "SAFE_MODE";

export interface SourceHealth {
  source: string;
  status: string;
  last_success: string | null;
  last_failure: string | null;
  consecutive_failures: number;
  circuit_state: string;
  never_called: boolean;
}

export interface HealthResponse {
  overall_status: HealthStatus;
  sources: SourceHealth[];
}

// ── Portfolio ───────────────────────────────────────────────────────

export interface Portfolio {
  id: number;
  name: string;
  description: string | null;
  base_currency: string;
  created_at: string;
}

export interface PortfolioList {
  total: number;
  limit: number;
  offset: number;
  data: Portfolio[];
}

// ── Holdings ────────────────────────────────────────────────────────

export interface Position {
  symbol: string;
  quantity: number;
  avg_cost_ngn: number;
  total_cost_ngn: number;
  price_ngn: number | null;
  market_value_ngn: number;
  gain_loss_ngn: number;
  gain_loss_pct: number;
  price_available: boolean;
}

export interface HoldingsResponse {
  as_of: string;
  holdings: Record<string, { symbol: string; quantity: number; avg_cost_ngn: number; total_cost_ngn: number }>;
  cash_ngn: number;
  total_invested_ngn: number;
  symbols: string[];
  num_positions: number;
  valuation: {
    as_of: string;
    holdings_value_ngn: number;
    cash_ngn: number;
    total_value_ngn: number;
    positions: Position[];
    data_quality: string;
  };
}

// ── Summary ─────────────────────────────────────────────────────────

export interface ReturnWindow {
  label: string;
  value: number | null;
  annualized: number | null;
  start_date: string | null;
  end_date: string | null;
  available: boolean;
}

export interface HoldingDetail {
  symbol: string;
  shares: number;
  market_value_ngn: number;
  market_value_reporting: number | null;
  weight: number;
  tri_quality: string;
  avg_cost_ngn: number;
  gain_loss_pct: number;
}

export interface ConcentrationMetrics {
  hhi: number;
  max_position_weight: number;
  max_position_symbol: string | null;
  num_positions: number;
}

export interface DataFreshness {
  last_price_date: string | null;
  last_fx_date: string | null;
  last_cpi_date: string | null;
  last_action_date: string | null;
}

export interface SummaryResponse {
  portfolio_id: number;
  as_of: string;
  reporting: ReportingMode;
  value_ngn: number;
  value_reporting: number | null;
  cash_ngn: number;
  holdings_value_ngn: number;
  total_invested_ngn: number;
  returns: ReturnWindow[];
  current_drawdown: number | null;
  top_holdings: HoldingDetail[];
  concentration: ConcentrationMetrics;
  freshness: DataFreshness;
  quality: QualityFlags;
  provenance: Record<string, unknown>;
}

// ── Timeseries ──────────────────────────────────────────────────────

export interface TimeseriesPoint {
  date: string;
  value: number | null;
  value_ngn: number;
  cumulative_return: number | null;
  drawdown: number;
  rolling_vol_30d: number | null;
}

export interface TimeseriesResponse {
  reporting: ReportingMode;
  start_date: string;
  end_date: string;
  num_points: number;
  quality: QualityFlags;
  series: TimeseriesPoint[];
  provenance: Record<string, unknown>;
}

// ── Performance ─────────────────────────────────────────────────────

export interface PerformanceMetrics {
  twr: number | null;
  twr_annualized: number | null;
  mwr: number | null;
  cagr: number | null;
  volatility_daily: number | null;
  volatility_annualized: number | null;
  max_drawdown: number | null;
  max_drawdown_start: string | null;
  max_drawdown_end: string | null;
  sharpe_ratio: number | null;
  total_return: number | null;
  start_value: number | null;
  end_value: number | null;
  num_days: number;
}

export interface PerformanceResponse {
  reporting_mode: ReportingMode;
  metrics: PerformanceMetrics;
  quality: QualityFlags;
  series: Array<{ date: string; value: number | null; value_ngn: number; daily_return: number | null }>;
  provenance: Record<string, unknown>;
}

// ── Decomposition ───────────────────────────────────────────────────

export interface DecompositionDay {
  date: string;
  total_return: number;
  equity_component: number | null;
  fx_component: number | null;
  inflation_component: number | null;
}

export interface DecompositionResponse {
  reporting: ReportingMode;
  series: DecompositionDay[];
  summary: {
    total_return: number;
    equity_component: number | null;
    fx_component: number | null;
    inflation_component: number | null;
  };
  quality: QualityFlags;
  provenance: Record<string, unknown>;
}

// ── Stocks / Screener ────────────────────────────────────────────────

export interface Stock {
  symbol: string;
  name: string;
  price: number;
  change: number | null;
  change_percent: number | null;
  volume: number | null;
  market_cap: number | null;
  sector: string | null;
  pe_ratio: number | null;
  dividend_yield: number | null;
  liquidity_tier: string | null;
  source: string;
  timestamp: string;
}

export interface StockListResponse {
  success: boolean;
  count: number;
  data: Stock[];
  source: string;
  contains_simulated: boolean;
  simulated_symbols: string[];
  meta: Record<string, unknown> | null;
}

export interface TechnicalIndicators {
  [key: string]: unknown;
}

// ── Recommendations ─────────────────────────────────────────────────

export interface BiasSignal {
  bias_direction: string;
  bias_probability: number | null;
  indicator_agreement: number;
  signal_magnitude: number;
  data_confidence_factor: number;
  reasoning: string;
  is_suppressed: boolean;
  suppression_reason: string | null;
}

export interface Recommendation {
  symbol: string;
  name: string;
  action: string;
  horizon: string;
  confidence: number;
  current_price: number;
  primary_reason: string;
  supporting_reasons: string[];
  risk_warnings: string[];
  explanation: string;
  status: string;
  confidence_score: number;
  suppression_reason: string | null;
  bias_direction: string;
  bias_probability: number | null;
  bias_label: string;
  bias_signal: BiasSignal | null;
  probabilistic_reasoning: string | null;
  // Entry/exit points (may be present)
  entry_price?: number;
  entry_zone_low?: number;
  entry_zone_high?: number;
  stop_loss?: number;
  stop_loss_percent?: number;
  target_1?: number;
  target_2?: number | null;
  target_3?: number | null;
  risk_reward_ratio?: number;
  // Risk
  risk_level?: string;
  volatility?: number;
  max_drawdown?: number;
  liquidity_score?: number;
  liquidity_warning?: string | null;
  // Market context
  market_regime?: string;
  regime_adjustment?: string;
  sector_context?: string | null;
  corporate_action_alert?: string | null;
  [key: string]: unknown;
}

export interface RecommendationListResponse {
  success: boolean;
  count: number;
  horizon: string;
  suppressed_count: number;
  data: Recommendation[];
}

export interface RecommendationResponse {
  success: boolean;
  data: Recommendation;
}

// ── Market Data ─────────────────────────────────────────────────────

export interface TrendingStock {
  symbol: string;
  company_name: string;
  sector: string;
  last_close: number;
  todays_close: number;
  change: number;
  change_percent: number;
  rank: number;
}

export interface MarketSnapshot {
  asi_value?: number;
  asi_change?: number;
  asi_change_percent?: number;
  volume?: number;
  value?: number;
  market_cap?: number;
  deals?: number;
  [key: string]: unknown;
}

export interface MarketRegime {
  regime: string;
  confidence: number;
  trend_direction: string;
  reasoning: string;
  warnings: string[];
}

export interface TrendingResponse {
  success: boolean;
  date: string;
  top_gainers: TrendingStock[];
  top_losers: TrendingStock[];
  biggest_gainer: Record<string, unknown> | null;
  biggest_loser: Record<string, unknown> | null;
}

export interface MarketSummaryResponse {
  success: boolean;
  snapshot: MarketSnapshot | null;
  trending: { date: string; top_gainers: TrendingStock[]; top_losers: TrendingStock[] } | null;
  breadth: Record<string, unknown> | null;
  regime: MarketRegime | null;
  source: string;
  timestamp: string;
}

// ── Audit ───────────────────────────────────────────────────────────

export interface AuditEvent {
  id: number;
  component: string;
  event_type: string;
  level: string;
  message: string;
  payload: Record<string, unknown> | null;
  ts: string;
}

export interface AuditList {
  total: number;
  limit: number;
  offset: number;
  data: AuditEvent[];
}

// ── Transactions ────────────────────────────────────────────────────

export interface Transaction {
  id: number;
  portfolio_id: number;
  ts: string;
  tx_type: string;
  symbol: string | null;
  quantity: number | null;
  price_ngn: number | null;
  amount_ngn: number;
  fees_ngn: number;
  notes: string | null;
}

export interface TransactionList {
  total: number;
  limit: number;
  offset: number;
  data: Transaction[];
}
