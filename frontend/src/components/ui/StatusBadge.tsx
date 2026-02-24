/**
 * Status Badge Component
 * 
 * Compact, color-coded status indicators with tooltip support.
 * Used for NO_TRADE, READY, INSUFFICIENT_HISTORY, etc.
 * 
 * Design: Institutional, calm, non-hype
 */

import React, { useState } from 'react';
import { getStatusExplanation, type StatusExplanation } from '../../core/api/uiService';

type Severity = 'info' | 'success' | 'warning' | 'error' | 'muted';

interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md' | 'lg';
  showTooltip?: boolean;
  customLabel?: string;
}

// Static mappings for common statuses
const STATUS_CONFIG: Record<string, { label: string; severity: Severity }> = {
  'READY': { label: 'Ready', severity: 'success' },
  'PARTIALLY_READY': { label: 'Partial', severity: 'warning' },
  'NOT_READY': { label: 'Setup Required', severity: 'warning' },
  'NO_TRADE': { label: 'No Trade', severity: 'info' },
  'INSUFFICIENT_HISTORY': { label: 'Limited Data', severity: 'info' },
  'INSUFFICIENT_SAMPLE': { label: 'Building Stats', severity: 'info' },
  'STALE_DATA': { label: 'Stale', severity: 'warning' },
  'HIGH': { label: 'High', severity: 'success' },
  'MEDIUM': { label: 'Medium', severity: 'warning' },
  'DEGRADED': { label: 'Degraded', severity: 'error' },
  'ACTIVE': { label: 'Active', severity: 'success' },
  'SUPPRESSED': { label: 'Suppressed', severity: 'muted' },
  'INVALID': { label: 'Invalid', severity: 'error' },
};

const StatusBadge: React.FC<StatusBadgeProps> = ({ 
  status, 
  size = 'md', 
  showTooltip = true,
  customLabel 
}) => {
  const [tooltipVisible, setTooltipVisible] = useState(false);
  const [explanation, setExplanation] = useState<StatusExplanation | null>(null);
  const [loadingExplanation, setLoadingExplanation] = useState(false);
  
  const config = STATUS_CONFIG[status.toUpperCase()] || { 
    label: status, 
    severity: 'muted' as Severity 
  };
  
  const handleMouseEnter = async () => {
    if (!showTooltip) return;
    
    setTooltipVisible(true);
    
    if (!explanation && !loadingExplanation) {
      setLoadingExplanation(true);
      try {
        const exp = await getStatusExplanation(status);
        setExplanation(exp);
      } catch (err) {
        console.error('Failed to load explanation:', err);
      } finally {
        setLoadingExplanation(false);
      }
    }
  };
  
  const handleMouseLeave = () => {
    setTooltipVisible(false);
  };
  
  return (
    <div 
      className="status-badge-wrapper"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <span className={`badge badge--${config.severity} badge--${size}`}>
        {customLabel || config.label}
      </span>
      
      {/* Tooltip */}
      {showTooltip && tooltipVisible && (
        <div className="status-tooltip">
          <div className="status-tooltip__content">
            {loadingExplanation ? (
              <span className="status-tooltip__loading">Loading...</span>
            ) : explanation ? (
              <>
                <strong className="status-tooltip__title">{explanation.title}</strong>
                <p className="status-tooltip__text">{explanation.explanation}</p>
                {explanation.action && (
                  <p className="status-tooltip__action">
                    <em>{explanation.action}</em>
                  </p>
                )}
              </>
            ) : (
              <span>Status: {status}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default StatusBadge;
