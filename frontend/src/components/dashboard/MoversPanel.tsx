/**
 * MoversPanel - Top Gainers and Losers
 * 
 * Quick view of market movement extremes.
 * Helps identify momentum and potential opportunities/warnings.
 */

import React from 'react';
import type { Stock } from '../../core';

interface MoversPanelProps {
  stocks: Stock[];
  loading?: boolean;
  onStockClick?: (symbol: string) => void;
}

const MoversPanel: React.FC<MoversPanelProps> = ({
  stocks,
  loading = false,
  onStockClick,
}) => {
  // Sort and get top gainers and losers
  const sortedByChange = [...stocks].sort(
    (a, b) => (b.change_percent || 0) - (a.change_percent || 0)
  );
  
  const gainers = sortedByChange.filter(s => (s.change_percent || 0) > 0).slice(0, 5);
  const losers = sortedByChange.filter(s => (s.change_percent || 0) < 0).reverse().slice(0, 5);

  const MoverItem = ({ stock, isGainer }: { stock: Stock; isGainer: boolean }) => (
    <button
      onClick={() => onStockClick?.(stock.symbol)}
      className="flex items-center justify-between py-2 px-1 hover:bg-[var(--color-bg-hover)] rounded transition-colors w-full text-left"
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className="font-medium text-sm text-[var(--color-text-primary)]">
          {stock.symbol}
        </span>
        <span className="text-xs text-[var(--color-text-tertiary)] truncate">
          ₦{stock.price?.toFixed(2)}
        </span>
      </div>
      <span className={`font-mono text-sm font-medium ${
        isGainer ? 'text-emerald-400' : 'text-red-400'
      }`}>
        {isGainer ? '+' : ''}{stock.change_percent?.toFixed(2)}%
      </span>
    </button>
  );

  const LoadingState = () => (
    <div className="space-y-2">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="flex items-center justify-between py-2 animate-pulse">
          <div className="flex items-center gap-2">
            <div className="h-4 w-12 bg-[var(--color-bg-tertiary)] rounded"></div>
            <div className="h-3 w-16 bg-[var(--color-bg-tertiary)] rounded"></div>
          </div>
          <div className="h-4 w-14 bg-[var(--color-bg-tertiary)] rounded"></div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Gainers */}
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-2 h-2 rounded-full bg-emerald-400"></div>
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wide">
            Top Gainers
          </h3>
        </div>
        
        {loading ? (
          <LoadingState />
        ) : gainers.length > 0 ? (
          <div className="space-y-1">
            {gainers.map((stock) => (
              <MoverItem key={stock.symbol} stock={stock} isGainer={true} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-tertiary)] py-4 text-center">
            No gainers today
          </p>
        )}
      </div>

      {/* Losers */}
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-2 h-2 rounded-full bg-red-400"></div>
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wide">
            Top Losers
          </h3>
        </div>
        
        {loading ? (
          <LoadingState />
        ) : losers.length > 0 ? (
          <div className="space-y-1">
            {losers.map((stock) => (
              <MoverItem key={stock.symbol} stock={stock} isGainer={false} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-tertiary)] py-4 text-center">
            No losers today
          </p>
        )}
      </div>
    </div>
  );
};

export default MoversPanel;
