/**
 * FastDashboard - Performance-Optimized Dashboard
 * 
 * CRITICAL FIXES:
 * 1. Pulse-first rendering (only /market/snapshot blocks first paint)
 * 2. Correct data wiring (ASI/Volume/Breadth from snapshot, NOT regime)
 * 3. Lazy-loaded heavy components
 * 4. Section-level loading states (no global spinner)
 * 5. SSE is fire-and-forget (never blocks)
 * 
 * Loading Order:
 * 1. Shell + Skeleton renders IMMEDIATELY
 * 2. Market snapshot fetched (< 200ms target)
 * 3. Banner renders with REAL ASI/Volume/Breadth
 * 4. Secondary data loads via requestIdleCallback
 * 5. Heavy components lazy-mount on scroll/click
 */

import React, { useState, useCallback, Suspense, lazy } from 'react';
import { useMarketDataProgressive } from '../core/hooks/useMarketData';
import { usePulse, useSummary } from '../core/hooks/useProgressiveData';
import { type Stock } from '../core';
import MarketRegimeBannerFast from '../components/dashboard/MarketRegimeBannerFast';

// Lazy-loaded heavy components
const StockScreener = lazy(() => import('../components/screener/StockScreener'));

// ============================================
// SKELETON COMPONENTS
// ============================================

const BannerSkeleton: React.FC = () => (
  <div className="card p-4 animate-pulse">
    <div className="flex items-center gap-4">
      <div className="w-10 h-10 rounded-lg bg-[var(--color-bg-tertiary)]" />
      <div className="flex-1">
        <div className="h-4 w-32 bg-[var(--color-bg-tertiary)] rounded mb-2" />
        <div className="h-3 w-48 bg-[var(--color-bg-tertiary)] rounded" />
      </div>
      <div className="hidden md:flex gap-6">
        <div className="w-16 h-12 bg-[var(--color-bg-tertiary)] rounded" />
        <div className="w-16 h-12 bg-[var(--color-bg-tertiary)] rounded" />
        <div className="w-16 h-12 bg-[var(--color-bg-tertiary)] rounded" />
      </div>
    </div>
  </div>
);

const CardSkeleton: React.FC<{ height?: string }> = ({ height = 'h-32' }) => (
  <div className={`card p-4 animate-pulse ${height}`}>
    <div className="h-4 w-24 bg-[var(--color-bg-tertiary)] rounded mb-4" />
    <div className="space-y-2">
      <div className="h-3 w-full bg-[var(--color-bg-tertiary)] rounded" />
      <div className="h-3 w-3/4 bg-[var(--color-bg-tertiary)] rounded" />
    </div>
  </div>
);

const TableSkeleton: React.FC = () => (
  <div className="card p-4 animate-pulse">
    <div className="h-4 w-24 bg-[var(--color-bg-tertiary)] rounded mb-4" />
    <div className="space-y-3">
      {[1, 2, 3, 4, 5].map(i => (
        <div key={i} className="flex gap-4">
          <div className="h-3 w-16 bg-[var(--color-bg-tertiary)] rounded" />
          <div className="h-3 w-20 bg-[var(--color-bg-tertiary)] rounded" />
          <div className="h-3 w-12 bg-[var(--color-bg-tertiary)] rounded" />
        </div>
      ))}
    </div>
  </div>
);

// ============================================
// QUICK MOVERS (Inline for fast load)
// ============================================

interface MoverStock {
  symbol: string;
  price: number;
  change_pct: number;
}

