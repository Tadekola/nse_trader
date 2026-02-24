/**
 * Market Data Hooks - Separated by Concern
 * 
 * These hooks enforce strict data separation:
 * - useMarketSnapshot: ASI, Volume, Breadth (from /api/v1/market/snapshot + /market/breadth)
 * - useMarketRegime: Regime label, confidence, description (from /api/v1/market/regime)
 * 
 * CRITICAL: Snapshot data must NEVER come from regime engine.
 * Regime provides classification ONLY, not market metrics.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { API_BASE_URL } from '../api/client';

// ============================================
// TYPES
// ============================================

export interface MarketSnapshot {
  asi: {
    value: number;
    change: number;
    change_percent: number;
  };
  volume: {
    total_volume: number;
    total_value: number;
  };
  market_cap: number;
  deals: number;
  timestamp: string;
  source: string;
}

export interface MarketBreadth {
  advancing: number;
  declining: number;
  unchanged: number;
  total: number;
  ratio: number;
  sentiment: string;
  is_estimated: boolean;
}

export interface MarketRegime {
  regime: string;
  confidence: number;
  trend_direction: string;
  reasoning: string;
  warnings: string[];
}

export interface CombinedMarketData {
  snapshot: MarketSnapshot | null;
  breadth: MarketBreadth | null;
  regime: MarketRegime | null;
}

// ============================================
// SNAPSHOT HOOK (ASI, Volume, Market Cap)
// ============================================

export function useMarketSnapshot() {
  const [data, setData] = useState<MarketSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchSnapshot = useCallback(async () => {
    // Abort previous request
    if (abortRef.current) {
      abortRef.current.abort();
    }
    abortRef.current = new AbortController();

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/market/snapshot`, {
        signal: abortRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const json = await response.json();
      
      if (json.success && json.data) {
        const d = json.data;
        
        // Safety check: ASI should be > 100,000 for NGX
        if (d.asi < 100000) {
          console.warn('[MarketSnapshot] ASI value suspiciously low:', d.asi);
        }
        
        setData({
          asi: {
            value: d.asi || 0,
            change: d.asi_change || 0,
            change_percent: d.asi_change_percent || 0,
          },
          volume: {
            total_volume: d.volume || 0,
            total_value: d.value || 0,
          },
          market_cap: d.market_cap || 0,
          deals: d.deals || 0,
          timestamp: json.timestamp,
          source: json.source || 'ngnmarket.com',
        });
        setError(null);
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        console.error('[MarketSnapshot] Fetch failed:', err);
        setError(String(err));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSnapshot();
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, [fetchSnapshot]);

  return { data, loading, error, refresh: fetchSnapshot };
}

// ============================================
// BREADTH HOOK (Advancers, Decliners)
// ============================================

export function useMarketBreadth() {
  const [data, setData] = useState<MarketBreadth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBreadth = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/market/breadth`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const json = await response.json();
      
      if (json.success && json.data) {
        const d = json.data;
        setData({
          advancing: d.advancing || 0,
          declining: d.declining || 0,
          unchanged: d.unchanged || 0,
          total: d.total || 0,
          ratio: d.ratio || 0,
          sentiment: d.sentiment || 'neutral',
          is_estimated: json.is_estimated !== false,
        });
        setError(null);
      }
    } catch (err) {
      console.error('[MarketBreadth] Fetch failed:', err);
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBreadth();
  }, [fetchBreadth]);

  return { data, loading, error, refresh: fetchBreadth };
}

// ============================================
// REGIME HOOK (Classification ONLY)
// ============================================

export function useMarketRegime() {
  const [data, setData] = useState<MarketRegime | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRegime = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/market/regime`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const json = await response.json();
      
      if (json.success) {
        setData({
          regime: json.regime || 'range_bound',
          confidence: json.confidence || 0,
          trend_direction: json.trend_direction || 'neutral',
          reasoning: json.reasoning || '',
          warnings: json.warnings || [],
        });
        setError(null);
      }
    } catch (err) {
      console.error('[MarketRegime] Fetch failed:', err);
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRegime();
  }, [fetchRegime]);

  return { data, loading, error, refresh: fetchRegime };
}

// ============================================
// COMBINED HOOK with PROPER LOADING ORDER
// ============================================

/**
 * Combined market data hook with progressive loading.
 * 
 * Loading order:
 * 1. Snapshot (blocking - required for first paint)
 * 2. Breadth + Regime (parallel, after snapshot)
 */
