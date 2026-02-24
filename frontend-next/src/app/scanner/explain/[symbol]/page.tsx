"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getExplanation } from "@/api/scanner-client";
import type { ScoreExplanationResponse, MetricExplanation, GuardrailTrigger } from "@/api/scanner-types";
import { cn, fmtNum } from "@/api/utils";

function TierBadge({ tier }: { tier: string }) {
  const cls =
    tier === "HIGH" ? "badge-green"
      : tier === "MEDIUM" ? "badge-blue"
        : tier === "LOW" ? "badge-amber"
          : "badge-red";
  return <span className={`badge ${cls}`}>{tier}</span>;
}

function scoreTier(score: number, dq: string): string {
  if (dq === "INSUFFICIENT") return "INSUFFICIENT";
  if (score >= 70) return "HIGH";
  if (score >= 40) return "MEDIUM";
  return "LOW";
}

function MetricRow({ m }: { m: MetricExplanation }) {
  const pct = Math.min((m.component_score / m.max_possible) * 100, 100);
  return (
    <tr className="table-row">
      <td className="table-cell font-medium text-terminal-text">{m.metric_name.replace(/_/g, " ")}</td>
      <td className="table-cell text-terminal-muted">{m.raw_value != null ? fmtNum(m.raw_value, 4) : "—"}</td>
      <td className="table-cell text-terminal-muted">{m.winsorized_value != null ? fmtNum(m.winsorized_value, 4) : "—"}</td>
      <td className="table-cell text-terminal-cyan">{fmtNum(m.percentile_rank, 2)}</td>
      <td className="table-cell">
        <div className="flex items-center gap-2">
          <span className="font-semibold w-10 text-right">{fmtNum(m.component_score, 1)}</span>
          <div className="flex-1 h-2 bg-terminal-border rounded-full overflow-hidden max-w-[80px]">
            <div
              className={cn(
                "h-full rounded-full",
                pct >= 70 ? "bg-terminal-green" : pct >= 40 ? "bg-terminal-accent" : "bg-terminal-amber",
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-terminal-dim text-xs">/{m.max_possible}</span>
        </div>
      </td>
      <td className="table-cell text-terminal-dim text-xs">{m.direction.replace(/_/g, " ")}</td>
    </tr>
  );
}

function GuardrailRow({ g }: { g: GuardrailTrigger }) {
  return (
    <div className={cn(
      "flex items-start gap-3 p-3 rounded-md border",
      g.triggered
        ? "bg-terminal-red/10 border-terminal-red/30"
        : "bg-terminal-border/20 border-terminal-border",
    )}>
      <span className={cn("text-lg", g.triggered ? "text-terminal-red" : "text-terminal-dim")}>
        {g.triggered ? "⚠" : "✓"}
      </span>
      <div className="flex-1">
        <p className={cn("text-sm font-medium", g.triggered ? "text-terminal-red" : "text-terminal-muted")}>
          {g.name.replace(/_/g, " ")}
        </p>
        <p className="text-xs text-terminal-dim mt-0.5">{g.reason}</p>
        {g.triggered && (
          <p className="text-xs font-mono text-terminal-amber mt-1">
            Score: {fmtNum(g.score_before, 1)} → {fmtNum(g.score_after, 1)} (capped at {g.cap_value})
          </p>
        )}
      </div>
    </div>
  );
}

export default function ExplainPage() {
  const params = useParams();
  const symbol = (params.symbol as string)?.toUpperCase();

  const [data, setData] = useState<ScoreExplanationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!symbol) return;
    getExplanation(symbol)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [symbol]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-terminal-dim font-mono animate-pulse">Loading explanation for {symbol}…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card p-6">
        <p className="text-terminal-red font-mono">Error: {error}</p>
        <Link href="/scanner/table" className="btn-ghost text-xs mt-3 inline-block">← Back to Table</Link>
      </div>
    );
  }

  if (!data) return null;

  const tier = scoreTier(data.quality_score, data.data_quality);
  const cb = data.confidence_breakdown;

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold font-mono text-terminal-text">{data.symbol}</h1>
            <TierBadge tier={tier} />
            <span className="badge badge-dim">{data.data_quality}</span>
          </div>
          <p className="text-sm text-terminal-dim font-mono mt-1">
            Score Explanation · Engine {data.scoring_config_version} · {data.scoring_config_hash.slice(0, 8)}
          </p>
        </div>
        <Link href="/scanner/table" className="btn-ghost text-xs">← Back to Table</Link>
      </div>

      {/* Score Hero */}
      <div className="card card-body flex items-center gap-6">
        <div className="text-center">
          <p className="stat-label">Quality Score</p>
          <p className={cn(
            "text-4xl font-mono font-bold",
            data.quality_score >= 70 ? "text-terminal-green"
              : data.quality_score >= 40 ? "text-terminal-accent"
                : "text-terminal-red",
          )}>
            {fmtNum(data.quality_score, 1)}
          </p>
        </div>
        <div className="flex-1 h-3 bg-terminal-border rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full",
              data.quality_score >= 70 ? "bg-terminal-green"
                : data.quality_score >= 40 ? "bg-terminal-accent"
                  : "bg-terminal-red",
            )}
            style={{ width: `${Math.min(data.quality_score, 100)}%` }}
          />
        </div>
        <span className="text-terminal-dim font-mono text-sm">/100</span>
      </div>

      {/* Red Flags */}
      {data.red_flags.length > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="text-sm font-medium text-terminal-red">Red Flags ({data.red_flags.length})</span>
          </div>
          <div className="card-body flex flex-wrap gap-2">
            {data.red_flags.map((f) => (
              <span key={f} className="badge badge-red">{f.replace(/_/g, " ")}</span>
            ))}
          </div>
        </div>
      )}

      {/* Reasons */}
      {data.reasons.length > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="text-sm font-medium text-terminal-text">Scoring Rationale</span>
          </div>
          <div className="card-body">
            <ul className="space-y-1.5">
              {data.reasons.map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-terminal-muted">
                  <span className="text-terminal-accent mt-0.5">•</span>
                  {r}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Metric Explanations */}
      <div className="card">
        <div className="card-header">
          <span className="text-sm font-medium text-terminal-text">Metric Breakdown ({data.metric_explanations.length} components)</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px]">
            <thead className="border-b border-terminal-border">
              <tr>
                <th className="table-header">Metric</th>
                <th className="table-header">Raw</th>
                <th className="table-header">Winsorized</th>
                <th className="table-header">Pctl Rank</th>
                <th className="table-header">Score</th>
                <th className="table-header">Direction</th>
              </tr>
            </thead>
            <tbody>
              {data.metric_explanations.map((m) => (
                <MetricRow key={m.metric_name} m={m} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Guardrails */}
      <div className="card">
        <div className="card-header">
          <span className="text-sm font-medium text-terminal-text">Guardrails</span>
          <span className="text-xs text-terminal-dim">
            {data.guardrail_triggers.filter((g) => g.triggered).length} triggered
          </span>
        </div>
        <div className="card-body space-y-2">
          {data.guardrail_triggers.map((g) => (
            <GuardrailRow key={g.name} g={g} />
          ))}
        </div>
      </div>

      {/* Confidence Penalty */}
      <div className="card">
        <div className="card-header">
          <span className="text-sm font-medium text-terminal-text">Confidence Penalty</span>
          <span className={cn("badge", cb.total > 0.2 ? "badge-red" : cb.total > 0 ? "badge-amber" : "badge-green")}>
            {fmtNum(cb.total, 3)}
          </span>
        </div>
        <div className="card-body">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <p className="stat-label">Missing Fields</p>
              <p className="text-sm font-mono text-terminal-text">{cb.missing_fields.length > 0 ? cb.missing_fields.join(", ") : "None"}</p>
              <p className="text-xs text-terminal-dim mt-0.5">Penalty: {fmtNum(cb.missing_fields_penalty, 3)}</p>
            </div>
            <div>
              <p className="stat-label">Staleness</p>
              <p className="text-sm font-mono text-terminal-text">{cb.staleness_days != null ? `${cb.staleness_days} days` : "—"}</p>
              <p className="text-xs text-terminal-dim mt-0.5">Penalty: {fmtNum(cb.staleness_penalty, 3)}</p>
            </div>
            <div>
              <p className="stat-label">Liquidity</p>
              <p className="text-sm font-mono text-terminal-text">{fmtNum(cb.liquidity_score, 3)}</p>
              <p className="text-xs text-terminal-dim mt-0.5">Penalty: {fmtNum(cb.liquidity_penalty, 3)}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Winsor Bounds */}
      <div className="card">
        <div className="card-header">
          <span className="text-sm font-medium text-terminal-text">Winsorization Bounds</span>
          <span className="text-xs text-terminal-dim">5th–95th percentile</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-terminal-border">
              <tr>
                <th className="table-header">Metric</th>
                <th className="table-header">Lower</th>
                <th className="table-header">Upper</th>
                <th className="table-header">Universe</th>
                <th className="table-header">Non-null</th>
              </tr>
            </thead>
            <tbody>
              {data.winsor_bounds.map((w) => (
                <tr key={w.metric_name} className="table-row">
                  <td className="table-cell font-medium text-terminal-text">{w.metric_name}</td>
                  <td className="table-cell text-terminal-muted">{w.lower_bound != null ? fmtNum(w.lower_bound, 4) : "—"}</td>
                  <td className="table-cell text-terminal-muted">{w.upper_bound != null ? fmtNum(w.upper_bound, 4) : "—"}</td>
                  <td className="table-cell text-terminal-dim">{w.universe_size}</td>
                  <td className="table-cell text-terminal-dim">{w.non_null_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
