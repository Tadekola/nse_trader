/**
 * SignalCard - Trading signal with confidence and reasoning
 * 
 * Shows actionable signals with full transparency on methodology.
 * Critical for institutional credibility.
 */

import React from 'react';
import type { Recommendation } from '../../core';

interface SignalCardProps {
  recommendation: Recommendation;
  onStockClick?: (symbol: string) => void;
  expanded?: boolean;
}

const SignalCard: React.FC<SignalCardProps> = ({
  recommendation,
  onStockClick,
  expanded = false,
}) => {
  const [isExpanded, setIsExpanded] = React.useState(expanded);

  const actionConfig: Record<string, {
    label: string;
    color: string;
    bgColor: string;
    borderColor: string;
  }> = {
    STRONG_BUY: { 
      label: 'Strong Buy', 
      color: 'text-emerald-400', 
      bgColor: 'bg-emerald-500/15',
      borderColor: 'border-emerald-500/30'
    },
    BUY: { 
      label: 'Buy', 
      color: 'text-emerald-300', 
      bgColor: 'bg-emerald-500/10',
      borderColor: 'border-emerald-500/20'
    },
    HOLD: { 
      label: 'Hold', 
      color: 'text-amber-400', 
      bgColor: 'bg-amber-500/10',
      borderColor: 'border-amber-500/20'
    },
    SELL: { 
      label: 'Sell', 
      color: 'text-red-300', 
      bgColor: 'bg-red-500/10',
      borderColor: 'border-red-500/20'
    },
    STRONG_SELL: { 
      label: 'Strong Sell', 
      color: 'text-red-400', 
      bgColor: 'bg-red-500/15',
      borderColor: 'border-red-500/30'
    },
    AVOID: { 
      label: 'Avoid', 
      color: 'text-gray-400', 
      bgColor: 'bg-gray-500/10',
      borderColor: 'border-gray-500/20'
    },
  };

  const config = actionConfig[recommendation.action] || actionConfig.HOLD;

  const confidenceColor = recommendation.confidence >= 70 
    ? 'text-emerald-400' 
    : recommendation.confidence >= 50 
      ? 'text-amber-400' 
      : 'text-red-400';

  const riskConfig: Record<string, { label: string; color: string }> = {
    low: { label: 'Low Risk', color: 'text-emerald-400' },
    moderate: { label: 'Moderate Risk', color: 'text-amber-400' },
    high: { label: 'High Risk', color: 'text-orange-400' },
    very_high: { label: 'Very High Risk', color: 'text-red-400' },
  };

  const risk = riskConfig[recommendation.risk_level] || riskConfig.moderate;

  return (
    <div className={`card border ${config.borderColor} overflow-hidden`}>
      {/* Header */}
      <div 
        className={`p-4 ${config.bgColor} cursor-pointer`}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            {/* Action Badge */}
            <span className={`px-3 py-1.5 rounded-lg text-sm font-semibold ${config.bgColor} ${config.color} border ${config.borderColor}`}>
              {config.label}
            </span>
            
            {/* Symbol & Name */}
            <div>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  onStockClick?.(recommendation.symbol);
                }}
                className="font-semibold text-[var(--color-text-primary)] hover:text-[var(--color-accent-primary)] transition-colors"
              >
                {recommendation.symbol}
              </button>
              <p className="text-xs text-[var(--color-text-tertiary)]">
                {recommendation.name}
              </p>
            </div>
          </div>

          {/* Confidence */}
          <div className="text-right">
            <div className="flex items-center gap-1">
              <span className={`text-lg font-mono font-bold ${confidenceColor}`}>
                {recommendation.confidence}%
              </span>
              <span className="text-xs text-[var(--color-text-tertiary)]">confidence</span>
            </div>
            <div className="w-20 h-1.5 bg-[var(--color-bg-tertiary)] rounded-full mt-1 overflow-hidden">
              <div 
                className={`h-full rounded-full transition-all ${
                  recommendation.confidence >= 70 ? 'bg-emerald-400' :
                  recommendation.confidence >= 50 ? 'bg-amber-400' : 'bg-red-400'
                }`}
                style={{ width: `${recommendation.confidence}%` }}
              />
            </div>
          </div>
        </div>

        {/* Quick Stats Row */}
        <div className="flex items-center gap-4 mt-3 text-xs">
          <span className="text-[var(--color-text-secondary)]">
            ₦{recommendation.current_price?.toFixed(2)}
          </span>
          <span className={risk.color}>{risk.label}</span>
          {recommendation.entry_exit && (
            <span className="text-[var(--color-text-tertiary)]">
              R:R {recommendation.entry_exit.risk_reward?.toFixed(1)}
            </span>
          )}
          <span className="text-[var(--color-text-tertiary)] ml-auto">
            {recommendation.horizon === 'short_term' ? 'Day Trade' :
             recommendation.horizon === 'swing' ? 'Swing' : 'Position'}
          </span>
        </div>
      </div>

      {/* Primary Reason */}
      <div className="px-4 py-3 border-t border-[var(--color-border-subtle)]">
        <p className="text-sm text-[var(--color-text-secondary)]">
          {recommendation.primary_reason}
        </p>
      </div>

      {/* Expanded Details */}
      {isExpanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-[var(--color-border-subtle)]">
          {/* Entry/Exit Points */}
          {recommendation.entry_exit && (
            <div className="pt-4">
              <h4 className="text-xs font-semibold text-[var(--color-text-tertiary)] uppercase tracking-wide mb-2">
                Entry & Exit
              </h4>
              <div className="grid grid-cols-4 gap-3">
                <div>
                  <p className="text-xs text-[var(--color-text-tertiary)]">Entry</p>
                  <p className="font-mono text-sm text-[var(--color-text-primary)]">
                    ₦{recommendation.entry_exit.entry_price?.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-[var(--color-text-tertiary)]">Stop Loss</p>
                  <p className="font-mono text-sm text-red-400">
                    ₦{recommendation.entry_exit.stop_loss?.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-[var(--color-text-tertiary)]">Target 1</p>
                  <p className="font-mono text-sm text-emerald-400">
                    ₦{recommendation.entry_exit.target_1?.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-[var(--color-text-tertiary)]">Risk/Reward</p>
                  <p className="font-mono text-sm text-[var(--color-text-primary)]">
                    {recommendation.entry_exit.risk_reward?.toFixed(2)}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Supporting Reasons */}
          {recommendation.supporting_reasons?.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-[var(--color-text-tertiary)] uppercase tracking-wide mb-2">
                Supporting Factors
              </h4>
              <ul className="space-y-1">
                {recommendation.supporting_reasons.map((reason, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-[var(--color-text-secondary)]">
                    <span className="text-emerald-400 mt-0.5">+</span>
                    {reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Risk Warnings */}
          {recommendation.risk_warnings?.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-[var(--color-text-tertiary)] uppercase tracking-wide mb-2">
                Risk Factors
              </h4>
              <ul className="space-y-1">
                {recommendation.risk_warnings.map((warning, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-amber-400">
                    <span className="mt-0.5">⚠</span>
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Signals Breakdown */}
          {recommendation.signals?.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-[var(--color-text-tertiary)] uppercase tracking-wide mb-2">
                Technical Signals
              </h4>
              <div className="flex flex-wrap gap-2">
                {recommendation.signals.map((signal, i) => (
                  <span 
                    key={i}
                    className={`px-2 py-1 rounded text-xs ${
                      signal.direction === 'bullish' 
                        ? 'bg-emerald-500/10 text-emerald-400' 
                        : signal.direction === 'bearish'
                          ? 'bg-red-500/10 text-red-400'
                          : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]'
                    }`}
                  >
                    {signal.name}: {signal.direction}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* User Explanation */}
          {recommendation.user_explanation && (
            <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
              <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                {recommendation.user_explanation}
              </p>
            </div>
          )}

          {/* Validity */}
          <div className="flex items-center justify-between text-xs text-[var(--color-text-tertiary)]">
            <span>Generated: {new Date(recommendation.timestamp).toLocaleString()}</span>
            {recommendation.valid_until && (
              <span>Valid until: {new Date(recommendation.valid_until).toLocaleString()}</span>
            )}
          </div>
        </div>
      )}

      {/* Expand Toggle */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full py-2 text-xs text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] border-t border-[var(--color-border-subtle)]"
      >
        {isExpanded ? 'Show less' : 'Show more details'}
      </button>
    </div>
  );
};

export default SignalCard;
