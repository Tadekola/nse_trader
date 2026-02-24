/**
 * Progressive Data Loading Hooks
 * 
 * React hooks for the 3-layer progressive rendering architecture:
 * 1. usePulse - Layer 1 data (instant)
 * 2. useSummary - Layer 2 data (fast)
 * 3. useStockDetail - Layer 3 data (lazy)
 * 4. useMarketStream - SSE real-time updates
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getPulse,
  getSummary,
  getStockDetail,
  getMarketStream,
  type PulseData,
  type SummaryData,
  type StockDetail,
} from '../api/uiService';

/**
 * Layer 1: Pulse data hook
 * 
 * Fetches minimal data for instant first paint.
 * Should complete in < 100ms.
 */
export function usePulse() {
  const [data, setData] = useState<PulseData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const fetchPulse = useCallback(async (forceRefresh = false) => {
    try {
      const pulseData = await getPulse(forceRefresh);
      setData(pulseData);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);
  
  // Initial fetch
  useEffect(() => {
    fetchPulse();
  }, [fetchPulse]);
  
  // SSE updates
  useEffect(() => {
    const stream = getMarketStream();
    
    const unsubscribe = stream.on('pulse', (pulseData) => {
      setData(pulseData as PulseData);
    });
    
    // Connect to stream
    stream.connect();
    
    return () => {
      unsubscribe();
    };
  }, []);
  
  return {
    data,
    loading,
    error,
    refresh: () => fetchPulse(true),
  };
}

/**
 * Layer 2: Summary data hook
 * 
 * Fetches movers and breadth data after pulse.
 * Should complete in < 500ms.
 */
export function useSummary(enabled = true) {
  const [data, setData] = useState<SummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const fetchSummary = useCallback(async (forceRefresh = false) => {
    if (!enabled) return;
    
    try {
      setLoading(true);
      const summaryData = await getSummary(5, forceRefresh);
      setData(summaryData);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [enabled]);
  
  // Fetch after a small delay to prioritize pulse
  useEffect(() => {
    if (!enabled) return;
    
    const timer = setTimeout(() => {
      fetchSummary();
    }, 50); // 50ms delay to let pulse render first
    
    return () => clearTimeout(timer);
  }, [fetchSummary, enabled]);
  
  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (!enabled) return;
    
    const interval = setInterval(() => {
      fetchSummary();
    }, 30000);
    
    return () => clearInterval(interval);
  }, [fetchSummary, enabled]);
  
  return {
    data,
    loading,
    error,
    refresh: () => fetchSummary(true),
  };
}

/**
 * Layer 3: Stock detail hook (lazy)
 * 
 * Fetches full stock data on demand.
 * Only called when user clicks a stock.
 */
export function useStockDetail(symbol: string | null) {
  const [data, setData] = useState<StockDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const fetchDetail = useCallback(async () => {
    if (!symbol) {
      setData(null);
      return;
    }
    
    try {
      setLoading(true);
      setError(null);
      const detail = await getStockDetail(symbol);
      setData(detail);
    } catch (err) {
      setError(String(err));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [symbol]);
  
  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);
  
  return {
    data,
    loading,
    error,
    refresh: fetchDetail,
  };
}

/**
 * SSE Stream hook
 * 
 * Manages SSE connection and provides event callbacks.
 */
export function useMarketStream() {
  const [connected, setConnected] = useState(false);
  const [lastHeartbeat, setLastHeartbeat] = useState<Date | null>(null);
  const streamRef = useRef(getMarketStream());
  
  useEffect(() => {
    const stream = streamRef.current;
    
    const unsubConnected = stream.on('connected', () => {
      setConnected(true);
    });
    
    const unsubHeartbeat = stream.on('heartbeat', () => {
      setLastHeartbeat(new Date());
    });
    
    const unsubError = stream.on('error', () => {
      setConnected(false);
    });
    
    const unsubDisconnected = stream.on('disconnected', () => {
      setConnected(false);
    });
    
    stream.connect();
    
    return () => {
      unsubConnected();
      unsubHeartbeat();
      unsubError();
      unsubDisconnected();
    };
  }, []);
  
  return {
    connected,
    lastHeartbeat,
    stream: streamRef.current,
  };
}

/**
 * Combined progressive data hook
 * 
 * Orchestrates the 3-layer loading pattern:
 * 1. Pulse loads immediately
 * 2. Summary loads after pulse
 * 3. Detail loads on demand
 */
export function useProgressiveData() {
  const pulse = usePulse();
  const summary = useSummary(!pulse.loading);
  const stream = useMarketStream();
  
  // Calculate overall loading state
  const initialLoadComplete = !pulse.loading;
  const fullyLoaded = !pulse.loading && !summary.loading;
  
  return {
    pulse,
    summary,
    stream,
    initialLoadComplete,
    fullyLoaded,
  };
}
