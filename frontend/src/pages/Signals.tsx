/**
 * Signals Page - Advanced Investor Workspace
 * 
 * Full signals view with filtering by horizon, action, and sector.
 * Designed for active traders who want detailed signal analysis.
 */

import React, { useState, useEffect, useCallback } from 'react';
import SignalCard from '../components/signals/SignalCard';
import { 
  recommendationsService, 
  EmptyState,
  type Recommendation, 
  type MarketRegime 
} from '../core';

type TimeHorizon = 'short_term' | 'swing' | 'long_term';
type ActionFilter = 'all' | 'buy' | 'sell';

const Signals: React.FC = () => {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [marketRegime, setMarketRegime] = useState<MarketRegime | null>(null);
  const [horizon, setHorizon] = useState<TimeHorizon>('swing');
  const [actionFilter, setActionFilter] = useState<ActionFilter>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRecommendations = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await recommendationsService.getTop({ 
        horizon, 
        limit: 20 
      });
      setRecommendations(data);
    } catch (err) {
      console.error('Failed to fetch recommendations:', err);
      setError('Failed to load signals. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [horizon]);

  const fetchMarketRegime = useCallback(async () => {
    try {
      const data = await recommendationsService.getMarketRegime();
      setMarketRegime(data);
    } catch (err) {
      console.error('Failed to fetch market regime:', err);
    }
  }, []);

  useEffect(() => {
    fetchRecommendations();
    fetchMarketRegime();
  }, [fetchRecommendations, fetchMarketRegime]);

  // Filter recommendations
  const filteredRecs = recommendations.filter(rec => {
    if (actionFilter === 'buy') {
      return rec.action === 'STRONG_BUY' || rec.action === 'BUY';
    }
    if (actionFilter === 'sell') {
      return rec.action === 'STRONG_SELL' || rec.action === 'SELL';
    }
    return true;
  });

  const horizonLabels: Record<TimeHorizon, { label: string; description: string }> = {
    short_term: { label: 'Day Trade', description: '1-5 days' },
    swing: { label: 'Swing', description: '1-4 weeks' },
    long_term: { label: 'Position', description: '3+ months' },
  };

  return (
    <div className="space-y-6 pb-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">
            Trading Signals
          </h1>
          <p className="text-sm text-[var(--color-text-tertiary)] mt-1">
            AI-generated recommendations with full methodology transparency
          </p>
        </div>

        {/* Market Regime Badge */}
        {marketRegime && (
          <div className={`px-3 py-2 rounded-lg text-sm ${
            marketRegime.regime === 'bull' ? 'bg-emerald-500/10 text-emerald-400' :
            marketRegime.regime === 'bear' ? 'bg-red-500/10 text-red-400' :
            'bg-amber-500/10 text-amber-400'
          }`}>
            <span className="font-medium">{marketRegime.regime.replace('_', ' ').toUpperCase()}</span>
            <span className="text-xs ml-2 opacity-75">
              {marketRegime.confidence <= 1 ? (marketRegime.confidence * 100).toFixed(0) : marketRegime.confidence}% conf
            </span>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="card p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Horizon Selector */}
          <div>
            <label className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide block mb-2">
              Time Horizon
            </label>
            <div className="flex items-center gap-1 p-1 bg-[var(--color-bg-tertiary)] rounded-lg">
              {(Object.keys(horizonLabels) as TimeHorizon[]).map((h) => (
                <button
                  key={h}
                  onClick={() => setHorizon(h)}
                  className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                    horizon === h
                      ? 'bg-[var(--color-accent-primary)] text-white'
                      : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
                  }`}
                >
                  <span>{horizonLabels[h].label}</span>
                  <span className="hidden sm:inline text-xs opacity-75 ml-1">({horizonLabels[h].description})</span>
                </button>
              ))}
            </div>
          </div>

          {/* Action Filter */}
          <div>
            <label className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide block mb-2">
              Signal Type
            </label>
            <div className="flex items-center gap-1 p-1 bg-[var(--color-bg-tertiary)] rounded-lg">
              {(['all', 'buy', 'sell'] as ActionFilter[]).map((action) => (
                <button
                  key={action}
                  onClick={() => setActionFilter(action)}
                  className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                    actionFilter === action
                      ? action === 'buy' 
                        ? 'bg-emerald-500 text-white'
                        : action === 'sell'
                          ? 'bg-red-500 text-white'
                          : 'bg-[var(--color-accent-primary)] text-white'
                      : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
                  }`}
                >
                  {action === 'all' ? 'All Signals' : action === 'buy' ? 'Buy Only' : 'Sell Only'}
                </button>
              ))}
            </div>
          </div>

          {/* Results count */}
          <div className="ml-auto text-sm text-[var(--color-text-tertiary)]">
            {loading ? 'Loading...' : `${filteredRecs.length} signals`}
          </div>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 flex items-center gap-3">
          <svg width="20" height="20" className="w-5 h-5 text-red-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm text-red-400">{error}</p>
          <button 
            onClick={fetchRecommendations}
            className="ml-auto text-xs text-red-400 hover:text-red-300 underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="card p-4 animate-pulse">
              <div className="flex items-center gap-4">
                <div className="h-8 w-24 bg-[var(--color-bg-tertiary)] rounded-lg"></div>
                <div className="flex-1">
                  <div className="h-4 w-32 bg-[var(--color-bg-tertiary)] rounded mb-2"></div>
                  <div className="h-3 w-48 bg-[var(--color-bg-tertiary)] rounded"></div>
                </div>
                <div className="h-6 w-16 bg-[var(--color-bg-tertiary)] rounded"></div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && filteredRecs.length === 0 && (
        <div className="card">
          <EmptyState
            variant="signals"
            title="No signals match your criteria"
            description={actionFilter !== 'all' 
              ? `No ${actionFilter} signals for the ${horizonLabels[horizon].label.toLowerCase()} timeframe.`
              : 'Try adjusting your filters or check back later.'}
            reason={marketRegime 
              ? `Market: ${marketRegime.regime.replace('_', ' ')} • ${recommendations.length} stocks analyzed`
              : `${recommendations.length} stocks analyzed`}
            action={actionFilter !== 'all' ? {
              label: 'Show all signals',
              onClick: () => setActionFilter('all')
            } : undefined}
          />
        </div>
      )}

      {/* Signals Grid */}
      {!loading && !error && filteredRecs.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filteredRecs.map((rec) => (
            <SignalCard
              key={`${rec.symbol}-${rec.horizon}`}
              recommendation={rec}
              onStockClick={(symbol) => console.log('Stock clicked:', symbol)}
            />
          ))}
        </div>
      )}

      {/* Disclaimer */}
      <div className="card p-4 text-xs text-[var(--color-text-tertiary)] leading-relaxed">
        <strong className="text-[var(--color-text-secondary)]">Disclaimer:</strong> These signals are generated by algorithmic analysis and should not be considered financial advice. 
        Always conduct your own research and consider your risk tolerance before making investment decisions. 
        Past performance does not guarantee future results. The Nigerian stock market carries significant risks including liquidity constraints.
      </div>
    </div>
  );
};

export default Signals;
