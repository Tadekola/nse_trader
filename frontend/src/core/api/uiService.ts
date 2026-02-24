/**
 * UI-Optimized API Service
 * 
 * Provides fast, progressive data fetching for the frontend:
 * - /ui/pulse - First paint data (< 1KB)
 * - /ui/summary - Actionable layer data
 * - /ui/stream - SSE real-time updates
 * 
 * Design principles:
 * - Fetch pulse FIRST for instant banner
 * - Stream updates instead of polling
 * - Cache aggressively
 */

import { API_BASE_URL } from './client';

// Types for UI-optimized endpoints
export interface PulseData {
  timestamp: string;
  trust: {
    integrity: 'HIGH' | 'MEDIUM' | 'DEGRADED';
    readiness: 'READY' | 'PARTIALLY_READY' | 'NOT_READY';
    banner: string;
    active_sources?: string[];
    has_issues: boolean;
  };
  market: {
    direction: 'up' | 'down' | 'neutral';
    asi?: number;
    asi_change_pct: number;
    regime: string;
    regime_confidence: number;
  };
  counts: {
    symbols_ready: number;
    symbols_total: number;
  };
  _meta: {
    cache_seconds: number;
    endpoint: string;
    error?: string;
  };
}

export interface MoverStock {
  symbol: string;
  name: string;
  price: number;
  change_pct: number;
  volume: number;
}

export interface SummaryData {
  timestamp: string;
  movers: {
    gainers: MoverStock[];
    losers: MoverStock[];
  };
  breadth: {
    advancing: number;
    declining: number;
    unchanged: number;
    total: number;
    ratio: number;
  };
  readiness: {
    symbols_ready: number;
    symbols_with_data: number;
    no_trade_count: number;
  };
  _meta: {
    cache_seconds: number;
    endpoint: string;
    error?: string;
  };
}

export interface StockDetail {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  high: number;
  low: number;
  open: number;
  source?: string;
  coverage: {
    sessions_available: number;
    is_sufficient: boolean;
    is_stale: boolean;
    source: string;
  };
  indicators_available: boolean;
  explanation: {
    what_this_means: string;
  };
}

export interface StatusExplanation {
  status_code: string;
  title: string;
  explanation: string;
  action: string;
  severity: 'info' | 'warning' | 'success' | 'error';
}

// Cache for pulse data
let pulseCache: { data: PulseData | null; timestamp: number } = { data: null, timestamp: 0 };
const PULSE_CACHE_MS = 10000; // 10 seconds

// Cache for summary data
let summaryCache: { data: SummaryData | null; timestamp: number } = { data: null, timestamp: 0 };
const SUMMARY_CACHE_MS = 30000; // 30 seconds

/**
 * Get pulse data - FIRST call on page load
 * Returns cached data if fresh, otherwise fetches
 */
export async function getPulse(forceRefresh = false): Promise<PulseData> {
  const now = Date.now();
  
  // Return cached if fresh
  if (!forceRefresh && pulseCache.data && (now - pulseCache.timestamp) < PULSE_CACHE_MS) {
    return pulseCache.data;
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/ui/pulse`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });
    
    if (!response.ok) {
      throw new Error(`Pulse fetch failed: ${response.status}`);
    }
    
    const data: PulseData = await response.json();
    
    // Update cache
    pulseCache = { data, timestamp: now };
    
    return data;
  } catch (error) {
    console.error('Failed to fetch pulse:', error);
    
    // Return stale cache if available
    if (pulseCache.data) {
      return pulseCache.data;
    }
    
    // Return fallback
    return {
      timestamp: new Date().toISOString(),
      trust: {
        integrity: 'DEGRADED',
        readiness: 'NOT_READY',
        banner: 'Connecting to server...',
        has_issues: true,
      },
      market: {
        direction: 'neutral',
        asi_change_pct: 0,
        regime: 'unknown',
        regime_confidence: 0,
      },
      counts: {
        symbols_ready: 0,
        symbols_total: 0,
      },
      _meta: {
        cache_seconds: 5,
        endpoint: 'pulse',
        error: String(error),
      },
    };
  }
}

/**
 * Get summary data - SECOND call after pulse
 */
export async function getSummary(limit = 5, forceRefresh = false): Promise<SummaryData> {
  const now = Date.now();
  
  // Return cached if fresh
  if (!forceRefresh && summaryCache.data && (now - summaryCache.timestamp) < SUMMARY_CACHE_MS) {
    return summaryCache.data;
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/ui/summary?limit=${limit}`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });
    
    if (!response.ok) {
      throw new Error(`Summary fetch failed: ${response.status}`);
    }
    
    const data: SummaryData = await response.json();
    
    // Update cache
    summaryCache = { data, timestamp: now };
    
    return data;
  } catch (error) {
    console.error('Failed to fetch summary:', error);
    
    // Return stale cache if available
    if (summaryCache.data) {
      return summaryCache.data;
    }
    
    // Return fallback
    return {
      timestamp: new Date().toISOString(),
      movers: { gainers: [], losers: [] },
      breadth: { advancing: 0, declining: 0, unchanged: 0, total: 0, ratio: 0 },
      readiness: { symbols_ready: 0, symbols_with_data: 0, no_trade_count: 0 },
      _meta: { cache_seconds: 10, endpoint: 'summary', error: String(error) },
    };
  }
}

