"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getScanRun, getScanRunResults } from "@/api/scanner-client";
import type { ScanRunResponse, ScanResultListResponse } from "@/api/scanner-types";
import { cn, fmtDate, fmtTimestamp, fmtNum, fmtPct } from "@/api/utils";

export default function RunDetailPage() {
  const params = useParams();
  const runId = Number(params.id);

  const [run, setRun] = useState<ScanRunResponse | null>(null);
  const [results, setResults] = useState<ScanResultListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!runId) return;
    Promise.all([getScanRun(runId), getScanRunResults(runId)])
      .then(([r, res]) => { setRun(r); setResults(res); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-terminal-dim font-mono animate-pulse">Loading run #{runId}…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card p-6">
        <p className="text-terminal-red font-mono">Error: {error}</p>
        <Link href="/scanner/runs" className="btn-ghost text-xs mt-3 inline-block">← Back to Runs</Link>
      </div>
    );
  }

  if (!run || !results) return null;

  const summary = run.summary as Record<string, unknown> | null;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-terminal-text">Run #{run.id}</h1>
          <p className="text-sm text-terminal-dim font-mono mt-0.5">
            {run.universe_name} · {fmtDate(run.as_of_date)} · {fmtTimestamp(run.created_at)}
          </p>
        </div>
        <Link href="/scanner/runs" className="btn-ghost text-xs">← All Runs</Link>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card card-body">
          <p className="stat-label">Scanned</p>
          <p className="stat-value text-terminal-text">{run.symbols_scanned}</p>
        </div>
        <div className="card card-body">
          <p className="stat-label">Ranked</p>
          <p className="stat-value text-terminal-accent">{run.symbols_ranked}</p>
        </div>
        <div className="card card-body">
          <p className="stat-label">Avg Quality</p>
          <p className="stat-value text-terminal-cyan">
            {summary?.avg_quality != null ? fmtNum(summary.avg_quality as number, 1) : "—"}
          </p>
        </div>
        <div className="card card-body">
          <p className="stat-label">Degraded</p>
          <p className="stat-value text-terminal-amber">
            {summary?.degraded_count != null ? String(summary.degraded_count) : "—"}
          </p>
        </div>
      </div>

      {/* Results Table */}
      <div className="card">
        <div className="card-header">
          <span className="text-sm font-medium text-terminal-text">Results ({results.total})</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px]">
            <thead className="border-b border-terminal-border">
              <tr>
                <th className="table-header">#</th>
                <th className="table-header">Symbol</th>
                <th className="table-header">Score</th>
                <th className="table-header">Data Quality</th>
                <th className="table-header">Penalty</th>
                <th className="table-header">Flags</th>
                <th className="table-header">1Y NGN</th>
                <th className="table-header">1Y USD</th>
              </tr>
            </thead>
            <tbody>
              {results.results.map((r) => {
                const dq = (r.flags as Record<string, unknown>)?.data_quality as string | undefined;
                return (
                  <tr key={r.symbol} className="table-row">
                    <td className="table-cell text-terminal-dim">{r.rank}</td>
                    <td className="table-cell">
                      <Link
                        href={`/scanner/explain/${r.symbol}?run_id=${runId}`}
                        className="text-terminal-accent hover:underline font-medium"
                      >
                        {r.symbol}
                      </Link>
                    </td>
                    <td className="table-cell font-semibold">{fmtNum(r.quality_score, 1)}</td>
                    <td className="table-cell">
                      <span className={cn(
                        "badge text-[10px]",
                        dq === "FULL" ? "badge-green" : dq === "DEGRADED" ? "badge-amber" : "badge-red",
                      )}>
                        {dq || "—"}
                      </span>
                    </td>
                    <td className={cn(
                      "table-cell",
                      r.confidence_penalty && r.confidence_penalty > 0.2 ? "text-terminal-amber" : "text-terminal-muted",
                    )}>
                      {fmtNum(r.confidence_penalty, 2)}
                    </td>
                    <td className={cn(
                      "table-cell",
                      (r.red_flags?.length ?? 0) > 0 ? "text-terminal-red" : "text-terminal-dim",
                    )}>
                      {(r.red_flags?.length ?? 0) > 0 ? r.red_flags!.length : "—"}
                    </td>
                    <td className={cn("table-cell", triColor(r.trailing_returns?.tri_1y_ngn))}>
                      {r.trailing_returns?.tri_1y_ngn != null ? fmtPct(r.trailing_returns.tri_1y_ngn, 1) : "—"}
                    </td>
                    <td className={cn("table-cell", triColor(r.trailing_returns?.tri_1y_usd))}>
                      {r.trailing_returns?.tri_1y_usd != null ? fmtPct(r.trailing_returns.tri_1y_usd, 1) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function triColor(val: number | null | undefined): string {
  if (val == null) return "text-terminal-dim";
  return val > 0 ? "text-terminal-green" : val < 0 ? "text-terminal-red" : "text-terminal-muted";
}
