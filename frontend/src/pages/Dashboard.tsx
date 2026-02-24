/**
 * Dashboard Page - Main market overview
 * 
 * This is the primary landing experience. It answers:
 * "What is the market doing and what should I pay attention to?"
 * 
 * Information hierarchy:
 * 1. Market regime (Bull/Bear/Range)
 * 2. Top opportunities
 * 3. Market movers
 * 4. Sector overview
 */

import React, { useState, useEffect, useCallback } from 'react';
import MarketRegimeBanner from '../components/dashboard/MarketRegimeBanner';
import TopOpportunities from '../components/dashboard/TopOpportunities';
import MoversPanel from '../components/dashboard/MoversPanel';
import SectorOverview from '../components/dashboard/SectorOverview';
import MarketInsight from '../components/dashboard/MarketInsight';
import StockScreener from '../components/screener/StockScreener';
import { 
  stocksService, 
  recommendationsService,
  type Stock, 
  type Recommendation, 
  type MarketRegime 
} from '../core';
import { useProgressiveData } from '../core/hooks/useProgressiveData';

type TimeHorizon = 'short_term' | 'swing' | 'long_term';

interface MarketSummary {
  asi: { value: number; change: number; change_percent: number };
  breadth: { advancing: number; declining: number; unchanged: number; ratio: number };
  volume: { total_volume: number; total_value: number };
  sectors: never[];
  stock_count: number;
  timestamp: string;
}

