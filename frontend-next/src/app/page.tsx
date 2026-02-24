"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getBuyRecommendations,
  getMarketSummary,
} from "@/api/client";
import type {
  Recommendation,
  MarketRegime,
  TrendingStock,
  MarketSnapshot,
} from "@/api/types";
import { cn } from "@/api/utils";

type Horizon = "short_term" | "swing" | "long_term";
const HORIZONS: { key: Horizon; label: string }[] = [
  { key: "long_term", label: "Long Term" },
  { key: "swing", label: "Swing" },
  { key: "short_term", label: "Short Term" },
];

function regimeColor(regime: string) {
  switch (regime?.toLowerCase()) {
    case "trending": return "text-terminal-green";
    case "mean_reverting": return "text-terminal-amber";
    case "high_volatility": return "text-terminal-red";
    case "low_liquidity": return "text-terminal-red";
    default: return "text-terminal-muted";
  }
}

function trendIcon(dir: string) {
  switch (dir?.toLowerCase()) {
    case "bullish": return "▲";
    case "bearish": return "▼";
    default: return "►";
  }
}

function biasStyle(direction: string) {
  switch (direction?.toLowerCase()) {
    case "bullish": return "bg-terminal-green/15 border-terminal-green/40 text-terminal-green";
    case "bearish": return "bg-terminal-red/15 border-terminal-red/40 text-terminal-red";
    default: return "bg-terminal-surface border-terminal-border text-terminal-muted";
  }
}

function actionBadge(action: string) {
  switch (action) {
    case "STRONG_BUY": return "badge-green";
    case "BUY": return "badge-green";
    case "HOLD": return "badge-amber";
    case "SELL": return "badge-red";
    case "STRONG_SELL": return "badge-red";
    case "AVOID": return "badge-red";
    default: return "badge-dim";
  }
}

