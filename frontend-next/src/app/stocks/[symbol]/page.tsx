"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  getStockRecommendation,
  getStockAllHorizons,
  getStockIndicators,
} from "@/api/client";
import type { Recommendation } from "@/api/types";
import { cn } from "@/api/utils";

type UserLevel = "beginner" | "intermediate" | "advanced";

function actionColor(action: string) {
  switch (action) {
    case "STRONG_BUY": case "BUY": return "text-terminal-green";
    case "SELL": case "STRONG_SELL": case "AVOID": return "text-terminal-red";
    default: return "text-terminal-amber";
  }
}

function actionBg(action: string) {
  switch (action) {
    case "STRONG_BUY": case "BUY": return "bg-terminal-green/10 border-terminal-green/30";
    case "SELL": case "STRONG_SELL": case "AVOID": return "bg-terminal-red/10 border-terminal-red/30";
    default: return "bg-terminal-amber/10 border-terminal-amber/30";
  }
}

function biasBar(probability: number | null | undefined) {
  if (probability == null) return null;
  const pct = Math.max(0, Math.min(100, probability));
  const color = pct >= 60 ? "bg-terminal-green" : pct >= 40 ? "bg-terminal-amber" : "bg-terminal-red";
  return (
    <div className="w-full bg-terminal-bg rounded-full h-2 mt-1">
      <div className={cn("h-2 rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function StockDetailPage() {
  const params = useParams();
  const symbol = (params.symbol as string)?.toUpperCase() ?? "";

  const [rec, setRec] = useState<Recommendation | null>(null);
  const [horizons, setHorizons] = useState<Record<string, Record<string, unknown>> | null>(null);
  const [indicators, setIndicators] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userLevel, setUserLevel] = useState<UserLevel>("beginner");

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [recoRes, horizonRes] = await Promise.allSettled([
          getStockRecommendation(symbol, "long_term", userLevel),
          getStockAllHorizons(symbol, userLevel),
        ]);
        if (recoRes.status === "fulfilled") setRec(recoRes.value.data);
        else throw new Error(recoRes.reason?.message || "Failed to load recommendation");
        if (horizonRes.status === "fulfilled") setHorizons(horizonRes.value.recommendations);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load stock data");
      }
      setLoading(false);
    }

    async function loadIndicators() {
      try {
        const res = await getStockIndicators(symbol);
        setIndicators(res.indicators as Record<string, unknown>);
      } catch {
        // optional
      }
    }

    if (symbol) {
      load();
      loadIndicators();
    }
  }, [symbol, userLevel]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32 text-terminal-dim text-sm">
        Analyzing {symbol}...
      </div>
    );
  }

  if (error || !rec) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-xs text-terminal-dim hover:text-terminal-text">← Back</Link>
        <div className="card py-16 text-center text-terminal-red text-sm">
          {error || `No recommendation available for ${symbol}`}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back + Header */}
      <div>
        <Link href="/" className="text-xs text-terminal-dim hover:text-terminal-text">← Back to Top Picks</Link>
      </div>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-terminal-text">{rec.symbol}</h1>
          <p className="text-sm text-terminal-muted">{rec.name}</p>
        </div>
        <div className="flex gap-2 items-center">
          {/* User Level Toggle */}
          <div className="toggle-group">
            {(["beginner", "intermediate", "advanced"] as UserLevel[]).map((lvl) => (
              <button
                key={lvl}
                onClick={() => setUserLevel(lvl)}
                className={cn("toggle-item text-[10px]", userLevel === lvl && "toggle-item-active")}
              >
                {lvl.charAt(0).toUpperCase() + lvl.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Signal Card */}
      <div className={cn("card border-2 p-6", actionBg(rec.action))}>
        <div className="flex items-center justify-between mb-4">
          <div>
            <span className={cn("text-2xl font-bold font-mono", actionColor(rec.action))}>
              {rec.bias_label || rec.action}
            </span>
            {rec.bias_probability != null && (
              <span className="text-lg text-terminal-muted ml-2 font-mono">{rec.bias_probability}%</span>
            )}
          </div>
          <div className="text-right">
            <span className="text-2xl font-bold font-mono text-terminal-text">
              ₦{rec.current_price.toLocaleString("en", { minimumFractionDigits: 2 })}
            </span>
            <span className="block text-xs text-terminal-dim">Current Price</span>
          </div>
        </div>

        {/* Bias Probability Bar */}
        {rec.bias_probability != null && (
          <div className="mb-4">
            <div className="flex justify-between text-[10px] text-terminal-dim font-mono mb-0.5">
              <span>Bearish</span>
              <span>Neutral</span>
              <span>Bullish</span>
            </div>
            {biasBar(rec.bias_probability)}
          </div>
        )}

        {/* Key Metrics Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
          <div>
            <span className="text-terminal-dim">Confidence</span>
            <span className="block text-terminal-text text-sm font-semibold">{rec.confidence.toFixed(0)}%</span>
          </div>
          <div>
            <span className="text-terminal-dim">Data Quality</span>
            <span className="block text-terminal-text text-sm font-semibold">{(rec.confidence_score * 100).toFixed(0)}%</span>
          </div>
          <div>
            <span className="text-terminal-dim">Status</span>
            <span className={cn(
              "block text-sm font-semibold",
              rec.status === "ACTIVE" ? "text-terminal-green" : "text-terminal-amber"
            )}>
              {rec.status}
            </span>
          </div>
          <div>
            <span className="text-terminal-dim">Horizon</span>
            <span className="block text-terminal-text text-sm font-semibold">{rec.horizon.replace("_", " ")}</span>
          </div>
        </div>
      </div>

      {/* Entry/Exit + Risk — side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Entry/Exit Points */}
        {rec.entry_price != null && (
          <div className="card">
            <h2 className="text-sm font-semibold text-terminal-text mb-3">Entry & Exit Points</h2>
            <div className="space-y-2 text-xs font-mono">
              <div className="flex justify-between">
                <span className="text-terminal-dim">Entry Price</span>
                <span className="text-terminal-green">₦{rec.entry_price?.toFixed(2)}</span>
              </div>
              {rec.entry_zone_low != null && rec.entry_zone_high != null && (
                <div className="flex justify-between">
                  <span className="text-terminal-dim">Entry Zone</span>
                  <span className="text-terminal-text">₦{rec.entry_zone_low?.toFixed(2)} – ₦{rec.entry_zone_high?.toFixed(2)}</span>
                </div>
              )}
              {rec.stop_loss != null && (
                <div className="flex justify-between">
                  <span className="text-terminal-dim">Stop Loss</span>
                  <span className="text-terminal-red">₦{rec.stop_loss?.toFixed(2)} ({rec.stop_loss_percent?.toFixed(1)}%)</span>
                </div>
              )}
              {rec.target_1 != null && (
                <div className="flex justify-between">
                  <span className="text-terminal-dim">Target 1</span>
                  <span className="text-terminal-green">₦{rec.target_1?.toFixed(2)}</span>
                </div>
              )}
              {rec.target_2 != null && (
                <div className="flex justify-between">
                  <span className="text-terminal-dim">Target 2</span>
                  <span className="text-terminal-green">₦{Number(rec.target_2).toFixed(2)}</span>
                </div>
              )}
              {rec.target_3 != null && (
                <div className="flex justify-between">
                  <span className="text-terminal-dim">Target 3</span>
                  <span className="text-terminal-green">₦{Number(rec.target_3).toFixed(2)}</span>
                </div>
              )}
              {rec.risk_reward_ratio != null && (
                <div className="flex justify-between border-t border-terminal-border pt-2 mt-2">
                  <span className="text-terminal-dim">Risk/Reward</span>
                  <span className="text-terminal-accent font-semibold">{rec.risk_reward_ratio?.toFixed(2)}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Risk Metrics */}
        <div className="card">
          <h2 className="text-sm font-semibold text-terminal-text mb-3">Risk Assessment</h2>
          <div className="space-y-2 text-xs font-mono">
            {rec.risk_level && (
              <div className="flex justify-between">
                <span className="text-terminal-dim">Risk Level</span>
                <span className={cn(
                  rec.risk_level === "LOW" ? "text-terminal-green" :
                  rec.risk_level === "MEDIUM" ? "text-terminal-amber" : "text-terminal-red"
                )}>{rec.risk_level}</span>
              </div>
            )}
            {rec.volatility != null && (
              <div className="flex justify-between">
                <span className="text-terminal-dim">Volatility</span>
                <span className="text-terminal-text">{(Number(rec.volatility) * 100).toFixed(1)}%</span>
              </div>
            )}
            {rec.max_drawdown != null && (
              <div className="flex justify-between">
                <span className="text-terminal-dim">Max Drawdown</span>
                <span className="text-terminal-red">{(Number(rec.max_drawdown) * 100).toFixed(1)}%</span>
              </div>
            )}
            {rec.liquidity_score != null && (
              <div className="flex justify-between">
                <span className="text-terminal-dim">Liquidity Score</span>
                <span className="text-terminal-text">{(Number(rec.liquidity_score) * 100).toFixed(0)}%</span>
              </div>
            )}
            {rec.liquidity_warning && (
              <p className="text-[10px] text-terminal-amber mt-1">⚠ {rec.liquidity_warning}</p>
            )}
            {rec.market_regime && (
              <div className="flex justify-between border-t border-terminal-border pt-2 mt-2">
                <span className="text-terminal-dim">Market Regime</span>
                <span className="text-terminal-text">{rec.market_regime.replace("_", " ")}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Explanation */}
      <div className="card">
        <h2 className="text-sm font-semibold text-terminal-text mb-3">Analysis</h2>
        <p className="text-xs text-terminal-muted leading-relaxed whitespace-pre-wrap">
          {rec.probabilistic_reasoning || rec.explanation}
        </p>
      </div>

      {/* Reasons */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="text-sm font-semibold text-terminal-text mb-3">Why This Signal</h2>
          <p className="text-xs text-terminal-accent mb-2">{rec.primary_reason}</p>
          {rec.supporting_reasons.length > 0 && (
            <ul className="space-y-1">
              {rec.supporting_reasons.map((r, i) => (
                <li key={i} className="text-[11px] text-terminal-muted flex gap-1.5">
                  <span className="text-terminal-dim shrink-0">•</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          <h2 className="text-sm font-semibold text-terminal-red mb-3">Risk Warnings</h2>
          {rec.risk_warnings.length === 0 ? (
            <p className="text-xs text-terminal-dim">No specific warnings</p>
          ) : (
            <ul className="space-y-1">
              {rec.risk_warnings.map((w, i) => (
                <li key={i} className="text-[11px] text-terminal-amber flex gap-1.5">
                  <span className="shrink-0">⚠</span>
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          )}
          {rec.corporate_action_alert && (
            <p className="text-xs text-terminal-cyan mt-3 border-t border-terminal-border pt-2">
              {rec.corporate_action_alert}
            </p>
          )}
        </div>
      </div>

      {/* Multi-Horizon Comparison */}
      {horizons && Object.keys(horizons).length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-terminal-text mb-3">Across All Horizons</h2>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-terminal-border">
                <th className="table-header">Horizon</th>
                <th className="table-header text-center">Signal</th>
                <th className="table-header text-right">Confidence</th>
                <th className="table-header">Primary Reason</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(horizons).map(([h, data]) => (
                <tr key={h} className="table-row">
                  <td className="table-cell font-mono">{h.replace("_", " ")}</td>
                  <td className="table-cell text-center">
                    <span className={cn(
                      "badge text-[10px]",
                      (data.action === "BUY" || data.action === "STRONG_BUY") ? "badge-green" :
                      (data.action === "SELL" || data.action === "STRONG_SELL") ? "badge-red" : "badge-amber"
                    )}>
                      {(data.bias_label as string) || (data.action as string)}
                    </span>
                  </td>
                  <td className="table-cell text-right font-mono">
                    {typeof data.confidence === "number" ? `${data.confidence.toFixed(0)}%` : "—"}
                  </td>
                  <td className="table-cell text-terminal-muted truncate max-w-xs">
                    {(data.primary_reason as string) || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Sector Context */}
      {rec.sector_context && (
        <div className="card">
          <h2 className="text-sm font-semibold text-terminal-text mb-2">Sector Context</h2>
          <p className="text-xs text-terminal-muted">{rec.sector_context}</p>
        </div>
      )}

      {/* Suppression Notice */}
      {rec.status === "SUPPRESSED" && rec.suppression_reason && (
        <div className="card border-terminal-amber/40 bg-terminal-amber/5">
          <h2 className="text-sm font-semibold text-terminal-amber mb-2">Signal Suppressed</h2>
          <p className="text-xs text-terminal-muted">{rec.suppression_reason}</p>
        </div>
      )}
    </div>
  );
}
