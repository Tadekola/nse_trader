/**
 * MarketRegimeBanner - Primary market status indicator
 * 
 * This is the FIRST thing users see. It answers:
 * "What is the market doing right now, and what does it mean for me?"
 * 
 * Design: Prominent but not alarming. Institutional, not casino.
 */

import React from 'react';
import type { MarketRegime } from '../../core';

interface MarketSummary {
  asi?: { value: number; change: number; change_percent: number };
  breadth?: { advancing: number; declining: number; unchanged: number; ratio: number };
  volume?: { total_volume: number; total_value: number };
  stock_count?: number;
  timestamp?: string;
}

interface MarketRegimeBannerProps {
  regime: MarketRegime | null;
  summary: MarketSummary | null;
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
  crisis: {
    label: 'Crisis Mode',
    description: 'Extreme conditions. Consider staying on sidelines.',
    color: 'text-red-500',
    bgColor: 'bg-red-500/15',
    borderColor: 'border-red-500/40',
    icon: (
      <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  },
};

const MarketRegimeBanner: React.FC<MarketRegimeBannerProps> = ({ 
  regime, 
  summary,
  loading = false 
}) => {
  if (loading) {
    return (
      <div className="card p-4 animate-pulse">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-[var(--color-bg-tertiary)]"></div>
          <div className="flex-1">
            <div className="h-4 w-32 bg-[var(--color-bg-tertiary)] rounded mb-2"></div>
            <div className="h-3 w-48 bg-[var(--color-bg-tertiary)] rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  const config = regime ? regimeConfig[regime.regime] || regimeConfig.range_bound : regimeConfig.range_bound;
  
  const breadthRatio = summary?.breadth 
    ? ((summary.breadth.advancing / (summary.breadth.advancing + summary.breadth.declining + summary.breadth.unchanged)) * 100)
    : 50;

  return (
    <div className={`card border ${config.borderColor} ${config.bgColor} p-4`}>
      <div className="flex items-start justify-between gap-4">
        {/* Left: Regime Info */}
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
            {regime?.recommended_strategy && (
              <p className="text-xs text-[var(--color-text-tertiary)] mt-1">
                <span className="font-medium">Strategy:</span> {regime.recommended_strategy}
              </p>
            )}
          </div>
        </div>

        {/* Right: Key Metrics */}
        {summary && (
          <div className="hidden md:flex items-center gap-6">
            {/* ASI */}
            <div className="text-right">
              <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">ASI</p>
              <p className="font-mono text-lg font-semibold text-[var(--color-text-primary)]">
                {summary.asi?.value?.toLocaleString() || '—'}
              </p>
              <p className={`text-xs font-mono ${
                (summary.asi?.change_percent || 0) >= 0 
                  ? 'text-emerald-400' 
                  : 'text-red-400'
              }`}>
                {(summary.asi?.change_percent || 0) >= 0 ? '+' : ''}
                {summary.asi?.change_percent?.toFixed(2) || '0.00'}%
              </p>
            </div>

            {/* Breadth */}
            <div className="text-right">
              <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">Breadth</p>
              <div className="flex items-center gap-2 justify-end">
                <span className="text-emerald-400 font-mono text-sm">{summary.breadth?.advancing || 0}</span>
                <span className="text-[var(--color-text-tertiary)]">/</span>
                <span className="text-red-400 font-mono text-sm">{summary.breadth?.declining || 0}</span>
              </div>
              <div className="w-20 h-1.5 bg-[var(--color-bg-tertiary)] rounded-full mt-1 overflow-hidden">
                <div 
                  className="h-full bg-emerald-400 rounded-full transition-all duration-500"
                  style={{ width: `${breadthRatio}%` }}
                />
              </div>
            </div>

            {/* Volume */}
            <div className="text-right">
              <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">Volume</p>
              <p className="font-mono text-sm text-[var(--color-text-primary)]">
                {summary.volume?.total_volume 
                  ? `${(summary.volume.total_volume / 1_000_000).toFixed(1)}M`
                  : '—'}
              </p>
              <p className="text-xs text-[var(--color-text-tertiary)]">
                ₦{summary.volume?.total_value 
                  ? `${(summary.volume.total_value / 1_000_000_000).toFixed(2)}B`
                  : '—'}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Warnings */}
      {regime?.warnings && regime.warnings.length > 0 && (
        <div className="mt-3 pt-3 border-t border-[var(--color-border-subtle)]">
          <div className="flex items-start gap-2">
            <svg width="16" height="16" className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <p className="text-xs text-amber-400">
              {regime.warnings[0]}
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default MarketRegimeBanner;
