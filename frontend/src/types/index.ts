/**
 * NSE Trader Type Definitions
 * 
 * Centralized type definitions matching the backend API.
 * Single source of truth for all data structures.
 */

// ============================================
// STOCK TYPES
// ============================================

export interface Stock {
  symbol: string;
  name: string;
  sector: string;
  price: number;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  change: number;
  change_percent: number;
  volume: number;
  market_cap_billions?: number;
  pe_ratio?: number;
  dividend_yield?: number;
  eps?: number;
  liquidity_tier?: LiquidityTier;
  liquidity_score?: number;
  is_active?: boolean;
  source: string;
  timestamp: string;
}

export type LiquidityTier = 'high' | 'medium' | 'low' | 'very_low';

export interface StockWithIndicators extends Stock {
  indicators?: TechnicalIndicators;
  signals?: Signal[];
}

// ============================================
// TECHNICAL INDICATORS
// ============================================

export interface TechnicalIndicators {
  rsi?: number;
  rsi_signal?: 'oversold' | 'neutral' | 'overbought';
  macd?: number;
  macd_signal?: number;
  macd_histogram?: number;
  macd_trend?: 'bullish' | 'bearish' | 'neutral';
  sma_20?: number;
  sma_50?: number;
  sma_200?: number;
  ema_12?: number;
  ema_26?: number;
  atr?: number;
  atr_percent?: number;
  adx?: number;
  adx_trend?: 'strong' | 'moderate' | 'weak' | 'no_trend';
  bollinger_upper?: number;
  bollinger_middle?: number;
  bollinger_lower?: number;
  bollinger_position?: 'above' | 'within' | 'below';
  obv?: number;
  volume_ratio?: number;
}

export interface Signal {
  name: string;
  type: 'trend' | 'momentum' | 'volatility' | 'volume';
  direction: 'bullish' | 'bearish' | 'neutral';
  strength: number; // 0-1
  description: string;
}

// ============================================
// RECOMMENDATIONS
// ============================================

export type RecommendationAction = 
  | 'STRONG_BUY' 
  | 'BUY' 
  | 'HOLD' 
  | 'SELL' 
  | 'STRONG_SELL' 
  | 'AVOID';

export type TimeHorizon = 'short_term' | 'swing' | 'long_term';

export type UserLevel = 'beginner' | 'intermediate' | 'advanced';

export interface Recommendation {
  symbol: string;
  name: string;
  action: RecommendationAction;
  horizon: TimeHorizon;
  confidence: number; // 0-100
  current_price: number;
  primary_reason: string;
  supporting_reasons: string[];
  risk_warnings: string[];
  explanation: string;
  user_explanation?: string;
  liquidity_score: number;
  liquidity_warning?: string;
  market_regime: MarketRegimeType;
  risk_level: RiskLevel;
  volatility: number;
  entry_exit?: EntryExitPoints;
  signals: Signal[];
  timestamp: string;
  valid_until?: string;
}

export interface EntryExitPoints {
  entry_price: number;
  stop_loss: number;
  target_1: number;
  target_2?: number;
  target_3?: number;
  risk_reward: number;
}

// ============================================
// MARKET DATA
// ============================================

export type MarketRegimeType = 
  | 'bull' 
  | 'bear' 
  | 'range_bound' 
  | 'high_volatility' 
  | 'low_liquidity' 
  | 'crisis';

export type RiskLevel = 'low' | 'moderate' | 'high' | 'very_high';

export interface MarketRegime {
  regime: MarketRegimeType;
  trend: 'up' | 'down' | 'sideways';
  confidence: number;
  duration_days: number;
  recommended_strategy: string;
  position_size_modifier: number;
  risk_adjustment: string;
  sectors_to_favor: string[];
  sectors_to_avoid: string[];
  warnings: string[];
  metrics: {
    asi_vs_sma_50: number;
    asi_vs_sma_200: number;
    volatility_percentile: number;
    breadth_ratio: number;
  };
}

export interface MarketSummary {
  asi: {
    value: number;
    change: number;
    change_percent: number;
    trend?: 'up' | 'down' | 'sideways';
  };
  breadth: {
    advancing: number;
    declining: number;
    unchanged: number;
    ratio: number;
  };
  volume: {
    total_volume: number;
    total_value: number;
    vs_average?: number;
  };
  sectors: SectorPerformance[];
  stock_count: number;
  timestamp: string;
}

export interface SectorPerformance {
  name: string;
  change_percent: number;
  volume: number;
  leading_stock?: string;
  trend: 'Leading' | 'Improving' | 'Lagging' | 'Weakening';
}

// ============================================
// API RESPONSE TYPES
// ============================================

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  source?: string;
  cached?: boolean;
  timestamp?: string;
  error?: string;
}

export interface ListResponse<T> {
  success: boolean;
  count: number;
  data: T[];
  source?: string;
}

// ============================================
// UI STATE TYPES
// ============================================

export interface FilterState {
  searchTerm: string;
  sector: string | null;
  liquidityTier: LiquidityTier | null;
  priceRange: { min: number | null; max: number | null };
  changeFilter: 'all' | 'positive' | 'negative';
  sortBy: keyof Stock;
  sortDirection: 'asc' | 'desc';
}

export interface ViewPreferences {
  theme: 'dark' | 'light';
  userLevel: UserLevel;
  defaultHorizon: TimeHorizon;
  showTechnicals: boolean;
  compactMode: boolean;
}

// ============================================
// UTILITY TYPES
// ============================================

export type LoadingState = 'idle' | 'loading' | 'success' | 'error';

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  lastUpdated: string | null;
}