export function useMarketDataProgressive() {
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null);
  const [breadth, setBreadth] = useState<MarketBreadth | null>(null);
  const [regime, setRegime] = useState<MarketRegime | null>(null);
  
  const [snapshotLoading, setSnapshotLoading] = useState(true);
  const [secondaryLoading, setSecondaryLoading] = useState(true);
  
  const [error, setError] = useState<string | null>(null);

  // Phase 1: Fetch snapshot FIRST (blocking for first paint)
  useEffect(() => {
    const fetchSnapshot = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/market/snapshot`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const json = await response.json();
        if (json.success && json.data) {
          const d = json.data;
          
          if (d.asi < 100000) {
            console.warn('[MarketData] ASI value suspiciously low:', d.asi);
          }
          
          setSnapshot({
            asi: {
              value: d.asi || 0,
              change: d.asi_change || 0,
              change_percent: d.asi_change_percent || 0,
            },
            volume: {
              total_volume: d.volume || 0,
              total_value: d.value || 0,
            },
            market_cap: d.market_cap || 0,
            deals: d.deals || 0,
            timestamp: json.timestamp,
            source: json.source || 'ngnmarket.com',
          });
        }
      } catch (err) {
        console.error('[MarketData] Snapshot fetch failed:', err);
        setError(String(err));
      } finally {
        setSnapshotLoading(false);
      }
    };

    fetchSnapshot();
  }, []);

  // Phase 2: Fetch breadth + regime AFTER snapshot (non-blocking)
  useEffect(() => {
    if (snapshotLoading) return; // Wait for snapshot

    const fetchSecondary = async () => {
      try {
        // Use requestIdleCallback for non-critical data
        const fetchData = async () => {
          const [breadthRes, regimeRes] = await Promise.allSettled([
            fetch(`${API_BASE_URL}/api/v1/market/breadth`),
            fetch(`${API_BASE_URL}/api/v1/market/regime`),
          ]);

          // Process breadth
          if (breadthRes.status === 'fulfilled' && breadthRes.value.ok) {
            const json = await breadthRes.value.json();
            if (json.success && json.data) {
              const d = json.data;
              setBreadth({
                advancing: d.advancing || 0,
                declining: d.declining || 0,
                unchanged: d.unchanged || 0,
                total: d.total || 0,
                ratio: d.ratio || 0,
                sentiment: d.sentiment || 'neutral',
                is_estimated: json.is_estimated !== false,
              });
            }
          }

          // Process regime
          if (regimeRes.status === 'fulfilled' && regimeRes.value.ok) {
            const json = await regimeRes.value.json();
            if (json.success) {
              setRegime({
                regime: json.regime || 'range_bound',
                confidence: json.confidence || 0,
                trend_direction: json.trend_direction || 'neutral',
                reasoning: json.reasoning || '',
                warnings: json.warnings || [],
              });
            }
          }

          setSecondaryLoading(false);
        };

        // Use idle callback if available
        if ('requestIdleCallback' in window) {
          (window as Window).requestIdleCallback(() => fetchData());
        } else {
          setTimeout(fetchData, 50);
        }
      } catch (err) {
        console.error('[MarketData] Secondary fetch failed:', err);
        setSecondaryLoading(false);
      }
    };

    fetchSecondary();
  }, [snapshotLoading]);

  return {
    snapshot,
    breadth,
    regime,
    snapshotLoading,
    secondaryLoading,
    error,
    // First paint ready when snapshot is loaded
    readyForPaint: !snapshotLoading,
    // Fully loaded when all data is available
    fullyLoaded: !snapshotLoading && !secondaryLoading,
  };
}