export default function TopPicksPage() {
  const [picks, setPicks] = useState<Recommendation[]>([]);
  const [horizon, setHorizon] = useState<Horizon>("long_term");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [regime, setRegime] = useState<MarketRegime | null>(null);
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null);
  const [gainers, setGainers] = useState<TrendingStock[]>([]);
  const [losers, setLosers] = useState<TrendingStock[]>([]);

  // Load market data once
  useEffect(() => {
    async function loadMarket() {
      try {
        const mkt = await getMarketSummary();
        setRegime(mkt.regime ?? null);
        setSnapshot(mkt.snapshot ?? null);
        setGainers(mkt.trending?.top_gainers ?? []);
        setLosers(mkt.trending?.top_losers ?? []);
      } catch {
        // Market data optional — don't block
      }
    }
    loadMarket();
  }, []);

  // Load recommendations on horizon change
  useEffect(() => {
    async function loadPicks() {
      setLoading(true);
      setError(null);
      try {
        const res = await getBuyRecommendations(horizon, 15);
        setPicks(res.data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load recommendations");
        setPicks([]);
      }
      setLoading(false);
    }
    loadPicks();
  }, [horizon]);

  return (
    <div className="space-y-6">
      {/* Market Regime Banner */}
      {regime && (
        <div className="card flex items-center gap-6 px-5 py-3">
          <div className="flex items-center gap-2">
            <span className={cn("text-lg font-bold font-mono", regimeColor(regime.regime))}>
              {trendIcon(regime.trend_direction)}
            </span>
            <div>
              <span className={cn("text-sm font-semibold", regimeColor(regime.regime))}>
                {regime.regime.replace("_", " ").toUpperCase()}
              </span>
              <span className="text-xs text-terminal-dim ml-2">
                {(regime.confidence * 100).toFixed(0)}% confidence
              </span>
            </div>
          </div>
          <p className="text-xs text-terminal-muted flex-1 truncate">
            {regime.reasoning}
          </p>
          {regime.warnings.length > 0 && (
            <span className="badge badge-amber text-[10px]">
              {regime.warnings.length} warning{regime.warnings.length > 1 ? "s" : ""}
            </span>
          )}
        </div>
      )}

      {/* Snapshot Strip */}
      {snapshot && (
        <div className="flex gap-4 text-xs font-mono">
          {snapshot.asi_value != null && (
            <div className="card px-3 py-2 flex items-center gap-2">
              <span className="text-terminal-dim">ASI</span>
              <span className="text-terminal-text font-semibold">
                {Number(snapshot.asi_value).toLocaleString("en", { maximumFractionDigits: 0 })}
              </span>
              {snapshot.asi_change_percent != null && (
                <span className={cn(
                  Number(snapshot.asi_change_percent) >= 0 ? "text-terminal-green" : "text-terminal-red"
                )}>
                  {Number(snapshot.asi_change_percent) >= 0 ? "+" : ""}
                  {Number(snapshot.asi_change_percent).toFixed(2)}%
                </span>
              )}
            </div>
          )}
          {snapshot.volume != null && (
            <div className="card px-3 py-2 flex items-center gap-2">
              <span className="text-terminal-dim">Volume</span>
              <span className="text-terminal-text">
                {Number(snapshot.volume).toLocaleString("en", { notation: "compact" } as Intl.NumberFormatOptions)}
              </span>
            </div>
          )}
          {snapshot.market_cap != null && (
            <div className="card px-3 py-2 flex items-center gap-2">
              <span className="text-terminal-dim">Mkt Cap</span>
              <span className="text-terminal-text">
                ₦{(Number(snapshot.market_cap) / 1e12).toFixed(2)}T
              </span>
            </div>
          )}
        </div>
      )}

      {/* Header + Horizon Toggle */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-terminal-text">Top Picks</h1>
          <p className="text-xs text-terminal-dim mt-0.5">
            Buy recommendations ranked by confidence
          </p>
        </div>
        <div className="toggle-group">
          {HORIZONS.map((h) => (
            <button
              key={h.key}
              onClick={() => setHorizon(h.key)}
              className={cn("toggle-item", horizon === h.key && "toggle-item-active")}
            >
              {h.label}
            </button>
          ))}
        </div>
      </div>

      {/* Recommendations Grid */}
      {loading ? (
        <div className="card py-16 text-center text-terminal-dim text-sm">
          Scanning market for {horizon.replace("_", " ")} opportunities...
        </div>
      ) : error ? (
        <div className="card py-16 text-center text-terminal-red text-sm">
          {error}
        </div>
      ) : picks.length === 0 ? (
        <div className="card py-16 text-center text-terminal-dim text-sm">
          No active buy signals at this horizon. Check back after market hours.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {picks.map((rec) => (
            <Link
              key={rec.symbol}
              href={`/stocks/${rec.symbol}`}
              className={cn(
                "card hover:border-terminal-border-bright transition-colors cursor-pointer",
                "border",
                biasStyle(rec.bias_direction),
              )}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <span className="font-semibold text-terminal-text text-sm">{rec.symbol}</span>
                  <span className="block text-[10px] text-terminal-dim truncate max-w-[180px]">{rec.name}</span>
                </div>
                <span className={cn("badge text-[10px]", actionBadge(rec.action))}>
                  {rec.bias_label || rec.action}
                </span>
              </div>

              <div className="flex items-center gap-4 text-xs font-mono mb-3">
                <div>
                  <span className="text-terminal-dim">Price</span>
                  <span className="block text-terminal-text">₦{rec.current_price.toLocaleString("en", { minimumFractionDigits: 2 })}</span>
                </div>
                {rec.bias_probability != null && (
                  <div>
                    <span className="text-terminal-dim">Probability</span>
                    <span className="block text-terminal-text">{rec.bias_probability}%</span>
                  </div>
                )}
                <div>
                  <span className="text-terminal-dim">Confidence</span>
                  <span className="block text-terminal-text">{(rec.confidence).toFixed(0)}%</span>
                </div>
                {rec.risk_reward_ratio != null && (
                  <div>
                    <span className="text-terminal-dim">R:R</span>
                    <span className="block text-terminal-text">{rec.risk_reward_ratio.toFixed(1)}</span>
                  </div>
                )}
              </div>

              <p className="text-[11px] text-terminal-muted line-clamp-2">
                {rec.primary_reason}
              </p>

              {rec.risk_warnings.length > 0 && (
                <p className="text-[10px] text-terminal-amber mt-2 truncate">
                  ⚠ {rec.risk_warnings[0]}
                </p>
              )}
            </Link>
          ))}
        </div>
      )}

      {/* Trending: Gainers & Losers */}
      {(gainers.length > 0 || losers.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Top Gainers */}
          <div className="card">
            <h2 className="text-sm font-semibold text-terminal-green mb-3">▲ Top Gainers</h2>
            <div className="space-y-1">
              {gainers.slice(0, 5).map((s) => (
                <Link
                  key={s.symbol}
                  href={`/stocks/${s.symbol}`}
                  className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-terminal-surface/50 text-xs font-mono"
                >
                  <div>
                    <span className="text-terminal-text font-medium">{s.symbol}</span>
                    <span className="text-terminal-dim ml-2 text-[10px]">{s.sector}</span>
                  </div>
                  <div className="text-right">
                    <span className="text-terminal-text">₦{s.todays_close.toFixed(2)}</span>
                    <span className="text-terminal-green ml-2">+{s.change_percent.toFixed(2)}%</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Top Losers */}
          <div className="card">
            <h2 className="text-sm font-semibold text-terminal-red mb-3">▼ Top Losers</h2>
            <div className="space-y-1">
              {losers.slice(0, 5).map((s) => (
                <Link
                  key={s.symbol}
                  href={`/stocks/${s.symbol}`}
                  className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-terminal-surface/50 text-xs font-mono"
                >
                  <div>
                    <span className="text-terminal-text font-medium">{s.symbol}</span>
                    <span className="text-terminal-dim ml-2 text-[10px]">{s.sector}</span>
                  </div>
                  <div className="text-right">
                    <span className="text-terminal-text">₦{s.todays_close.toFixed(2)}</span>
                    <span className="text-terminal-red ml-2">{s.change_percent.toFixed(2)}%</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