/**
 * Get stock detail - LAZY loaded on click
 */
export async function getStockDetail(symbol: string): Promise<StockDetail | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/ui/stock/${symbol}`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });
    
    if (!response.ok) {
      return null;
    }
    
    return await response.json();
  } catch (error) {
    console.error(`Failed to fetch stock ${symbol}:`, error);
    return null;
  }
}

/**
 * Get status explanation for tooltips
 */
export async function getStatusExplanation(statusCode: string): Promise<StatusExplanation> {
  try {
    const response = await fetch(`${API_BASE_URL}/ui/explain/${statusCode}`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });
    
    if (!response.ok) {
      throw new Error(`Explain fetch failed: ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error(`Failed to fetch explanation for ${statusCode}:`, error);
    return {
      status_code: statusCode,
      title: statusCode,
      explanation: 'Unable to load explanation',
      action: '',
      severity: 'info',
    };
  }
}

/**
 * SSE Stream connection manager
 */
export class MarketStream {
  private eventSource: EventSource | null = null;
  private listeners: Map<string, Set<(data: unknown) => void>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  
  connect(): void {
    if (this.eventSource) {
      return; // Already connected
    }
    
    try {
      this.eventSource = new EventSource(`${API_BASE_URL}/ui/stream`);
      
      this.eventSource.addEventListener('connected', (e) => {
        console.log('SSE connected:', e.data);
        this.reconnectAttempts = 0;
        this.emit('connected', JSON.parse(e.data));
      });
      
      this.eventSource.addEventListener('pulse', (e) => {
        const data = JSON.parse(e.data);
        // Update cache
        pulseCache = { data: data as PulseData, timestamp: Date.now() };
        this.emit('pulse', data);
      });
      
      this.eventSource.addEventListener('heartbeat', (e) => {
        this.emit('heartbeat', JSON.parse(e.data));
      });
      
      this.eventSource.addEventListener('error', (e) => {
        console.error('SSE error:', e);
        this.emit('error', { error: 'Connection error' });
        this.handleReconnect();
      });
      
      this.eventSource.onerror = () => {
        this.handleReconnect();
      };
    } catch (error) {
      console.error('Failed to connect SSE:', error);
      this.handleReconnect();
    }
  }
  
  private handleReconnect(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
      console.log(`SSE reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
      setTimeout(() => this.connect(), delay);
    } else {
      console.error('SSE max reconnect attempts reached');
      this.emit('disconnected', { reason: 'max_reconnects' });
    }
  }
  
  disconnect(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.listeners.clear();
  }
  
  on(event: string, callback: (data: unknown) => void): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
    
    // Return unsubscribe function
    return () => {
      this.listeners.get(event)?.delete(callback);
    };
  }
  
  private emit(event: string, data: unknown): void {
    this.listeners.get(event)?.forEach(callback => {
      try {
        callback(data);
      } catch (error) {
        console.error(`Error in SSE listener for ${event}:`, error);
      }
    });
  }
}

// Singleton stream instance
let streamInstance: MarketStream | null = null;

export function getMarketStream(): MarketStream {
  if (!streamInstance) {
    streamInstance = new MarketStream();
  }
  return streamInstance;
}
