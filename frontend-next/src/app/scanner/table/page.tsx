"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { getScannerTable } from "@/api/scanner-client";
import type { ScanResultTableResponse, ScanResultSortable } from "@/api/scanner-types";
import { cn, fmtNum, fmtPct } from "@/api/utils";

const TIERS = ["", "HIGH", "MEDIUM", "LOW", "INSUFFICIENT"] as const;

type SortCol =
  | "rank" | "quality_score" | "symbol"
  | "profitability" | "cash_quality" | "balance_sheet"
  | "stability" | "shareholder_return"
  | "liquidity_score" | "confidence_penalty" | "red_flag_count";

function TierBadge({ tier }: { tier: string }) {
  const cls =
    tier === "HIGH" ? "badge-green"
      : tier === "MEDIUM" ? "badge-blue"
        : tier === "LOW" ? "badge-amber"
          : "badge-red";
  return <span className={`badge ${cls} text-[10px]`}>{tier}</span>;
}

function SortHeader({
  label,
  field,
  current,
  dir,
  onSort,
}: {
  label: string;
  field: SortCol;
  current: string;
  dir: string;
  onSort: (f: SortCol) => void;
}) {
  const active = current === field;
  return (
    <th
      className="table-header cursor-pointer select-none hover:text-terminal-text whitespace-nowrap"
      onClick={() => onSort(field)}
    >
      {label}
      {active && <span className="ml-1">{dir === "asc" ? "▲" : "▼"}</span>}
    </th>
  );
}

