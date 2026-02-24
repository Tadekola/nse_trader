/**
 * Progressive Dashboard (Phase UI-3)
 * 
 * 3-Layer Progressive Rendering Architecture:
 * 
 * Layer 1 - MARKET PULSE (Instant)
 *   - Trust banner
 *   - Market direction
 *   - Regime badge
 *   
 * Layer 2 - ACTIONABLE SUMMARY (Fast)
 *   - Top gainers/losers
 *   - Market breadth
 *   - Readiness counts
 *   
 * Layer 3 - DEEP DETAIL (Lazy)
 *   - Full stock list
 *   - Indicators
 *   - Historical coverage
 * 
 * Design: Institutional, calm, non-hype
 */

import React, { useState, useCallback } from 'react';
import { useProgressiveData } from '../core';
import TrustBanner from '../components/ui/TrustBanner';
import MarketPulse from '../components/ui/MarketPulse';
import StatusBadge from '../components/ui/StatusBadge';
import QuickMovers from '../components/dashboard/QuickMovers';
import BreadthBar from '../components/dashboard/BreadthBar';

// Import progressive styles
import '../styles/trust-banner.css';
import '../styles/progressive-ui.css';

const ProgressiveDashboard: React.FC = () => {
  const { pulse, summary, stream, initialLoadComplete } = useProgressiveData();
  const [, setSelectedStock] = useState<string | null>(null);

  const handleStockClick = useCallback((symbol: string) => {
    setSelectedStock(symbol);
    // Future: Open detail panel or navigate to stock page
  }, []);

  return (
    <div className="progressive-dashboard">
      {/* ========================================
          LAYER 1: MARKET PULSE (Renders FIRST)
          ======================================== */}
      <section className="layer layer--pulse">
        <TrustBanner pulse={pulse.data} loading={pulse.loading} />
        
        <div className="pulse-row">
          <MarketPulse pulse={pulse.data} loading={pulse.loading} />
          
          {/* Connection indicator */}
          <div className="connection-status">
            <span className={`connection-status__dot connection-status__dot--${stream.connected ? 'connected' : 'disconnected'}`} />
            <span>{stream.connected ? 'Live' : 'Connecting...'}</span>
          </div>
        </div>
      </section>

      {/* ========================================
          LAYER 2: ACTIONABLE SUMMARY (Loads after pulse)
          ======================================== */}
      {initialLoadComplete && (
        <section className="layer layer--summary fade-in">
          {/* Readiness Summary */}
          <div className="readiness-summary">
            <div className="readiness-summary__item">
              <span className="readiness-summary__value">
                {summary.data?.readiness.symbols_ready ?? '—'}
              </span>
              <span className="readiness-summary__label">Ready</span>
            </div>
            <div className="readiness-summary__divider" />
            <div className="readiness-summary__item">
              <span className="readiness-summary__value">
                {summary.data?.readiness.no_trade_count ?? '—'}
              </span>
              <span className="readiness-summary__label">
                <StatusBadge status="NO_TRADE" size="sm" showTooltip={true} customLabel="No Trade" />
              </span>
            </div>
            <div className="readiness-summary__divider" />
            <div className="readiness-summary__item">
              <span className="readiness-summary__value">
                {summary.data?.breadth.total ?? '—'}
              </span>
              <span className="readiness-summary__label">Total</span>
            </div>
          </div>

          {/* Market Breadth */}
          <div style={{ marginTop: '16px' }}>
            <BreadthBar
              advancing={summary.data?.breadth.advancing ?? 0}
              declining={summary.data?.breadth.declining ?? 0}
              unchanged={summary.data?.breadth.unchanged ?? 0}
              loading={summary.loading}
            />
          </div>

          {/* Quick Movers */}
          <div style={{ marginTop: '16px' }}>
            <QuickMovers
              gainers={summary.data?.movers.gainers ?? []}
              losers={summary.data?.movers.losers ?? []}
              loading={summary.loading}
              onStockClick={handleStockClick}
            />
          </div>
        </section>
      )}

      {/* ========================================
          LAYER 3: DEEP DETAIL (Lazy loaded)
          ======================================== */}
      {initialLoadComplete && (
        <section className="layer layer--detail fade-in">
          {/* Information Card */}
          <div className="info-card">
            <div className="info-card__icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 16v-4M12 8h.01" />
              </svg>
            </div>
            <div className="info-card__content">
              <h4 className="info-card__title">Understanding This Dashboard</h4>
              <p className="info-card__text">
                This dashboard shows real-time Nigerian Stock Exchange data. 
                Stocks marked as "No Trade" have insufficient historical data for reliable analysis—this 
                is a <strong>protective feature</strong>, not an error.
              </p>
            </div>
          </div>

          {/* Placeholder for full stock list - would lazy load on scroll */}
          <div className="stock-list-placeholder">
            <h3 className="section-title">All Stocks</h3>
            <p className="section-subtitle">
              Click on any stock above to see detailed analysis, or scroll down to browse all available stocks.
            </p>
            
            {/* This would be the existing StockScreener component, lazy loaded */}
            <div className="lazy-load-hint">
              <span>Scroll to load full stock list...</span>
            </div>
          </div>
        </section>
      )}

      {/* Loading state for initial load */}
      {!initialLoadComplete && (
        <div className="initial-loading">
          <div className="initial-loading__spinner" />
          <span className="initial-loading__text">Loading market data...</span>
        </div>
      )}
    </div>
  );
};

export default ProgressiveDashboard;
