/**
 * StockCard - Compact stock display for lists
 * 
 * Shows essential info at a glance without overwhelming.
 * Designed for scanning, not reading.
 */

import React from 'react';
import type { Stock } from '../../core';

interface StockCardProps {
  stock: Stock;
  onClick?: () => void;
  showSector?: boolean;
  compact?: boolean;
}

const StockCard: React.FC<StockCardProps> = ({
  stock,
  onClick,
  showSector = false,
  compact = false,
}) => {
  const isPositive = (stock.change_percent || 0) > 0;
  const isNegative = (stock.change_percent || 0) < 0;

  const formatVolume = (vol: number) => {
    if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(1)}M`;
    if (vol >= 1_000) return `${(vol / 1_000).toFixed(0)}K`;
    return vol.toString();
  };

  if (compact) {
    return (
      <button
        onClick={onClick}
        className="flex items-center justify-between p-2 rounded-lg hover:bg-[var(--color-bg-hover)] transition-colors w-full text-left"
      >
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm text-[var(--color-text-primary)]">
            {stock.symbol}
          </span>
          <span className="text-xs text-[var(--color-text-tertiary)]">
            {stock.name?.slice(0, 15)}{stock.name?.length > 15 ? '...' : ''}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm text-[var(--color-text-primary)]">
            ₦{stock.price?.toFixed(2)}
          </span>
          <span className={`font-mono text-xs ${
            isPositive ? 'text-emerald-400' : isNegative ? 'text-red-400' : 'text-[var(--color-text-tertiary)]'
          }`}>
            {isPositive ? '+' : ''}{stock.change_percent?.toFixed(2)}%
          </span>
        </div>
      </button>
    );
  }

  return (
    <button
      onClick={onClick}
      className="card p-4 hover:border-[var(--color-border-default)] transition-colors w-full text-left group"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <h4 className="font-semibold text-[var(--color-text-primary)] group-hover:text-[var(--color-accent-primary)] transition-colors">
            {stock.symbol}
          </h4>
          <p className="text-xs text-[var(--color-text-tertiary)] truncate max-w-[150px]">
            {stock.name}
          </p>
        </div>
        
        {/* Change Badge */}
        <div className={`px-2 py-1 rounded-md text-xs font-mono font-medium ${
          isPositive 
            ? 'bg-emerald-500/15 text-emerald-400' 
            : isNegative 
              ? 'bg-red-500/15 text-red-400' 
              : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-tertiary)]'
        }`}>
          {isPositive ? '+' : ''}{stock.change_percent?.toFixed(2)}%
        </div>
      </div>

      {/* Price */}
      <div className="mb-3">
        <p className="text-2xl font-mono font-semibold text-[var(--color-text-primary)]">
          ₦{stock.price?.toFixed(2)}
        </p>
        <p className={`text-xs font-mono ${
          isPositive ? 'text-emerald-400' : isNegative ? 'text-red-400' : 'text-[var(--color-text-tertiary)]'
        }`}>
          {isPositive ? '+' : ''}₦{stock.change?.toFixed(2)}
        </p>
      </div>

      {/* Footer Stats */}
      <div className="flex items-center justify-between text-xs text-[var(--color-text-tertiary)]">
        <div className="flex items-center gap-1">
          <svg width="16" height="16" className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <span>{formatVolume(stock.volume || 0)}</span>
        </div>
        
        {showSector && stock.sector && (
          <span className="truncate max-w-[80px]">{stock.sector}</span>
        )}

        {stock.liquidity_tier && (
          <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase ${
            stock.liquidity_tier === 'high' 
              ? 'bg-emerald-500/10 text-emerald-400'
              : stock.liquidity_tier === 'medium'
                ? 'bg-amber-500/10 text-amber-400'
                : 'bg-red-500/10 text-red-400'
          }`}>
            {stock.liquidity_tier}
          </span>
        )}
      </div>
    </button>
  );
};

export default StockCard;
