/**
 * Zod Schemas for API Response Validation
 * 
 * Runtime validation ensures data integrity and provides
 * helpful error messages when API contracts are violated.
 */

import { z } from 'zod';

// === STOCK SCHEMAS ===

export const StockSchema = z.object({
  symbol: z.string(),
  name: z.string(),
  price: z.number(),
  open: z.number().optional(),
  high: z.number().optional(),
  low: z.number().optional(),
  close: z.number().optional(),
  change: z.number().optional().nullable(),
  change_percent: z.number().optional().nullable(),
  volume: z.number().optional().nullable(),
  market_cap: z.number().optional().nullable(),
  sector: z.string().optional().nullable(),
  pe_ratio: z.number().optional().nullable(),
  eps: z.number().optional().nullable(),
  dividend_yield: z.number().optional().nullable(),
  liquidity_tier: z.enum(['high', 'medium', 'low']).optional().nullable(),
  source: z.string(),
  timestamp: z.string(),
  recommendation: z.string().optional(),
  buy_signals: z.number().optional(),
  sell_signals: z.number().optional(),
  neutral_signals: z.number().optional(),
  shares_outstanding: z.number().optional(),
  is_active: z.boolean().optional(),
});

export type Stock = z.infer<typeof StockSchema>;

// === DATA SOURCE META SCHEMAS ===

export const SourceBreakdownSchema = z.object({
  ngx_official: z.number(),
  apt_securities: z.number(),
  kwayisi: z.number(),
  simulated: z.number(),
  total: z.number(),
});

export const DataMetaSchema = z.object({
  source_breakdown: SourceBreakdownSchema,
  is_simulated: z.boolean(),
  simulated_count: z.number(),
  simulated_symbols: z.array(z.string()),
  last_updated: z.string(),
  fetch_time_ms: z.number(),
});

export type SourceBreakdown = z.infer<typeof SourceBreakdownSchema>;
export type DataMeta = z.infer<typeof DataMetaSchema>;

export const StockListResponseSchema = z.object({
  success: z.boolean(),
  count: z.number(),
  data: z.array(StockSchema),
  source: z.string(),
  meta: DataMetaSchema.optional().nullable(),
});

// === MARKET SUMMARY SCHEMAS ===

export const MarketSummarySchema = z.object({
  asi: z.object({
    value: z.number(),
    change: z.number(),
    change_percent: z.number(),
    trend: z.string().optional(),
  }),
  breadth: z.object({
    advancing: z.number(),
    declining: z.number(),
    unchanged: z.number(),
    ratio: z.number(),
  }),
  volume: z.object({
    total_volume: z.number(),
    total_value: z.number(),
  }),
  sectors: z.array(z.object({
    name: z.string(),
    change_percent: z.number(),
    volume: z.number(),
  })).optional(),
  stock_count: z.number(),
  timestamp: z.string(),
});

export type MarketSummary = z.infer<typeof MarketSummarySchema>;

// === MARKET REGIME SCHEMAS ===

export const MarketRegimeSchema = z.object({
  regime: z.string(),
  trend: z.string(),
  confidence: z.number(),
  duration_days: z.number().optional().default(0),
  recommended_strategy: z.string().optional().default(''),
  position_size_modifier: z.number().optional().default(1.0),
  risk_adjustment: z.union([z.string(), z.number()]).optional().default(''),
  sectors_to_favor: z.array(z.string()).optional().default([]),
  sectors_to_avoid: z.array(z.string()).optional().default([]),
  warnings: z.array(z.string()).optional().default([]),
  metrics: z.object({
    asi_vs_sma_50: z.number(),
    asi_vs_sma_200: z.number(),
    volatility_percentile: z.number(),
    breadth_ratio: z.number(),
  }).optional().default({ asi_vs_sma_50: 0, asi_vs_sma_200: 0, volatility_percentile: 0, breadth_ratio: 0 }),
});

export type MarketRegime = z.infer<typeof MarketRegimeSchema>;

// === RECOMMENDATION SCHEMAS ===

export const SignalSchema = z.object({
  name: z.string(),
  type: z.string(),
  direction: z.string(),
  strength: z.number(),
  description: z.string(),
});

export const EntryExitSchema = z.object({
  entry_price: z.number(),
  stop_loss: z.number(),
  target_1: z.number(),
  target_2: z.number().optional(),
  risk_reward: z.number(),
});

export const RecommendationSchema = z.object({
  symbol: z.string(),
  name: z.string(),
  action: z.enum(['STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL', 'AVOID']),
  horizon: z.enum(['short_term', 'swing', 'long_term']),
  confidence: z.number(),
  current_price: z.number(),
  primary_reason: z.string(),
  supporting_reasons: z.array(z.string()),
  risk_warnings: z.array(z.string()),
  explanation: z.string(),
  liquidity_score: z.number(),
  liquidity_warning: z.string().nullable().optional(),
  market_regime: z.string(),
  risk_level: z.string(),
  volatility: z.number(),
  entry_exit: EntryExitSchema.nullable().optional(),
  signals: z.array(SignalSchema),
  timestamp: z.string(),
  valid_until: z.string().nullable().optional(),
  user_explanation: z.string().nullable().optional(),
  confidence_score: z.number().optional(),
  data_confidence: z.object({
    confidence_score: z.number(),
    status: z.string(),
    suppression_reason: z.string().optional(),
    primary_source: z.string().optional(),
    secondary_source: z.string().optional(),
    divergence_pct: z.number().optional(),
  }).optional(),
}).transform((data) => ({
  ...data,
  // Normalize null to undefined for compatibility
  liquidity_warning: data.liquidity_warning ?? undefined,
  entry_exit: data.entry_exit ?? undefined,
  valid_until: data.valid_until ?? undefined,
  user_explanation: data.user_explanation ?? undefined,
}));

export type Recommendation = z.infer<typeof RecommendationSchema>;

export const RecommendationListResponseSchema = z.object({
  data: z.array(RecommendationSchema),
});

// === API RESPONSE WRAPPERS ===

export const ApiResponseSchema = <T extends z.ZodTypeAny>(dataSchema: T) =>
  z.object({
    success: z.boolean(),
    data: dataSchema,
    source: z.string().optional(),
    cached: z.boolean().optional(),
  });

// === VALIDATION HELPERS ===

export function validateApiResponse<T>(
  schema: z.ZodType<T>,
  data: unknown,
  context: string
): T {
  const result = schema.safeParse(data);
  
  if (!result.success) {
    const errors = result.error.issues.map((e) => `${e.path.join('.')}: ${e.message}`);
    
    if (import.meta.env.DEV) {
      console.error(`[API Validation] ${context} failed:`, errors);
      console.error('[API Validation] Received data:', data);
    }
    
    // In production, log but don't crash - try to use data anyway
    console.warn(`API validation warning for ${context}:`, errors.slice(0, 3));
    return data as T;
  }
  
  return result.data;
}

export function safeValidate<T>(
  schema: z.ZodType<T>,
  data: unknown
): { success: true; data: T } | { success: false; errors: string[] } {
  const result = schema.safeParse(data);
  
  if (result.success) {
    return { success: true, data: result.data };
  }
  
  return {
    success: false,
    errors: result.error.issues.map((e) => `${e.path.join('.')}: ${e.message}`),
  };
}