export default function ScannerTablePage() {
  const [data, setData] = useState<ScanResultTableResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [tier, setTier] = useState("");
  const [minScore, setMinScore] = useState<string>("");
  const [maxScore, setMaxScore] = useState<string>("");

  // Pagination + sorting
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<SortCol>("rank");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getScannerTable({
        page,
        pageSize: 50,
        sortBy,
        sortDir,
        qualityTier: tier || undefined,
        minScore: minScore ? Number(minScore) : undefined,
        maxScore: maxScore ? Number(maxScore) : undefined,
      });
      setData(res);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [page, sortBy, sortDir, tier, minScore, maxScore]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  function handleSort(field: SortCol) {
    if (sortBy === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(field);
      setSortDir(field === "rank" || field === "symbol" ? "asc" : "desc");
    }
    setPage(1);
  }

  // Client-side symbol search filter
  const filtered = data?.results.filter((r) =>
    search ? r.symbol.toLowerCase().includes(search.toLowerCase()) : true,
  ) ?? [];

  if (error && !data) {
    return (
      <div className="card p-6">
        <p className="text-terminal-red font-mono">Error: {error}</p>
        <p className="text-terminal-dim text-sm mt-2">Ensure a scan has been completed.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-terminal-text">Quality Screener</h1>
          {data && (
            <p className="text-sm text-terminal-dim font-mono mt-0.5">
              {data.universe_name} · {data.as_of_date} · {data.total} results
            </p>
          )}
        </div>
        <Link href="/scanner" className="btn-ghost text-xs">
          ← Dashboard
        </Link>
      </div>

      {/* Filters */}
      <div className="card card-body flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search symbol…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-terminal-bg border border-terminal-border rounded px-3 py-1.5 text-sm font-mono text-terminal-text w-40 focus:outline-none focus:border-terminal-accent"
        />
        <select
          value={tier}
          onChange={(e) => { setTier(e.target.value); setPage(1); }}
          className="bg-terminal-bg border border-terminal-border rounded px-3 py-1.5 text-sm font-mono text-terminal-text focus:outline-none focus:border-terminal-accent"
        >
          {TIERS.map((t) => (
            <option key={t} value={t}>{t || "All Tiers"}</option>
          ))}
        </select>
        <div className="flex items-center gap-1 text-xs text-terminal-dim">
          <span>Score</span>
          <input
            type="number"
            placeholder="Min"
            value={minScore}
            onChange={(e) => { setMinScore(e.target.value); setPage(1); }}
            className="bg-terminal-bg border border-terminal-border rounded px-2 py-1 text-sm font-mono text-terminal-text w-16 focus:outline-none"
          />
          <span>–</span>
          <input
            type="number"
            placeholder="Max"
            value={maxScore}
            onChange={(e) => { setMaxScore(e.target.value); setPage(1); }}
            className="bg-terminal-bg border border-terminal-border rounded px-2 py-1 text-sm font-mono text-terminal-text w-16 focus:outline-none"
          />
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[1000px]">
          <thead className="border-b border-terminal-border">
            <tr>
              <SortHeader label="#" field="rank" current={sortBy} dir={sortDir} onSort={handleSort} />
              <SortHeader label="Symbol" field="symbol" current={sortBy} dir={sortDir} onSort={handleSort} />
              <SortHeader label="Score" field="quality_score" current={sortBy} dir={sortDir} onSort={handleSort} />
              <th className="table-header">Tier</th>
              <SortHeader label="Profit" field="profitability" current={sortBy} dir={sortDir} onSort={handleSort} />
              <SortHeader label="Cash" field="cash_quality" current={sortBy} dir={sortDir} onSort={handleSort} />
              <SortHeader label="B/S" field="balance_sheet" current={sortBy} dir={sortDir} onSort={handleSort} />
              <SortHeader label="Stab" field="stability" current={sortBy} dir={sortDir} onSort={handleSort} />
              <SortHeader label="SHR" field="shareholder_return" current={sortBy} dir={sortDir} onSort={handleSort} />
              <SortHeader label="Liq" field="liquidity_score" current={sortBy} dir={sortDir} onSort={handleSort} />
              <SortHeader label="Pen" field="confidence_penalty" current={sortBy} dir={sortDir} onSort={handleSort} />
              <SortHeader label="Flags" field="red_flag_count" current={sortBy} dir={sortDir} onSort={handleSort} />
              <th className="table-header">1Y NGN</th>
              <th className="table-header">1Y USD</th>
            </tr>
          </thead>
          <tbody>
            {loading && !data ? (
              <tr>
                <td colSpan={14} className="table-cell text-center text-terminal-dim animate-pulse">
                  Loading…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={14} className="table-cell text-center text-terminal-dim">
                  No results match filters
                </td>
              </tr>
            ) : (
              filtered.map((r) => (
                <tr key={r.symbol} className="table-row">
                  <td className="table-cell text-terminal-dim">{r.rank}</td>
                  <td className="table-cell">
                    <Link
                      href={`/scanner/explain/${r.symbol}`}
                      className="text-terminal-accent hover:underline font-medium"
                    >
                      {r.symbol}
                    </Link>
                  </td>
                  <td className="table-cell font-semibold">{fmtNum(r.quality_score, 1)}</td>
                  <td className="table-cell"><TierBadge tier={r.quality_tier} /></td>
                  <td className="table-cell text-terminal-muted">{fmtNum(r.profitability, 1)}</td>
                  <td className="table-cell text-terminal-muted">{fmtNum(r.cash_quality, 1)}</td>
                  <td className="table-cell text-terminal-muted">{fmtNum(r.balance_sheet, 1)}</td>
                  <td className="table-cell text-terminal-muted">{fmtNum(r.stability, 1)}</td>
                  <td className="table-cell text-terminal-muted">{fmtNum(r.shareholder_return, 1)}</td>
                  <td className="table-cell text-terminal-muted">{fmtNum(r.liquidity_score, 2)}</td>
                  <td className={cn("table-cell", r.confidence_penalty && r.confidence_penalty > 0.2 ? "text-terminal-amber" : "text-terminal-muted")}>
                    {fmtNum(r.confidence_penalty, 2)}
                  </td>
                  <td className={cn("table-cell", r.red_flag_count > 0 ? "text-terminal-red" : "text-terminal-dim")}>
                    {r.red_flag_count > 0 ? r.red_flag_count : "—"}
                  </td>
                  <td className={cn("table-cell", triColor(r.trailing_returns.tri_1y_ngn))}>
                    {r.trailing_returns.tri_1y_ngn != null ? fmtPct(r.trailing_returns.tri_1y_ngn, 1) : "—"}
                  </td>
                  <td className={cn("table-cell", triColor(r.trailing_returns.tri_1y_usd))}>
                    {r.trailing_returns.tri_1y_usd != null ? fmtPct(r.trailing_returns.tri_1y_usd, 1) : "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.total > 50 && (
        <div className="flex items-center justify-between text-sm font-mono">
          <span className="text-terminal-dim">
            Page {data.page} · {data.total} total
          </span>
          <div className="flex gap-2">
            <button
              className="btn-ghost text-xs"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ← Prev
            </button>
            <button
              className="btn-ghost text-xs"
              disabled={page * 50 >= data.total}
              onClick={() => setPage((p) => p + 1)}
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function triColor(val: number | null): string {
  if (val == null) return "text-terminal-dim";
  return val > 0 ? "text-terminal-green" : val < 0 ? "text-terminal-red" : "text-terminal-muted";
}
