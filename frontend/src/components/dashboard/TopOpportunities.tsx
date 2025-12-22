/**
 * TopOpportunities - Curated actionable recommendations
 * 
 * Shows the best risk-adjusted opportunities right now.
 * Designed for decision-making, not data browsing.
 */

import React from 'react';
import { EmptyState, type Recommendation } from '../../core';

type TimeHorizon = 'short_term' | 'swing' | 'long_term';

interface TopOpportunitiesProps {
  recommendations: Recommendation[];
  horizon: TimeHorizon;
  onHorizonChange: (horizon: TimeHorizon) => void;
  onStockClick: (symbol: string) => void;
  loading?: boolean;
}

const horizonLabels: Record<TimeHorizon, { label: string; description: string }> = {
  short_term: { label: 'Day Trade', description: '1-5 days' },
  swing: { label: 'Swing', description: '1-4 weeks' },
  long_term: { label: 'Position', description: '3+ months' },
};

const actionConfig: Record<string, {
  label: string;
  color: string;
  bgColor: string;
}> = {
  STRONG_BUY: { label: 'Strong Buy', color: 'text-emerald-400', bgColor: 'bg-emerald-500/15' },
  BUY: { label: 'Buy', color: 'text-emerald-300', bgColor: 'bg-emerald-500/10' },
  HOLD: { label: 'Hold', color: 'text-amber-400', bgColor: 'bg-amber-500/10' },
  SELL: { label: 'Sell', color: 'text-red-300', bgColor: 'bg-red-500/10' },
  STRONG_SELL: { label: 'Strong Sell', color: 'text-red-400', bgColor: 'bg-red-500/15' },
  AVOID: { label: 'Avoid', color: 'text-gray-400', bgColor: 'bg-gray-500/10' },
};

const TopOpportunities: React.FC<TopOpportunitiesProps> = ({
  recommendations,
  horizon,
  onHorizonChange,
  onStockClick,
  loading = false,
}) => {
  // Filter to only show actionable recommendations (BUY/STRONG_BUY)
  const buyRecs = recommendations.filter(r => 
    r.action === 'STRONG_BUY' || r.action === 'BUY'
  ).slice(0, 3);

  return (
    <div className="card p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wide">
            Top Opportunities
          </h3>
          <p className="text-xs text-[var(--color-text-tertiary)] mt-0.5">
            Best risk-adjusted signals right now
          </p>
        </div>
        
        {/* Horizon Selector */}
        <div className="flex items-center gap-1 p-1 bg-[var(--color-bg-tertiary)] rounded-lg">
          {(Object.keys(horizonLabels) as TimeHorizon[]).map((h) => (
            <button
              key={h}
              onClick={() => onHorizonChange(h)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                horizon === h
                  ? 'bg-[var(--color-accent-primary)] text-white'
                  : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
              }`}
            >
              {horizonLabels[h].label}
            </button>
          ))}
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg animate-pulse">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-[var(--color-bg-hover)]"></div>
                <div className="flex-1">
                  <div className="h-4 w-20 bg-[var(--color-bg-hover)] rounded mb-2"></div>
                  <div className="h-3 w-32 bg-[var(--color-bg-hover)] rounded"></div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && buyRecs.length === 0 && (
        <EmptyState
          variant="signals"
          title="No buy signals right now"
          description="Market conditions or risk levels don't support new entries at this time."
          reason={`${horizonLabels[horizon].label} timeframe • Checking ${recommendations.length} stocks`}
          compact
        />
      )}

      {/* Recommendations List */}
      {!loading && buyRecs.length > 0 && (
        <div className="space-y-3">
          {buyRecs.map((rec, index) => {
            const config = actionConfig[rec.action];
            return (
              <button
                key={rec.symbol}
                onClick={() => onStockClick(rec.symbol)}
                className="w-full p-3 bg-[var(--color-bg-tertiary)] rounded-lg hover:bg-[var(--color-bg-hover)] transition-colors text-left group"
              >
                <div className="flex items-start gap-3">
                  {/* Rank */}
                  <div className="w-8 h-8 rounded-lg bg-[var(--color-bg-hover)] flex items-center justify-center text-sm font-bold text-[var(--color-text-tertiary)] group-hover:bg-[var(--color-accent-primary)] group-hover:text-white transition-colors">
                    {index + 1}
                  </div>

                  {/* Stock Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-[var(--color-text-primary)]">
                        {rec.symbol}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${config.bgColor} ${config.color}`}>
                        {config.label}
                      </span>
                      <span className="text-xs text-[var(--color-text-tertiary)] font-mono">
                        {rec.confidence}%
                      </span>
                    </div>
                    <p className="text-xs text-[var(--color-text-secondary)] truncate">
                      {rec.primary_reason}
                    </p>
                  </div>

                  {/* Price & Target */}
                  <div className="text-right">
                    <p className="font-mono text-sm text-[var(--color-text-primary)]">
                      ₦{rec.current_price?.toFixed(2)}
                    </p>
                    {rec.entry_exit && (
                      <p className="text-xs text-emerald-400 font-mono">
                        → ₦{rec.entry_exit.target_1?.toFixed(2)}
                      </p>
                    )}
                  </div>
                </div>

                {/* Risk Warning */}
                {rec.liquidity_warning && (
                  <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-400">
                    <svg width="16" height="16" className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01" />
                    </svg>
                    <span>{rec.liquidity_warning}</span>
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* View All Link */}
      {!loading && buyRecs.length > 0 && (
        <button className="w-full mt-4 py-2 text-xs font-medium text-[var(--color-accent-primary)] hover:text-[var(--color-text-primary)] transition-colors">
          View all {horizon === 'short_term' ? 'day trade' : horizon === 'swing' ? 'swing' : 'position'} signals →
        </button>
      )}
    </div>
  );
};

export default TopOpportunities;