const QuickMoversInline: React.FC<{
  gainers: MoverStock[];
  losers: MoverStock[];
  loading: boolean;
  onStockClick?: (symbol: string) => void;
}> = ({ gainers, losers, loading, onStockClick }) => {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4">
        <CardSkeleton height="h-48" />
        <CardSkeleton height="h-48" />
      </div>
    );
  }

  const renderMover = (stock: MoverStock, type: 'gainer' | 'loser') => (
    <button
      key={stock.symbol}
      onClick={() => onStockClick?.(stock.symbol)}
      className="flex items-center justify-between p-2 rounded hover:bg-[var(--color-bg-tertiary)] transition-colors w-full text-left"
    >
      <div>
        <span className="font-medium text-sm text-[var(--color-text-primary)]">{stock.symbol}</span>
        <span className="text-xs text-[var(--color-text-tertiary)] ml-2">₦{stock.price.toFixed(2)}</span>
      </div>
      <span className={`font-mono text-sm font-medium ${type === 'gainer' ? 'text-emerald-400' : 'text-red-400'}`}>
        {stock.change_pct >= 0 ? '+' : ''}{stock.change_pct.toFixed(2)}%
      </span>
    </button>
  );

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Gainers */}
      <div className="card p-4">
        <h3 className="text-xs font-semibold text-emerald-400 uppercase tracking-wide mb-3 flex items-center gap-2">
          <span>↑</span> Top Gainers
        </h3>
        <div className="space-y-1">
          {gainers.length > 0 ? (
            gainers.slice(0, 5).map(s => renderMover(s, 'gainer'))
          ) : (
            <p className="text-xs text-[var(--color-text-tertiary)] p-2">No gainers today</p>
          )}
        </div>
      </div>

      {/* Losers */}
      <div className="card p-4">
        <h3 className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-3 flex items-center gap-2">
          <span>↓</span> Top Losers
        </h3>
        <div className="space-y-1">
          {losers.length > 0 ? (
            losers.slice(0, 5).map(s => renderMover(s, 'loser'))
          ) : (
            <p className="text-xs text-[var(--color-text-tertiary)] p-2">No losers today</p>
          )}
        </div>
      </div>
    </div>
  );
};

// ============================================
// MAIN DASHBOARD
// ============================================

