/**
 * MarketRegimeBannerFast - Performance-Optimized Market Banner
 * 
 * CRITICAL DATA SEPARATION:
 * - ASI, Volume, Breadth → from MarketSnapshot (LIVE DATA)
 * - Regime label, confidence → from MarketRegime (CLASSIFICATION ONLY)
 * 
 * This component NEVER uses regime-derived values for display metrics.
 * All numeric values come directly from market snapshot API.
 */

import React from 'react';
import type { MarketSnapshot, MarketBreadth, MarketRegime } from '../../core/hooks/useMarketData';

interface MarketRegimeBannerFastProps {
  snapshot: MarketSnapshot | null;
  breadth: MarketBreadth | null;
  regime: MarketRegime | null;
  loading?: boolean;
}

const regimeConfig: Record<string, {
  label: string;
  description: string;
  color: string;
  bgColor: string;
  borderColor: string;
  icon: React.ReactNode;
}> = {
  bull: {
    label: 'Bull Market',
    description: 'Market trending upward. Favor momentum and growth.',
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-emerald-500/30',
    icon: (
      <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
      </svg>
    ),
  },
  bear: {
    label: 'Bear Market',
    description: 'Market trending downward. Prioritize capital preservation.',
    color: 'text-red-400',
    bgColor: 'bg-red-500/10',
    borderColor: 'border-red-500/30',
    icon: (
      <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 17h8m0 0v-8m0 8l-8-8-4 4-6-6" />
      </svg>
    ),
  },
  range_bound: {
    label: 'Range-Bound',
    description: 'Market moving sideways. Look for support/resistance plays.',
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500/30',
    icon: (
      <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h8M12 8v8" />
      </svg>
    ),
  },
  mean_reverting: {
    label: 'Range-Bound',
    description: 'Market moving sideways. Look for support/resistance plays.',
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500/30',
    icon: (
      <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h8M12 8v8" />
      </svg>
    ),
  },
  trending: {
    label: 'Trending',
    description: 'Strong directional movement. Follow the trend.',
    color: 'text-blue-400',
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500/30',
    icon: (
      <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
      </svg>
    ),
  },
  high_volatility: {
    label: 'High Volatility',
    description: 'Elevated market swings. Reduce position sizes.',
    color: 'text-orange-400',
    bgColor: 'bg-orange-500/10',
    borderColor: 'border-orange-500/30',
    icon: (
      <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  low_liquidity: {
    label: 'Low Liquidity',
    description: 'Thin trading volume. Exercise caution on entries/exits.',
    color: 'text-purple-400',
    bgColor: 'bg-purple-500/10',
    borderColor: 'border-purple-500/30',
    icon: (
      <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
      </svg>
    ),
  },
};

const defaultConfig = {
  label: 'Analyzing...',
  description: 'Determining market conditions.',
  color: 'text-gray-400',
  bgColor: 'bg-gray-500/10',
  borderColor: 'border-gray-500/30',
  icon: (
    <svg width="20" height="20" className="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
    </svg>
  ),
};

const MarketRegimeBannerFast: React.FC<MarketRegimeBannerFastProps> = ({
  snapshot,
  breadth,
  regime,
  loading = false,
}) => {
  // Loading skeleton
  if (loading || !snapshot) {
    return (
      <div className="card p-4 animate-pulse">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-[var(--color-bg-tertiary)]" />
          <div className="flex-1">
            <div className="h-4 w-32 bg-[var(--color-bg-tertiary)] rounded mb-2" />
            <div className="h-3 w-48 bg-[var(--color-bg-tertiary)] rounded" />
          </div>
        </div>
      </div>
    );
  }

  // Safety check: ASI should be > 100,000 for NGX
  if (snapshot.asi.value < 100000 && snapshot.asi.value > 0) {
    console.warn('[MarketRegimeBanner] ASI value suspiciously low:', snapshot.asi.value);
  }

  // Get regime config (classification only)
  const regimeKey = regime?.regime?.toLowerCase() || 'range_bound';
  const config = regimeConfig[regimeKey] || defaultConfig;

  // Calculate breadth ratio for bar (from SNAPSHOT, not regime)
  const breadthTotal = breadth 
    ? breadth.advancing + breadth.declining + breadth.unchanged 
    : 0;
  const breadthRatio = breadthTotal > 0 
    ? (breadth!.advancing / breadthTotal) * 100 
    : 50;

  return (
    <div className={`card border ${config.borderColor} ${config.bgColor} p-4`}>
      <div className="flex items-start justify-between gap-4">
        {/* Left: Regime Info (TEXT ONLY from regime engine) */}
        <div className="flex items-start gap-4">
          <div className={`p-2.5 rounded-lg ${config.bgColor} ${config.color}`}>
            {config.icon}
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h2 className={`text-lg font-semibold ${config.color}`}>
                {config.label}
              </h2>
              {regime && (
                <span className="text-xs text-[var(--color-text-tertiary)] font-mono">
                  {regime.confidence <= 1 ? (regime.confidence * 100).toFixed(0) : regime.confidence}% confidence
                </span>
              )}
            </div>
            <p className="text-sm text-[var(--color-text-secondary)]">
              {config.description}
            </p>
          </div>
        </div>

        {/* Right: Key Metrics (ALL from SNAPSHOT, never from regime) */}
        <div className="hidden md:flex items-center gap-6">
          {/* ASI - from snapshot.asi */}
          <div className="text-right">
            <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">ASI</p>
            <p className="font-mono text-lg font-semibold text-[var(--color-text-primary)]">
              {snapshot.asi.value.toLocaleString()}
            </p>
            <p className={`text-xs font-mono ${
              snapshot.asi.change_percent >= 0 
                ? 'text-emerald-400' 
                : 'text-red-400'
            }`}>
              {snapshot.asi.change_percent >= 0 ? '+' : ''}
              {snapshot.asi.change_percent.toFixed(2)}%
            </p>
          </div>

          {/* Breadth - from breadth API, NOT regime */}
          {breadth && (
            <div className="text-right">
              <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">
                Breadth
                {breadth.is_estimated && <span className="text-amber-400 ml-1">*</span>}
              </p>
              <div className="flex items-center gap-2 justify-end">
                <span className="text-emerald-400 font-mono text-sm">{breadth.advancing}</span>
                <span className="text-[var(--color-text-tertiary)]">/</span>
                <span className="text-red-400 font-mono text-sm">{breadth.declining}</span>
              </div>
              <div className="w-20 h-1.5 bg-[var(--color-bg-tertiary)] rounded-full mt-1 overflow-hidden">
                <div 
                  className="h-full bg-emerald-400 rounded-full transition-all duration-500"
                  style={{ width: `${breadthRatio}%` }}
                />
              </div>
            </div>
          )}

          {/* Volume - from snapshot.volume */}
          <div className="text-right">
            <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">Volume</p>
            <p className="font-mono text-sm text-[var(--color-text-primary)]">
              {(snapshot.volume.total_volume / 1_000_000).toFixed(1)}M
            </p>
            <p className="text-xs text-[var(--color-text-tertiary)]">
              ₦{(snapshot.volume.total_value / 1_000_000_000).toFixed(2)}B
            </p>
          </div>
        </div>
      </div>

      {/* Warnings from regime engine */}
      {regime?.warnings && regime.warnings.length > 0 && (
        <div className="mt-3 pt-3 border-t border-[var(--color-border-subtle)]">
          <div className="flex items-start gap-2">
            <svg className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <p className="text-xs text-amber-400">
              {regime.warnings[0]}
            </p>
          </div>
        </div>
      )}

      {/* Data source indicator */}
      <div className="mt-3 pt-2 border-t border-[var(--color-border-subtle)] flex items-center justify-between">
        <span className="text-[10px] text-[var(--color-text-tertiary)]">
          Source: {snapshot.source}
        </span>
        {breadth?.is_estimated && (
          <span className="text-[10px] text-amber-400">
            * Breadth is estimated
          </span>
        )}
      </div>
    </div>
  );
};

export default MarketRegimeBannerFast;
