/**
 * Validated API Services
 * 
 * Type-safe API calls with runtime validation.
 * Uses Zod schemas to ensure data integrity.
 */

import { api } from './client';
import {
  StockSchema,
  StockListResponseSchema,
  MarketSummarySchema,
  MarketRegimeSchema,
  RecommendationSchema,
  DataMetaSchema,
  validateApiResponse,
  type Stock,
  type MarketSummary,
  type MarketRegime,
  type Recommendation,
  type DataMeta,
} from './schemas';
import { z } from 'zod';

// === STOCKS SERVICE ===

// Result type that includes meta for simulation tracking
export interface StockListResult {
  stocks: Stock[];
  meta: DataMeta | null;
}

export const stocksService = {
  async getAll(params?: { sector?: string; liquidity?: string }): Promise<Stock[]> {
    const result = await this.getAllWithMeta(params);
    return result.stocks;
  },

  async getAllWithMeta(params?: { sector?: string; liquidity?: string }): Promise<StockListResult> {
    const queryParams = new URLSearchParams();
    if (params?.sector) queryParams.append('sector', params.sector);
    if (params?.liquidity) queryParams.append('liquidity', params.liquidity);
    
    const endpoint = `/stocks/${queryParams.toString() ? '?' + queryParams : ''}`;
    const response = await api.get<unknown>(endpoint);
    
    const validated = validateApiResponse(StockListResponseSchema, response, 'stocks.getAll');
    return {
      stocks: validated.data,
      meta: validated.meta || null,
    };
  },

  async get(symbol: string): Promise<Stock> {
    const response = await api.get<unknown>(`/stocks/${symbol}`);
    
    const schema = z.object({
      success: z.boolean(),
      data: StockSchema,
      source: z.string(),
      cached: z.boolean().optional(),
    });
    
    const validated = validateApiResponse(schema, response, `stocks.get(${symbol})`);
    return validated.data;
  },

  async getMarketSummary(): Promise<MarketSummary> {
    const response = await api.get<unknown>('/stocks/market-summary');
    
    const schema = z.object({
      success: z.boolean(),
      data: MarketSummarySchema,
      source: z.string(),
    });
    
    const validated = validateApiResponse(schema, response, 'stocks.getMarketSummary');
    return validated.data;
  },

  async getSectors(): Promise<string[]> {
    const response = await api.get<{ success: boolean; sectors: string[] }>('/stocks/sectors');
    return response.sectors;
  },

  async search(query: string): Promise<Stock[]> {
    const response = await api.get<unknown>(`/stocks/search?q=${encodeURIComponent(query)}`);
    
    const schema = z.object({
      success: z.boolean(),
      query: z.string(),
      count: z.number(),
      data: z.array(StockSchema),
    });
    
    const validated = validateApiResponse(schema, response, `stocks.search(${query})`);
    return validated.data;
  },

  async getIndicators(symbol: string): Promise<Record<string, unknown>> {
    const response = await api.get<{ success: boolean; symbol: string; indicators: Record<string, unknown>; source: string }>(
      `/stocks/${symbol}/indicators`
    );
    return response.indicators;
  },
};

// === RECOMMENDATIONS SERVICE ===

export const recommendationsService = {
  async getTop(params?: {
    horizon?: 'short_term' | 'swing' | 'long_term';
    action?: string;
    sector?: string;
    minLiquidity?: string;
    limit?: number;
  }): Promise<Recommendation[]> {
    const queryParams = new URLSearchParams();
    if (params?.horizon) queryParams.append('horizon', params.horizon);
    if (params?.action) queryParams.append('action', params.action);
    if (params?.sector) queryParams.append('sector', params.sector);
    if (params?.minLiquidity) queryParams.append('min_liquidity', params.minLiquidity);
    if (params?.limit) queryParams.append('limit', params.limit.toString());
    
    const endpoint = `/recommendations${queryParams.toString() ? '?' + queryParams : ''}`;
    const response = await api.get<unknown>(endpoint);
    
    const schema = z.object({
      data: z.array(RecommendationSchema),
    });
    
    const validated = validateApiResponse(schema, response, 'recommendations.getTop');
    return validated.data;
  },

  async getBuys(
    horizon: 'short_term' | 'swing' | 'long_term' = 'swing',
    limit = 5
  ): Promise<Recommendation[]> {
    const response = await api.get<unknown>(
      `/recommendations/buy?horizon=${horizon}&limit=${limit}`
    );
    
    const schema = z.object({ data: z.array(RecommendationSchema) });
    const validated = validateApiResponse(schema, response, 'recommendations.getBuys');
    return validated.data;
  },

  async getSells(
    horizon: 'short_term' | 'swing' | 'long_term' = 'swing',
    limit = 5
  ): Promise<Recommendation[]> {
    const response = await api.get<unknown>(
      `/recommendations/sell?horizon=${horizon}&limit=${limit}`
    );
    
    const schema = z.object({ data: z.array(RecommendationSchema) });
    const validated = validateApiResponse(schema, response, 'recommendations.getSells');
    return validated.data;
  },

  async get(
    symbol: string,
    horizon: 'short_term' | 'swing' | 'long_term' = 'swing',
    userLevel: 'beginner' | 'intermediate' | 'advanced' = 'beginner'
  ): Promise<Recommendation> {
    const response = await api.get<unknown>(
      `/recommendations/${symbol}?horizon=${horizon}&user_level=${userLevel}`
    );
    
    const schema = z.object({
      success: z.boolean(),
      data: RecommendationSchema,
    });
    
    const validated = validateApiResponse(schema, response, `recommendations.get(${symbol})`);
    return validated.data;
  },

  async getMarketRegime(): Promise<MarketRegime> {
    const response = await api.get<unknown>('/recommendations/market-regime');
    
    const schema = z.object({
      success: z.boolean(),
      data: MarketRegimeSchema,
    });
    
    const validated = validateApiResponse(schema, response, 'recommendations.getMarketRegime');
    return validated.data;
  },
};

// Combined export for easy migration
export const validatedApi = {
  stocks: stocksService,
  recommendations: recommendationsService,
};
