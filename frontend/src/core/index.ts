/**
 * Core module exports
 * 
 * Centralized exports for:
 * - API client
 * - Error handling
 * - UI primitives
 * - Validation schemas
 */

// API
export { api, apiRequest, ApiError, NetworkError, TimeoutError, API_BASE_URL } from './api/client';
export { stocksService, recommendationsService, validatedApi } from './api/services';

// Schemas & Validation
export {
  StockSchema,
  StockListResponseSchema,
  MarketSummarySchema,
  MarketRegimeSchema,
  RecommendationSchema,
  RecommendationListResponseSchema,
  validateApiResponse,
  safeValidate,
  type Stock,
  type MarketSummary,
  type MarketRegime,
  type Recommendation,
} from './api/schemas';

// Errors
export { default as ErrorBoundary } from './errors/ErrorBoundary';

// UI Primitives
export { default as EmptyState } from './ui/EmptyState';
export { default as LoadingState, SkeletonCard, SkeletonTable, SkeletonList } from './ui/LoadingState';
