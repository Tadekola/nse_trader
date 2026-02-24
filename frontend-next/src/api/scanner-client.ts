/**
 * Scanner API client — typed functions for all 9 scanner endpoints.
 * 
 * Uses the same Next.js rewrite proxy as the main client:
 *   browser → /api/v1/scanner/* → FastAPI backend
 */

import type {
  ScannerDashboardResponse,
  ScanResultTableResponse,
  ScoreExplanationResponse,
  ScanRunListResponse,
  ScanRunResponse,
  ScanResultListResponse,
  ScannerHealthResponse,
} from "./scanner-types";

const BASE = "/api/v1/scanner";

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Scanner API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

// ── Dashboard ───────────────────────────────────────────────────────

export async function getScannerDashboard(
  universe = "top_liquid_50",
): Promise<ScannerDashboardResponse> {
  return fetchJSON<ScannerDashboardResponse>(
    `${BASE}/dashboard?universe_name=${universe}`,
  );
}

// ── Table (Sortable/Filterable) ─────────────────────────────────────

export async function getScannerTable(opts?: {
  universe?: string;
  page?: number;
  pageSize?: number;
  sortBy?: string;
  sortDir?: string;
  qualityTier?: string;
  minScore?: number;
  maxScore?: number;
}): Promise<ScanResultTableResponse> {
  const params = new URLSearchParams();
  params.set("universe_name", opts?.universe ?? "top_liquid_50");
  if (opts?.page) params.set("page", String(opts.page));
  if (opts?.pageSize) params.set("page_size", String(opts.pageSize));
  if (opts?.sortBy) params.set("sort_by", opts.sortBy);
  if (opts?.sortDir) params.set("sort_dir", opts.sortDir);
  if (opts?.qualityTier) params.set("quality_tier", opts.qualityTier);
  if (opts?.minScore != null) params.set("min_score", String(opts.minScore));
  if (opts?.maxScore != null) params.set("max_score", String(opts.maxScore));
  return fetchJSON<ScanResultTableResponse>(`${BASE}/table?${params}`);
}

// ── Explain ─────────────────────────────────────────────────────────

export async function getExplanation(
  symbol: string,
  runId?: number,
): Promise<ScoreExplanationResponse> {
  const params = new URLSearchParams();
  if (runId) params.set("run_id", String(runId));
  const qs = params.toString();
  return fetchJSON<ScoreExplanationResponse>(
    `${BASE}/explain/${symbol}${qs ? `?${qs}` : ""}`,
  );
}

// ── Runs ────────────────────────────────────────────────────────────

export async function listScanRuns(opts?: {
  universe?: string;
  limit?: number;
  offset?: number;
}): Promise<ScanRunListResponse> {
  const params = new URLSearchParams();
  if (opts?.universe) params.set("universe_name", opts.universe);
  params.set("limit", String(opts?.limit ?? 20));
  params.set("offset", String(opts?.offset ?? 0));
  return fetchJSON<ScanRunListResponse>(`${BASE}/runs?${params}`);
}

export async function getScanRun(runId: number): Promise<ScanRunResponse> {
  return fetchJSON<ScanRunResponse>(`${BASE}/runs/${runId}`);
}

export async function getScanRunResults(
  runId: number,
  limit = 50,
  offset = 0,
): Promise<ScanResultListResponse> {
  return fetchJSON<ScanResultListResponse>(
    `${BASE}/runs/${runId}/results?limit=${limit}&offset=${offset}`,
  );
}

// ── Health ──────────────────────────────────────────────────────────

export async function getScannerHealth(
  universe = "top_liquid_50",
): Promise<ScannerHealthResponse> {
  return fetchJSON<ScannerHealthResponse>(
    `${BASE}/health?universe_name=${universe}`,
  );
}