const Dashboard: React.FC = () => {
  // Progressive data loading (3-layer pattern)
  // Layer 1: pulse (instant), Layer 2: summary (fast), Layer 3: stocks (full)
  const { pulse, summary } = useProgressiveData();
  
  // Additional state for full data (Layer 3)
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [marketRegime, setMarketRegime] = useState<MarketRegime | null>(null);
  const [marketSummary, setMarketSummary] = useState<MarketSummary | null>(null);
  const [selectedHorizon, setSelectedHorizon] = useState<TimeHorizon>('swing');
  
  // Loading states (Layer 3 only - Layers 1&2 use progressive hooks)
  const [loadingStocks, setLoadingStocks] = useState(true);
  const [loadingRecommendations, setLoadingRecommendations] = useState(true);
  const [loadingRegime, setLoadingRegime] = useState(true);
  
  // Error state
  const [error, setError] = useState<string | null>(null);
  
  // Last updated timestamp
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  
  // Sync progressive data with local state for compatibility
  useEffect(() => {
    if (summary.data && summary.data.breadth) {
      const b = summary.data.breadth;
      const asiValue = (pulse.data?.market as { asi?: number })?.asi || 0;
      const asiPct = pulse.data?.market?.asi_change_pct || 0;
      
      setMarketSummary({
        asi: { value: asiValue, change: 0, change_percent: asiPct },
        breadth: {
          advancing: b.advancing,
          declining: b.declining,
          unchanged: b.unchanged,
          ratio: b.ratio,
        },
        volume: { total_volume: 0, total_value: 0 },
        sectors: [],
        stock_count: b.total,
        timestamp: summary.data.timestamp,
      });
    }
  }, [summary.data, pulse.data]);
  
  // Sync regime from pulse (fast first paint)
  useEffect(() => {
    if (pulse.data?.market?.regime && pulse.data.market.regime !== 'unknown') {
      // Only update if we don't have a regime yet (avoid overwriting detailed regime)
      if (!marketRegime) {
        setLoadingRegime(false);
      }
    }
  }, [pulse.data, marketRegime]);

  // Fetch stocks
  const fetchStocks = useCallback(async () => {
    try {
      setLoadingStocks(true);
      const data = await stocksService.getAll();
      setStocks(data);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Failed to fetch stocks:', err);
      setError('Failed to load market data');
    } finally {
      setLoadingStocks(false);
    }
  }, []);

  // Fetch recommendations
  const fetchRecommendations = useCallback(async () => {
    try {
      setLoadingRecommendations(true);
      const data = await recommendationsService.getTop({ 
        horizon: selectedHorizon, 
        limit: 10 
      });
      setRecommendations(data);
    } catch (err) {
      console.error('Failed to fetch recommendations:', err);
      // Don't set error - recommendations are optional enhancement
    } finally {
      setLoadingRecommendations(false);
    }
  }, [selectedHorizon]);

  // Fetch market regime
  const fetchMarketRegime = useCallback(async () => {
    try {
      setLoadingRegime(true);
      const data = await recommendationsService.getMarketRegime();
      setMarketRegime(data);
    } catch (err) {
      console.error('Failed to fetch market regime:', err);
      // Don't set error - regime is optional enhancement
    } finally {
      setLoadingRegime(false);
    }
  }, []);

  // Fetch REAL market data from API (ASI, Volume, Breadth)
  const fetchMarketSnapshot = useCallback(async () => {
    try {
      // Fetch snapshot for ASI and volume
      const snapshotRes = await fetch('/api/v1/market/snapshot');
      const snapshotData = await snapshotRes.json();
      
      // Fetch breadth data
      const breadthRes = await fetch('/api/v1/market/breadth');
      const breadthData = await breadthRes.json();
      
      if (snapshotData.success && snapshotData.data) {
        const s = snapshotData.data;
        const b = breadthData.success ? breadthData.data : null;
        
        // Safety check: ASI should be > 100,000 for NGX
        if (s.asi < 100000 && s.asi > 0) {
          console.warn('[Dashboard] ASI value suspiciously low:', s.asi);
        }
        
        setMarketSummary({
          asi: {
            value: s.asi || 0,
            change: s.asi_change || 0,
            change_percent: s.asi_change_percent || 0,
          },
          breadth: {
            advancing: b?.advancing || 0,
            declining: b?.declining || 0,
            unchanged: b?.unchanged || 0,
            ratio: b?.ratio || 0,
          },
          volume: {
            total_volume: s.volume || 0,
            total_value: s.value_traded || 0,
          },
          sectors: [],
          stock_count: stocks.length,
          timestamp: new Date().toISOString(),
        });
      }
    } catch (err) {
      console.error('Failed to fetch market snapshot:', err);
      // Fallback to stock-based calculation if API fails
      if (stocks.length > 0) {
        const advancing = stocks.filter(s => (s.change_percent || 0) > 0).length;
        const declining = stocks.filter(s => (s.change_percent || 0) < 0).length;
        const unchanged = stocks.length - advancing - declining;
        const totalVolume = stocks.reduce((sum, s) => sum + (s.volume || 0), 0);
        
        setMarketSummary({
          asi: { value: 0, change: 0, change_percent: 0 },
          breadth: {
            advancing,
            declining,
            unchanged,
            ratio: declining > 0 ? advancing / declining : advancing,
          },
          volume: {
            total_volume: totalVolume,
            total_value: totalVolume * 50,
          },
          sectors: [],
          stock_count: stocks.length,
          timestamp: new Date().toISOString(),
        });
      }
    }
  }, [stocks.length]);

  // Fetch market snapshot on mount
  useEffect(() => {
    fetchMarketSnapshot();
  }, [fetchMarketSnapshot]);

  // Initial data fetch
  useEffect(() => {
    fetchStocks();
    fetchRecommendations();
    fetchMarketRegime();
  }, [fetchStocks, fetchRecommendations, fetchMarketRegime]);

  // Refetch recommendations when horizon changes
  useEffect(() => {
    fetchRecommendations();
  }, [selectedHorizon, fetchRecommendations]);

  // Auto-refresh every 60 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchStocks();
    }, 60000);
    return () => clearInterval(interval);
  }, [fetchStocks]);

  // Handle stock click
  const handleStockClick = (symbol: string) => {
    // TODO: Navigate to stock detail page or open modal
    console.log('Stock clicked:', symbol);
  };

  return (
    <div className="space-y-6 pb-8">
      {/* Error Banner */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 flex items-center gap-3">
          <svg width="16" height="16" className="w-4 h-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm text-red-400">{error}</p>
          <button 
            onClick={() => {
              setError(null);
              fetchStocks();
            }}
            className="ml-auto text-xs text-red-400 hover:text-red-300 underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Market Regime Banner */}
      <MarketRegimeBanner 
        regime={marketRegime}
        summary={marketSummary}
        loading={loadingRegime && loadingStocks}
      />

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Opportunities */}
        <div className="lg:col-span-2 space-y-6">
          {/* Top Opportunities */}
          <TopOpportunities
            recommendations={recommendations}
            horizon={selectedHorizon}
            onHorizonChange={setSelectedHorizon}
            onStockClick={handleStockClick}
            loading={loadingRecommendations}
          />

          {/* Market Insight - Beginner friendly */}
          <MarketInsight
            regime={marketRegime}
            advancers={marketSummary?.breadth.advancing || 0}
            decliners={marketSummary?.breadth.declining || 0}
            totalStocks={stocks.length}
            loading={loadingRegime}
          />

          {/* Market Movers */}
          <MoversPanel
            stocks={stocks}
            loading={loadingStocks}
            onStockClick={handleStockClick}
          />

          {/* Full Stock Screener */}
          <div className="mt-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wide">
                All Stocks
              </h2>
            </div>
            <StockScreener
              stocks={stocks}
              loading={loadingStocks}
              onStockClick={handleStockClick}
            />
          </div>
        </div>

        {/* Right Column - Quick Stats & Insights */}
        <div className="space-y-6">
          {/* Quick Stats */}
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wide mb-4">
              Market Snapshot
            </h3>
            
            <div className="space-y-4">
              {/* Total Stocks */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--color-text-tertiary)]">Active Stocks</span>
                <span className="font-mono text-sm text-[var(--color-text-primary)]">
                  {loadingStocks ? '—' : stocks.length}
                </span>
              </div>

              {/* Breadth */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--color-text-tertiary)]">Advancers</span>
                <span className="font-mono text-sm text-emerald-400">
                  {loadingStocks ? '—' : marketSummary?.breadth.advancing || 0}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--color-text-tertiary)]">Decliners</span>
                <span className="font-mono text-sm text-red-400">
                  {loadingStocks ? '—' : marketSummary?.breadth.declining || 0}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--color-text-tertiary)]">Unchanged</span>
                <span className="font-mono text-sm text-[var(--color-text-secondary)]">
                  {loadingStocks ? '—' : marketSummary?.breadth.unchanged || 0}
                </span>
              </div>

              {/* Divider */}
              <div className="border-t border-[var(--color-border-subtle)]"></div>

              {/* Volume */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--color-text-tertiary)]">Total Volume</span>
                <span className="font-mono text-sm text-[var(--color-text-primary)]">
                  {loadingStocks ? '—' : `${((marketSummary?.volume.total_volume || 0) / 1_000_000).toFixed(1)}M`}
                </span>
              </div>
            </div>
          </div>

          {/* Sector Overview */}
          <SectorOverview
            stocks={stocks}
            loading={loadingStocks}
            onSectorClick={(sector) => console.log('Sector clicked:', sector)}
          />

          {/* Beginner Tip */}
          <div className="card p-4 border-l-4 border-l-[var(--color-accent-primary)]">
            <div className="flex items-start gap-3">
              <svg width="20" height="20" className="w-5 h-5 text-[var(--color-accent-primary)] flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <h4 className="text-sm font-medium text-[var(--color-text-primary)] mb-1">
                  New to Nigerian Stocks?
                </h4>
                <p className="text-xs text-[var(--color-text-tertiary)] leading-relaxed">
                  Start with high-liquidity stocks like GTCO, Zenith, or Dangote Cement. 
                  These trade frequently and have tighter spreads, making them easier to buy and sell.
                </p>
                <button className="text-xs text-[var(--color-accent-primary)] hover:underline mt-2">
                  Learn more →
                </button>
              </div>
            </div>
          </div>

          {/* Data Freshness */}
          <div className="card p-3">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span className="text-[var(--color-text-tertiary)]">Live Data</span>
              </div>
              <span className="text-[var(--color-text-tertiary)] font-mono">
                {lastUpdated 
                  ? `Updated ${lastUpdated.toLocaleTimeString()}`
                  : 'Loading...'
                }
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
