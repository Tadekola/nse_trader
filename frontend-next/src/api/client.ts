/**
 * Typed API client for NSE Trader backend.
 * 
 * All calls go through Next.js rewrites → localhost:8000.
 * Every function returns typed data matching backend contracts.
 */

import type {
  AuditList,
  DecompositionResponse,
  HealthResponse,
  HoldingsResponse,
  MarketSummaryResponse,
  PerformanceResponse,
  Portfolio,
  PortfolioList,
  RecommendationListResponse,
  RecommendationResponse,
  ReportingMode,
  StockListResponse,
  SummaryResponse,
  TechnicalIndicators,
  TimeseriesResponse,
  TransactionList,
} from "./types";

import { emitToast } from "./toast-bridge";

const BASE = "/api/v1";

async function fetchJSON<T>(url: string, timeoutMs = 60_000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      const msg = body
        ? `API ${res.status}: ${body.slice(0, 200)}`
        : `API request failed (${res.status})`;
      emitToast(msg, "error");
      throw new Error(msg);
    }
    return res.json() as Promise<T>;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      emitToast("Request timed out — server may be unavailable", "warning");
      throw new Error("Request timed out");
    }
    if (err instanceof TypeError && err.message.includes("fetch")) {
      emitToast("Network error — cannot reach server", "error");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

// ── Health ──────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthResponse> {
  return fetchJSON<HealthResponse>(`${BASE}/health/sources`);
}

// ── Portfolios ──────────────────────────────────────────────────────

export async function listPortfolios(
  limit = 50,
  offset = 0,
): Promise<PortfolioList> {
  return fetchJSON<PortfolioList>(
    `${BASE}/portfolios?limit=${limit}&offset=${offset}`,
  );
}

export async function getPortfolio(id: number): Promise<Portfolio> {
  return fetchJSON<Portfolio>(`${BASE}/portfolios/${id}`);
}

export async function deletePortfolio(
  id: number,
): Promise<{ deleted: boolean; portfolio_id: number }> {
  const res = await fetch(`${BASE}/portfolios/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Delete portfolio failed (${res.status}): ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<{ deleted: boolean; portfolio_id: number }>;
}

// ── Holdings ────────────────────────────────────────────────────────

export async function getHoldings(
  portfolioId: number,
  asOf?: string,
): Promise<HoldingsResponse> {
  const params = asOf ? `?as_of=${asOf}` : "";
  return fetchJSON<HoldingsResponse>(
    `${BASE}/portfolios/${portfolioId}/holdings${params}`,
  );
}

// ── Summary ─────────────────────────────────────────────────────────

export async function getSummary(
  portfolioId: number,
  reporting: ReportingMode = "NGN",
  asOf?: string,
): Promise<SummaryResponse> {
  const params = new URLSearchParams({ reporting });
  if (asOf) params.set("as_of", asOf);
  return fetchJSON<SummaryResponse>(
    `${BASE}/portfolios/${portfolioId}/summary?${params}`,
  );
}

// ── Timeseries ──────────────────────────────────────────────────────

export async function getTimeseries(
  portfolioId: number,
  reporting: ReportingMode = "NGN",
  start?: string,
  end?: string,
): Promise<TimeseriesResponse> {
  const params = new URLSearchParams({ reporting });
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  return fetchJSON<TimeseriesResponse>(
    `${BASE}/portfolios/${portfolioId}/timeseries?${params}`,
  );
}

// ── Performance ─────────────────────────────────────────────────────

export async function getPerformance(
  portfolioId: number,
  reporting: ReportingMode = "NGN",
  startDate?: string,
  endDate?: string,
): Promise<PerformanceResponse> {
  const params = new URLSearchParams({ reporting });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  return fetchJSON<PerformanceResponse>(
    `${BASE}/portfolios/${portfolioId}/performance?${params}`,
  );
}

// ── Decomposition ───────────────────────────────────────────────────

export async function getDecomposition(
  portfolioId: number,
  reporting: ReportingMode = "USD",
  startDate?: string,
  endDate?: string,
): Promise<DecompositionResponse> {
  const params = new URLSearchParams({ reporting });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  return fetchJSON<DecompositionResponse>(
    `${BASE}/portfolios/${portfolioId}/decomposition?${params}`,
  );
}

export async function createPortfolio(body: {
  name: string;
  description?: string;
  base_currency?: string;
}): Promise<Portfolio> {
  const res = await fetch(`${BASE}/portfolios`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Create portfolio failed (${res.status}): ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<Portfolio>;
}

export async function addTransactions(
  portfolioId: number,
  transactions: {
    ts: string;
    tx_type: string;
    symbol?: string;
    quantity?: number;
    price_ngn?: number;
    amount_ngn: number;
    fees_ngn?: number;
    notes?: string;
  }[],
): Promise<{ added: number }> {
  const res = await fetch(`${BASE}/portfolios/${portfolioId}/transactions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transactions }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Add transaction failed (${res.status}): ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<{ added: number }>;
}

// ── Transactions ────────────────────────────────────────────────────

export async function listTransactions(
  portfolioId: number,
  opts?: {
    symbol?: string;
    txType?: string;
    startDate?: string;
    endDate?: string;
    limit?: number;
    offset?: number;
  },
): Promise<TransactionList> {
  const params = new URLSearchParams();
  if (opts?.symbol) params.set("symbol", opts.symbol);
  if (opts?.txType) params.set("tx_type", opts.txType);
  if (opts?.startDate) params.set("start_date", opts.startDate);
  if (opts?.endDate) params.set("end_date", opts.endDate);
  params.set("limit", String(opts?.limit ?? 100));
  params.set("offset", String(opts?.offset ?? 0));
  return fetchJSON<TransactionList>(
    `${BASE}/portfolios/${portfolioId}/transactions?${params}`,
  );
}

