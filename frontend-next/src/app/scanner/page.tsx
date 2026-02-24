"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getScannerDashboard } from "@/api/scanner-client";
import type { ScannerDashboardResponse } from "@/api/scanner-types";
import { cn, fmtDate, fmtNum, fmtPct } from "@/api/utils";

function HealthBadge({ status }: { status: string }) {
  const cls =
    status === "HEALTHY"
      ? "badge-green"
      : status === "DEGRADED"
        ? "badge-amber"
        : "badge-red";
  return <span className={`badge ${cls}`}>{status}</span>;
}

function TierBadge({ tier }: { tier: string }) {
  const cls =
    tier === "HIGH"
      ? "badge-green"
      : tier === "MEDIUM"
        ? "badge-blue"
        : tier === "LOW"
          ? "badge-amber"
          : "badge-red";
  return <span className={`badge ${cls}`}>{tier}</span>;
}

function ScoreBar({ score, max = 100 }: { score: number; max?: number }) {
  const pct = Math.min((score / max) * 100, 100);
  const color =
    score >= 70
      ? "bg-terminal-green"
      : score >= 40
        ? "bg-terminal-accent"
        : score >= 20
          ? "bg-terminal-amber"
          : "bg-terminal-red";
  return (
    <div className="w-full h-2 bg-terminal-border rounded-full overflow-hidden">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function ScannerDashboard() {
  const [data, setData] = useState<ScannerDashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getScannerDashboard()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-terminal-dim font-mono animate-pulse">Loading scanner dashboard...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card p-6">
        <p className="text-terminal-red font-mono">Error: {error}</p>
        <p className="text-terminal-dim text-sm mt-2">
          Ensure the backend is running and a scan has been completed.
        </p>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-terminal-text">Quality Scanner</h1>
          <p className="text-sm text-terminal-dim font-mono mt-0.5">
            {data.universe_name} · {fmtDate(data.last_scan_date)} · Run #{data.last_scan_run_id}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <HealthBadge status={data.health_status} />
          <Link href="/scanner/table" className="btn-primary text-xs">
            View Table
          </Link>
        </div>
      </div>

      {/* Hero Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card card-body">
          <p className="stat-label">Universe Size</p>
          <p className="stat-value text-terminal-text">{data.universe_size}</p>
        </div>
        <div className="card card-body">
          <p className="stat-label">Avg Quality</p>
          <p className="stat-value text-terminal-accent">{fmtNum(data.avg_quality_score, 1)}</p>
        </div>
        <div className="card card-body">
          <p className="stat-label">Median Quality</p>
          <p className="stat-value text-terminal-cyan">{fmtNum(data.median_quality_score, 1)}</p>
        </div>
        <div className="card card-body">
          <p className="stat-label">Coverage</p>
          <p className="stat-value text-terminal-green">{fmtNum(data.fundamentals_coverage_pct, 0)}%</p>
        </div>
      </div>

      {/* Score Distribution + Tiers */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Distribution */}
        <div className="card">
          <div className="card-header">
            <span className="text-sm font-medium text-terminal-text">Score Distribution</span>
          </div>
          <div className="card-body space-y-3">
            {data.score_distribution.map((d) => (
              <div key={d.bucket} className="flex items-center gap-3">
                <span className="text-xs font-mono text-terminal-dim w-12">{d.bucket}</span>
                <div className="flex-1 h-5 bg-terminal-border/40 rounded overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded",
                      d.bucket === "80-100"
                        ? "bg-terminal-green/70"
                        : d.bucket === "60-80"
                          ? "bg-terminal-accent/70"
                          : d.bucket === "40-60"
                            ? "bg-terminal-cyan/70"
                            : d.bucket === "20-40"
                              ? "bg-terminal-amber/70"
                              : "bg-terminal-red/70",
                    )}
                    style={{
                      width: `${data.universe_size > 0 ? (d.count / data.universe_size) * 100 : 0}%`,
                    }}
                  />
                </div>
                <span className="text-xs font-mono text-terminal-muted w-6 text-right">{d.count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Tiers */}
        <div className="card">
          <div className="card-header">
            <span className="text-sm font-medium text-terminal-text">Quality Tiers</span>
          </div>
          <div className="card-body space-y-3">
            {data.quality_tiers.map((t) => (
              <div key={t.tier} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <TierBadge tier={t.tier} />
                  <span className="text-xs font-mono text-terminal-dim">
                    {t.min_score}–{t.max_score}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-mono font-semibold text-terminal-text">{t.count}</span>
                  <span className="text-xs text-terminal-dim truncate max-w-[180px]">
                    {t.symbols.slice(0, 5).join(", ")}
                    {t.symbols.length > 5 ? "…" : ""}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card card-body text-center">
          <p className="stat-label">Red Flags</p>
          <p className={cn("stat-value", data.total_red_flags > 10 ? "text-terminal-red" : "text-terminal-amber")}>
            {data.total_red_flags}
          </p>
        </div>
        <div className="card card-body text-center">
          <p className="stat-label">Degraded</p>
          <p className={cn("stat-value", data.degraded_count > 5 ? "text-terminal-amber" : "text-terminal-muted")}>
            {data.degraded_count}
          </p>
        </div>
        <div className="card card-body text-center">
          <p className="stat-label">Insufficient</p>
          <p className={cn("stat-value", data.insufficient_count > 3 ? "text-terminal-red" : "text-terminal-muted")}>
            {data.insufficient_count}
          </p>
        </div>
      </div>

      {/* Top 5 / Bottom 5 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <div className="card-header">
            <span className="text-sm font-medium text-terminal-green">Top 5</span>
          </div>
          <div className="card-body">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="table-header">#</th>
                  <th className="table-header">Symbol</th>
                  <th className="table-header">Score</th>
                  <th className="table-header w-24">Bar</th>
                </tr>
              </thead>
              <tbody>
                {data.top_5.map((r) => (
                  <tr key={r.symbol} className="table-row">
                    <td className="table-cell text-terminal-dim">{r.rank}</td>
                    <td className="table-cell">
                      <Link href={`/scanner/explain/${r.symbol}`} className="text-terminal-accent hover:underline">
                        {r.symbol}
                      </Link>
                    </td>
                    <td className="table-cell font-semibold">{fmtNum(r.quality_score, 1)}</td>
                    <td className="table-cell"><ScoreBar score={r.quality_score} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="text-sm font-medium text-terminal-red">Bottom 5</span>
          </div>
          <div className="card-body">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="table-header">#</th>
                  <th className="table-header">Symbol</th>
                  <th className="table-header">Score</th>
                  <th className="table-header w-24">Bar</th>
                </tr>
              </thead>
              <tbody>
                {data.bottom_5.map((r) => (
                  <tr key={r.symbol} className="table-row">
                    <td className="table-cell text-terminal-dim">{r.rank}</td>
                    <td className="table-cell">
                      <Link href={`/scanner/explain/${r.symbol}`} className="text-terminal-accent hover:underline">
                        {r.symbol}
                      </Link>
                    </td>
                    <td className="table-cell font-semibold">{fmtNum(r.quality_score, 1)}</td>
                    <td className="table-cell"><ScoreBar score={r.quality_score} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Provenance Footer */}
      {data.scoring_config_version && (
        <div className="text-xs text-terminal-dim font-mono text-right">
          Engine {data.scoring_config_version} · Config {data.scoring_config_hash?.slice(0, 8)}
        </div>
      )}
    </div>
  );
}
