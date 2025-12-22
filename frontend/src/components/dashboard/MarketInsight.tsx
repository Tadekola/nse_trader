/**
 * MarketInsight - Human-readable market commentary
 * 
 * Translates data into plain English insights.
 * Critical for beginners who don't understand raw numbers.
 */

import React from 'react';
import type { MarketRegime } from '../../core';

interface MarketInsightProps {
  regime: MarketRegime | null;
  advancers: number;
  decliners: number;
  totalStocks: number;
  loading?: boolean;
}

const MarketInsight: React.FC<MarketInsightProps> = ({
  regime,
  advancers,
  decliners,
  totalStocks,
  loading = false,
}) => {
  // Generate human-readable insight based on market data
  const generateInsight = (): { title: string; body: string; sentiment: 'positive' | 'negative' | 'neutral' } => {
    const breadthRatio = advancers / (advancers + decliners || 1);
    const regimeType = regime?.regime || 'range_bound';
    
    // Bull market with good breadth
    if (regimeType === 'bull' && breadthRatio > 0.6) {
      return {
        title: 'Favorable Conditions',
        body: `Most stocks are rising today (${advancers} of ${totalStocks}). The market is in an uptrend, which historically favors buying quality stocks on dips.`,
        sentiment: 'positive',
      };
    }
    
    // Bear market
    if (regimeType === 'bear') {
      return {
        title: 'Defensive Positioning Recommended',
        body: `The market is in a downtrend. Focus on capital preservation. Consider reducing exposure or moving to defensive sectors like consumer staples.`,
        sentiment: 'negative',
      };
    }
    
    // High volatility
    if (regimeType === 'high_volatility') {
      return {
        title: 'Elevated Volatility',
        body: `Market swings are larger than normal. If you're new to trading, consider waiting for calmer conditions. Experienced traders might find opportunities in the chaos.`,
        sentiment: 'neutral',
      };
    }
    
    // Low liquidity
    if (regimeType === 'low_liquidity') {
      return {
        title: 'Thin Trading Volume',
        body: `Trading activity is below average. This can lead to wider spreads and difficulty executing large orders. Stick to the most liquid stocks.`,
        sentiment: 'neutral',
      };
    }
    
    // Crisis
    if (regimeType === 'crisis') {
      return {
        title: 'Extreme Caution Advised',
        body: `Market conditions are severely stressed. Unless you have significant experience, consider staying on the sidelines until conditions normalize.`,
        sentiment: 'negative',
      };
    }
    
    // Weak breadth (more decliners)
    if (breadthRatio < 0.4) {
      return {
        title: 'Broad Weakness',
        body: `More stocks are falling than rising (${decliners} decliners vs ${advancers} advancers). This suggests underlying weakness even if the index looks stable.`,
        sentiment: 'negative',
      };
    }
    
    // Range-bound / neutral
    return {
      title: 'Mixed Signals',
      body: `The market is moving sideways without a clear direction. This is a time for patience. Wait for clearer signals before making significant moves.`,
      sentiment: 'neutral',
    };
  };

  if (loading) {
    return (
      <div className="card p-4 animate-pulse">
        <div className="h-4 w-40 bg-[var(--color-bg-tertiary)] rounded mb-3"></div>
        <div className="h-3 w-full bg-[var(--color-bg-tertiary)] rounded mb-2"></div>
        <div className="h-3 w-3/4 bg-[var(--color-bg-tertiary)] rounded"></div>
      </div>
    );
  }

  const insight = generateInsight();
  
  const sentimentConfig = {
    positive: {
      icon: (
        <svg width="16" height="16" className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      color: 'text-emerald-400',
      bgColor: 'bg-emerald-500/10',
    },
    negative: {
      icon: (
        <svg width="16" height="16" className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      ),
      color: 'text-amber-400',
      bgColor: 'bg-amber-500/10',
    },
    neutral: {
      icon: (
        <svg width="16" height="16" className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      color: 'text-[var(--color-text-secondary)]',
      bgColor: 'bg-[var(--color-bg-tertiary)]',
    },
  };

  const config = sentimentConfig[insight.sentiment];

  return (
    <div className={`card p-4 ${config.bgColor} border-l-4 ${
      insight.sentiment === 'positive' ? 'border-l-emerald-400' :
      insight.sentiment === 'negative' ? 'border-l-amber-400' :
      'border-l-[var(--color-border-default)]'
    }`}>
      <div className="flex items-start gap-3">
        <div className={`flex-shrink-0 mt-0.5 ${config.color}`}>
          {config.icon}
        </div>
        <div>
          <h4 className="text-sm font-semibold text-[var(--color-text-primary)] mb-1">
            {insight.title}
          </h4>
          <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
            {insight.body}
          </p>
        </div>
      </div>
    </div>
  );
};

export default MarketInsight;
