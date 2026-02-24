/**
 * Validation Badge Component
 * 
 * Shows multi-source validation status for price data.
 * Displays "Validated" badge when data is confirmed by multiple sources.
 * 
 * Design: Subtle, informational, non-intrusive
 */

import React, { useState } from 'react';

interface ValidationInfo {
  is_validated: boolean;
  confidence_level: 'HIGH' | 'MEDIUM' | 'LOW' | 'SUPPRESSED';
  confidence_score: number;
  sources_count: number;
  status?: string;
  divergence_pct?: number;
  primary_source?: string;
  secondary_source?: string;
}

interface ValidationBadgeProps {
  validation?: ValidationInfo;
  size?: 'sm' | 'md';
  showTooltip?: boolean;
}

const ValidationBadge: React.FC<ValidationBadgeProps> = ({
  validation,
  size = 'sm',
  showTooltip = true,
}) => {
  const [tooltipVisible, setTooltipVisible] = useState(false);

  if (!validation) {
    return null;
  }

  const { is_validated, confidence_level, sources_count, divergence_pct, primary_source, secondary_source } = validation;

  // Only show badge if validated or has multiple sources
  if (!is_validated && sources_count <= 1) {
    return null;
  }

  const getBadgeClass = () => {
    if (is_validated && confidence_level === 'HIGH') {
      return 'validation-badge--validated';
    }
    if (confidence_level === 'LOW' || confidence_level === 'SUPPRESSED') {
      return 'validation-badge--warning';
    }
    return 'validation-badge--partial';
  };

  const getIcon = () => {
    if (is_validated && confidence_level === 'HIGH') {
      return (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M9 12l2 2 4-4" />
          <circle cx="12" cy="12" r="10" />
        </svg>
      );
    }
    if (confidence_level === 'LOW' || confidence_level === 'SUPPRESSED') {
      return (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v4M12 16h.01" />
        </svg>
      );
    }
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 8v4" />
      </svg>
    );
  };

  const getTooltipContent = () => {
    const sources = [];
    if (primary_source) sources.push(primary_source);
    if (secondary_source) sources.push(secondary_source);
    const sourceText = sources.length > 0 ? sources.join(' + ') : `${sources_count} sources`;

    if (is_validated && confidence_level === 'HIGH') {
      return {
        title: 'Multi-Source Validated',
        description: `Price confirmed by ${sourceText} with high agreement.`,
        detail: divergence_pct !== undefined 
          ? `Divergence: ${divergence_pct.toFixed(2)}%` 
          : null,
      };
    }
    if (is_validated) {
      return {
        title: 'Validated',
        description: `Price checked against ${sourceText}.`,
        detail: divergence_pct !== undefined 
          ? `Minor divergence: ${divergence_pct.toFixed(2)}%` 
          : null,
      };
    }
    if (confidence_level === 'LOW') {
      return {
        title: 'Price Divergence Detected',
        description: `Sources (${sourceText}) show significant price differences. Use with caution.`,
        detail: divergence_pct !== undefined 
          ? `Divergence: ${divergence_pct.toFixed(2)}%` 
          : null,
      };
    }
    return {
      title: 'Single Source',
      description: `Price from ${primary_source || 'primary source'} only. Secondary validation unavailable.`,
      detail: null,
    };
  };

  const tooltip = getTooltipContent();

  return (
    <div 
      className="validation-badge-wrapper"
      onMouseEnter={() => setTooltipVisible(true)}
      onMouseLeave={() => setTooltipVisible(false)}
    >
      <span className={`validation-badge validation-badge--${size} ${getBadgeClass()}`}>
        {getIcon()}
        {is_validated && confidence_level === 'HIGH' && (
          <span className="validation-badge__label">Validated</span>
        )}
      </span>

      {/* Tooltip */}
      {showTooltip && tooltipVisible && (
        <div className="validation-tooltip">
          <div className="validation-tooltip__content">
            <strong className="validation-tooltip__title">{tooltip.title}</strong>
            <p className="validation-tooltip__text">{tooltip.description}</p>
            {tooltip.detail && (
              <span className="validation-tooltip__detail">{tooltip.detail}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ValidationBadge;
