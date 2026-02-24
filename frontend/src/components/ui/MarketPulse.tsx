/**
 * Market Pulse Component (Layer 1)
 * 
 * Compact market direction and regime indicator.
 * Renders with pulse data for instant market state awareness.
 */

import React from 'react';
import type { PulseData } from '../../core/api/uiService';

interface MarketPulseProps {
  pulse: PulseData | null;
  loading?: boolean;
}

const MarketPulse: React.FC<MarketPulseProps> = ({ pulse, loading }) => {
  if (loading || !pulse) {
    return (
      <div className="market-pulse market-pulse--loading">
        <div className="market-pulse__skeleton" />
      </div>
    );
  }
  
  const { market } = pulse;
  
  const getDirectionIcon = () => {
    switch (market.direction) {
      case 'up':
        return (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="18 15 12 9 6 15" />
          </svg>
        );
      case 'down':
        return (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        );
      default:
        return (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        );
    }
  };
  
  const getDirectionClass = () => {
    switch (market.direction) {
      case 'up': return 'market-pulse--up';
      case 'down': return 'market-pulse--down';
      default: return 'market-pulse--neutral';
    }
  };
  
  const getRegimeBadge = () => {
    const regime = market.regime.toLowerCase();
    
    const regimeLabels: Record<string, { label: string; class: string }> = {
      'bull': { label: 'Bull', class: 'badge--success' },
      'bear': { label: 'Bear', class: 'badge--danger' },
      'range': { label: 'Range', class: 'badge--neutral' },
      'high_volatility': { label: 'Volatile', class: 'badge--warning' },
      'accumulation': { label: 'Accumulating', class: 'badge--info' },
      'distribution': { label: 'Distributing', class: 'badge--warning' },
      'normal': { label: 'Normal', class: 'badge--neutral' },
      'unknown': { label: '—', class: 'badge--muted' },
    };
    
    const { label, class: badgeClass } = regimeLabels[regime] || regimeLabels['unknown'];
    
    return (
      <span className={`badge ${badgeClass}`}>
        {label}
      </span>
    );
  };
  
  return (
    <div className={`market-pulse ${getDirectionClass()}`}>
      <div className="market-pulse__direction">
        <span className="market-pulse__icon">
          {getDirectionIcon()}
        </span>
        <span className="market-pulse__change">
          {market.asi_change_pct >= 0 ? '+' : ''}{market.asi_change_pct.toFixed(2)}%
        </span>
      </div>
      
      <div className="market-pulse__regime">
        {getRegimeBadge()}
      </div>
    </div>
  );
};

export default MarketPulse;