// ── Stocks ────────────────────────────────────────────────────────────

export async function listStocks(opts?: {
  sector?: string;
  liquidity?: string;
}): Promise<StockListResponse> {
  const params = new URLSearchParams();
  if (opts?.sector) params.set("sector", opts.sector);
  if (opts?.liquidity) params.set("liquidity", opts.liquidity);
  const qs = params.toString();
  return fetchJSON<StockListResponse>(`${BASE}/stocks${qs ? `?${qs}` : ""}`);
}

export async function getStock(symbol: string): Promise<{ success: boolean; data: Record<string, unknown> }> {
  return fetchJSON(`${BASE}/stocks/${symbol}`);
}

export async function getStockIndicators(symbol: string): Promise<{ success: boolean; symbol: string; indicators: TechnicalIndicators }> {
  return fetchJSON(`${BASE}/stocks/${symbol}/indicators`);
}

export async function getStockSectors(): Promise<{ success: boolean; sectors: string[] }> {
  return fetchJSON(`${BASE}/stocks/sectors`);
}

// ── Recommendations ───────────────────────────────────────────────────

export async function getTopRecommendations(opts?: {
  horizon?: string;
  action?: string;
  sector?: string;
  min_liquidity?: string;
  limit?: number;
}): Promise<RecommendationListResponse> {
  const params = new URLSearchParams();
  if (opts?.horizon) params.set("horizon", opts.horizon);
  if (opts?.action) params.set("action", opts.action);
  if (opts?.sector) params.set("sector", opts.sector);
  if (opts?.min_liquidity) params.set("min_liquidity", opts.min_liquidity);
  if (opts?.limit) params.set("limit", String(opts.limit));
  return fetchJSON<RecommendationListResponse>(`${BASE}/recommendations?${params}`);
}

export async function getBuyRecommendations(
  horizon = "long_term",
  limit = 10,
): Promise<RecommendationListResponse> {
  return fetchJSON<RecommendationListResponse>(
    `${BASE}/recommendations/buy?horizon=${horizon}&limit=${limit}`,
  );
}

export async function getSellRecommendations(
  horizon = "swing",
  limit = 5,
): Promise<RecommendationListResponse> {
  return fetchJSON<RecommendationListResponse>(
    `${BASE}/recommendations/sell?horizon=${horizon}&limit=${limit}`,
  );
}

export async function getStockRecommendation(
  symbol: string,
  horizon = "long_term",
  userLevel = "beginner",
): Promise<RecommendationResponse> {
  return fetchJSON<RecommendationResponse>(
    `${BASE}/recommendations/${symbol}?horizon=${horizon}&user_level=${userLevel}`,
  );
}

export async function getStockAllHorizons(
  symbol: string,
  userLevel = "beginner",
): Promise<{ success: boolean; symbol: string; recommendations: Record<string, Record<string, unknown>> }> {
  return fetchJSON(`${BASE}/recommendations/${symbol}/all-horizons?user_level=${userLevel}`);
}

// ── Market Data ───────────────────────────────────────────────────────

export async function getMarketSummary(): Promise<MarketSummaryResponse> {
  return fetchJSON<MarketSummaryResponse>(`${BASE}/market/summary`);
}

export async function getMarketRegime(): Promise<{ success: boolean; regime: string; confidence: number; trend_direction: string; reasoning: string; warnings: string[] }> {
  return fetchJSON(`${BASE}/market/regime`);
}

// ── Scan Trigger ──────────────────────────────────────────────────────

export interface ScanHistoryEntry {
  id: number;
  triggered_at: string;
  completed_at: string | null;
  success: boolean;
  symbols_fetched: number;
  symbols_total: number;
  latest_date: string | null;
  duration_seconds: number;
  warnings: string[];
  message: string | null;
}

export interface ScanTriggerResponse {
  success: boolean;
  message: string;
  symbols_fetched: number;
  symbols_total: number;
  latest_date: string;
  duration_seconds: number;
  warnings: string[];
}

export interface ScanLatestResponse {
  has_scans: boolean;
  last_scan: ScanHistoryEntry | null;
}

export async function getLatestScan(): Promise<ScanLatestResponse> {
  return fetchJSON<ScanLatestResponse>(`${BASE}/scan/latest`);
}

export async function triggerScan(): Promise<ScanTriggerResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 150_000);
  try {
    const res = await fetch(`${BASE}/scan/trigger`, {
      method: "POST",
      signal: controller.signal,
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      const msg = body
        ? `Scanner API ${res.status}: ${body.slice(0, 200)}`
        : `Scan failed (${res.status})`;
      emitToast(msg, "error");
      throw new Error(msg);
    }
    return res.json() as Promise<ScanTriggerResponse>;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      emitToast("Scan timed out — try again later", "warning");
      throw new Error("Scan timed out");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

// ── Audit ─────────────────────────────────────────────────────────────

export async function listAuditEvents(opts?: {
  component?: string;
  eventType?: string;
  level?: string;
  startDate?: string;
  endDate?: string;
  limit?: number;
  offset?: number;
}): Promise<AuditList> {
  const params = new URLSearchParams();
  if (opts?.component) params.set("component", opts.component);
  if (opts?.eventType) params.set("event_type", opts.eventType);
  if (opts?.level) params.set("level", opts.level);
  if (opts?.startDate) params.set("start_date", opts.startDate);
  if (opts?.endDate) params.set("end_date", opts.endDate);
  params.set("limit", String(opts?.limit ?? 50));
  params.set("offset", String(opts?.offset ?? 0));
  return fetchJSON<AuditList>(`${BASE}/audit/events?${params}`);
}