const FastDashboard: React.FC = () => {
  // Market data with progressive loading
  const marketData = useMarketDataProgressive();
  
  // UI pulse/summary data
  const pulse = usePulse();
  const summary = useSummary(!pulse.loading);
  
  // Lazy mount flags
  const [showAllStocks, setShowAllStocks] = useState(false);
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [stocksLoading, setStocksLoading] = useState(false);

  // Handle stock click
  const handleStockClick = useCallback((symbol: string) => {
    console.log('Stock clicked:', symbol);
  }, []);

  // Lazy load stocks when "All Stocks" section is requested
  const loadAllStocks = useCallback(async () => {
    if (stocksLoading || stocks.length > 0) return;
    
    setStocksLoading(true);
    try {
      const response = await fetch('/api/v1/stocks');
      if (response.ok) {
        const data = await response.json();
        setStocks(data.stocks || data || []);
      }
    } catch (err) {
      console.error('Failed to load stocks:', err);
    } finally {
      setStocksLoading(false);
    }
  }, [stocksLoading, stocks.length]);

  // Prepare movers data from summary
  const gainers: MoverStock[] = summary.data?.movers?.gainers || [];
  const losers: MoverStock[] = summary.data?.movers?.losers || [];

  return (
    <div className="space-y-6 pb-8">
      {/* ================================================
          LAYER 1: MARKET BANNER (First Paint Critical)
          ================================================ */}
      {marketData.readyForPaint ? (
        <MarketRegimeBannerFast
          snapshot={marketData.snapshot}
          breadth={marketData.breadth}
          regime={marketData.regime}
          loading={false}
        />
      ) : (
        <BannerSkeleton />
      )}

      {/* ================================================
          LAYER 2: QUICK STATS + MOVERS
          ================================================ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Movers */}
        <div className="lg:col-span-2 space-y-6">
          {/* Quick Movers */}
          <QuickMoversInline
            gainers={gainers}
            losers={losers}
            loading={summary.loading}
            onStockClick={handleStockClick}
          />

          {/* Market Insight */}
          {marketData.readyForPaint && marketData.breadth && (
            <div className="card p-4 border-l-4 border-l-[var(--color-accent-primary)]">
              <div className="flex items-start gap-3">
                <svg className="w-5 h-5 text-[var(--color-accent-primary)] flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <h4 className="text-sm font-medium text-[var(--color-text-primary)] mb-1">
                    Market Breadth Analysis
                  </h4>
                  <p className="text-xs text-[var(--color-text-tertiary)] leading-relaxed">
                    {marketData.breadth.advancing > marketData.breadth.declining
                      ? `Buyers are in control with ${marketData.breadth.advancing} advancing stocks vs ${marketData.breadth.declining} declining.`
                      : marketData.breadth.declining > marketData.breadth.advancing
                      ? `Sellers dominate with ${marketData.breadth.declining} declining stocks vs ${marketData.breadth.advancing} advancing.`
                      : 'Market is balanced between buyers and sellers.'}
                    {marketData.breadth.is_estimated && (
                      <span className="text-amber-400 ml-1">(Estimated)</span>
                    )}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Lazy-loaded All Stocks Section */}
          <div className="mt-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wide">
                All Stocks
              </h2>
              {!showAllStocks && (
                <button
                  onClick={() => {
                    setShowAllStocks(true);
                    loadAllStocks();
                  }}
                  className="text-xs text-[var(--color-accent-primary)] hover:underline"
                >
                  Load full list →
                </button>
              )}
            </div>
            
            {showAllStocks ? (
              <Suspense fallback={<TableSkeleton />}>
                <StockScreener
                  stocks={stocks}
                  loading={stocksLoading}
                  onStockClick={handleStockClick}
                />
              </Suspense>
            ) : (
              <div className="card p-8 text-center">
                <p className="text-sm text-[var(--color-text-tertiary)]">
                  Click "Load full list" to view all stocks
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Right Column - Quick Stats */}
        <div className="space-y-6">
          {/* Market Snapshot Card */}
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wide mb-4">
              Market Snapshot
            </h3>
            
            {marketData.readyForPaint && marketData.snapshot ? (
              <div className="space-y-4">
                {/* ASI */}
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[var(--color-text-tertiary)]">ASI</span>
                  <div className="text-right">
                    <span className="font-mono text-sm text-[var(--color-text-primary)]">
                      {marketData.snapshot.asi.value.toLocaleString()}
                    </span>
                    <span className={`text-xs ml-2 ${marketData.snapshot.asi.change_percent >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {marketData.snapshot.asi.change_percent >= 0 ? '+' : ''}
                      {marketData.snapshot.asi.change_percent.toFixed(2)}%
                    </span>
                  </div>
                </div>

                {/* Breadth */}
                {marketData.breadth && (
                  <>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-[var(--color-text-tertiary)]">Advancers</span>
                      <span className="font-mono text-sm text-emerald-400">
                        {marketData.breadth.advancing}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-[var(--color-text-tertiary)]">Decliners</span>
                      <span className="font-mono text-sm text-red-400">
                        {marketData.breadth.declining}
                      </span>
                    </div>
                  </>
                )}

                <div className="border-t border-[var(--color-border-subtle)]" />

                {/* Volume */}
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[var(--color-text-tertiary)]">Volume</span>
                  <span className="font-mono text-sm text-[var(--color-text-primary)]">
                    {(marketData.snapshot.volume.total_volume / 1_000_000).toFixed(1)}M
                  </span>
                </div>

                {/* Value */}
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[var(--color-text-tertiary)]">Value</span>
                  <span className="font-mono text-sm text-[var(--color-text-primary)]">
                    ₦{(marketData.snapshot.volume.total_value / 1_000_000_000).toFixed(2)}B
                  </span>
                </div>
              </div>
            ) : (
              <div className="space-y-3 animate-pulse">
                {[1, 2, 3, 4].map(i => (
                  <div key={i} className="flex justify-between">
                    <div className="h-3 w-16 bg-[var(--color-bg-tertiary)] rounded" />
                    <div className="h-3 w-20 bg-[var(--color-bg-tertiary)] rounded" />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Data Source Badge */}
          <div className="card p-3">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${marketData.readyForPaint ? 'bg-emerald-400' : 'bg-amber-400'} animate-pulse`} />
                <span className="text-[var(--color-text-tertiary)]">
                  {marketData.readyForPaint ? 'Live Data' : 'Loading...'}
                </span>
              </div>
              <span className="text-[var(--color-text-tertiary)] font-mono">
                ngnmarket.com
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FastDashboard;
