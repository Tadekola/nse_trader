/**
 * Trust Banner Component (Layer 1)
 * 
 * Displays system trust status at the top of every page.
 * Renders FIRST with pulse data for instant feedback.
 * 
 * Design principles:
 * - Minimal, non-intrusive
 * - Color-coded for instant recognition
 * - Expandable for details
 */

import React, { useState } from 'react';
import type { PulseData } from '../../core/api/uiService';

interface TrustBannerProps {
  pulse: PulseData | null;
  loading?: boolean;
}

const TrustBanner: React.FC<TrustBannerProps> = ({ pulse, loading }) => {
  const [expanded, setExpanded] = useState(false);
  
  if (loading || !pulse) {
    return (
      <div className="trust-banner trust-banner--loading">
        <div className="trust-banner__content">
          <span className="trust-banner__indicator trust-banner__indicator--loading" />
          <span className="trust-banner__text">Connecting...</span>
        </div>
      </div>
    );
  }
  
  const { trust, counts } = pulse;
  
  // Determine banner style based on integrity
  const getIntegrityClass = () => {
    switch (trust.integrity) {
      case 'HIGH': return 'trust-banner--high';
      case 'MEDIUM': return 'trust-banner--medium';
      case 'DEGRADED': return 'trust-banner--degraded';
      default: return 'trust-banner--medium';
    }
  };
  
  // Get indicator icon
  const getIndicatorIcon = () => {
    switch (trust.integrity) {
      case 'HIGH':
        return (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 12l2 2 4-4" />
            <circle cx="12" cy="12" r="10" />
          </svg>
        );
      case 'MEDIUM':
        return (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
        );
      case 'DEGRADED':
        return (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
            <path d="M12 9v4M12 17h.01" />
          </svg>
        );
      default:
        return null;
    }
  };
  
  return (
    <div className={`trust-banner ${getIntegrityClass()}`}>
      <div className="trust-banner__content">
        <button 
          className="trust-banner__main"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
        >
          <span className="trust-banner__indicator">
            {getIndicatorIcon()}
          </span>
          <span className="trust-banner__text">{trust.banner}</span>
          <span className="trust-banner__readiness">
            {trust.readiness === 'READY' && '● Ready'}
            {trust.readiness === 'PARTIALLY_READY' && '◐ Partial'}
            {trust.readiness === 'NOT_READY' && '○ Setup Required'}
          </span>
          <svg 
            className={`trust-banner__chevron ${expanded ? 'trust-banner__chevron--expanded' : ''}`}
            width="16" 
            height="16" 
            viewBox="0 0 24 24" 
            fill="none" 
            stroke="currentColor" 
            strokeWidth="2"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
        
        {/* Quick stats - always visible */}
        <div className="trust-banner__stats">
          <span className="trust-banner__stat">
            <strong>{counts.symbols_ready}</strong> ready
          </span>
          <span className="trust-banner__divider">|</span>
          <span className="trust-banner__stat">
            <strong>{counts.symbols_total}</strong> total
          </span>
        </div>
      </div>
      
      {/* Expanded details */}
      {expanded && (
        <div className="trust-banner__details">
          <div className="trust-banner__detail-grid">
            <div className="trust-banner__detail-item">
              <span className="trust-banner__detail-label">Data Integrity</span>
              <span className={`trust-banner__detail-value trust-banner__detail-value--${trust.integrity.toLowerCase()}`}>
                {trust.integrity}
              </span>
            </div>
            <div className="trust-banner__detail-item">
              <span className="trust-banner__detail-label">Performance Tracking</span>
              <span className="trust-banner__detail-value">
                {trust.readiness.replace('_', ' ')}
              </span>
            </div>
            <div className="trust-banner__detail-item">
              <span className="trust-banner__detail-label">Symbols Ready</span>
              <span className="trust-banner__detail-value">
                {counts.symbols_ready} / {counts.symbols_total}
              </span>
            </div>
            {trust.active_sources && trust.active_sources.length > 0 && (
              <div className="trust-banner__detail-item">
                <span className="trust-banner__detail-label">Active Sources</span>
                <span className="trust-banner__detail-value text-xs">
                  {trust.active_sources.join(', ')}
                </span>
              </div>
            )}
          </div>
          
          {trust.has_issues && (
            <div className="trust-banner__warning">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8v4M12 16h.01" />
              </svg>
              <span>Some limitations apply. Check individual stock pages for details.</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default TrustBanner;
