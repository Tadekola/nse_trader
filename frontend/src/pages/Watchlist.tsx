/**
 * Watchlist Page - Personal Stock Tracking
 * 
 * Allows users to track stocks of interest.
 * Persists to localStorage for now, backend persistence later.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { stocksService, EmptyState, type Stock } from '../core';

const WATCHLIST_KEY = 'nse_trader_watchlist';

const Watchlist: React.FC = () => {
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([]);
  const [watchlistStocks, setWatchlistStocks] = useState<Stock[]>([]);
  const [allStocks, setAllStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);

  // Load watchlist from localStorage
  useEffect(() => {
    const saved = localStorage.getItem(WATCHLIST_KEY);
    if (saved) {
      try {
        setWatchlistSymbols(JSON.parse(saved));
      } catch {
        console.error('Failed to parse watchlist from localStorage');
      }
    }
  }, []);

  // Save watchlist to localStorage
  useEffect(() => {
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify(watchlistSymbols));
  }, [watchlistSymbols]);

  // Fetch stock data
  const fetchStocks = useCallback(async () => {
    try {
      setLoading(true);
      const data = await stocksService.getAll();
      setAllStocks(data);
      
      // Filter to watchlist stocks
      const watched = data.filter(s => watchlistSymbols.includes(s.symbol));
      setWatchlistStocks(watched);
    } catch (err) {
      console.error('Failed to fetch stocks:', err);
    } finally {
      setLoading(false);
    }
  }, [watchlistSymbols]);

  useEffect(() => {
    fetchStocks();
  }, [fetchStocks]);

  const addToWatchlist = (symbol: string) => {
    if (!watchlistSymbols.includes(symbol)) {
      setWatchlistSymbols([...watchlistSymbols, symbol]);
    }
    setShowAddModal(false);
    setSearchQuery('');
  };

  const removeFromWatchlist = (symbol: string) => {
    setWatchlistSymbols(watchlistSymbols.filter(s => s !== symbol));
  };

  // Filter stocks for search
  const searchResults = searchQuery.length >= 1
    ? allStocks.filter(s => 
        !watchlistSymbols.includes(s.symbol) &&
        (s.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
         s.name.toLowerCase().includes(searchQuery.toLowerCase()))
      ).slice(0, 10)
    : [];

  return (
    <div className="space-y-6 pb-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">
            Watchlist
          </h1>
          <p className="text-sm text-[var(--color-text-tertiary)] mt-1">
            Track stocks you're interested in
          </p>
        </div>

        <button
          onClick={() => setShowAddModal(true)}
          className="px-4 py-2 bg-[var(--color-accent-primary)] text-white text-sm font-medium rounded-lg hover:bg-[var(--color-accent-primary)]/90 transition-colors"
        >
          + Add Stock
        </button>
      </div>

      {/* Add Stock Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="card p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
                Add to Watchlist
              </h2>
              <button
                onClick={() => {
                  setShowAddModal(false);
                  setSearchQuery('');
                }}
                className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]"
              >
                <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <input
              type="text"
              placeholder="Search stocks..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-4 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border-subtle)] rounded-lg text-sm text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)] focus:outline-none focus:border-[var(--color-accent-primary)]"
              autoFocus
            />

            {searchResults.length > 0 && (
              <div className="mt-3 max-h-64 overflow-y-auto space-y-1">
                {searchResults.map(stock => (
                  <button
                    key={stock.symbol}
                    onClick={() => addToWatchlist(stock.symbol)}
                    className="w-full flex items-center justify-between p-3 hover:bg-[var(--color-bg-hover)] rounded-lg transition-colors"
                  >
                    <div>
                      <span className="font-medium text-[var(--color-text-primary)]">{stock.symbol}</span>
                      <span className="text-sm text-[var(--color-text-tertiary)] ml-2">{stock.name}</span>
                    </div>
                    <span className="text-sm font-mono text-[var(--color-text-secondary)]">
                      ₦{stock.price?.toFixed(2)}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {searchQuery.length >= 1 && searchResults.length === 0 && (
              <p className="mt-3 text-sm text-[var(--color-text-tertiary)] text-center py-4">
                No stocks found matching "{searchQuery}"
              </p>
            )}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!loading && watchlistStocks.length === 0 && (
        <div className="card">
          <EmptyState
            variant="watchlist"
            title="Your watchlist is empty"
            description="Add stocks you want to track. They'll appear here with live prices and signals."
            action={{
              label: 'Add your first stock',
              onClick: () => setShowAddModal(true),
            }}
          />
        </div>
      )}

      {/* Watchlist Grid */}
      {!loading && watchlistStocks.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {watchlistStocks.map(stock => {
            const isPositive = (stock.change_percent ?? 0) > 0;
            const isNegative = (stock.change_percent ?? 0) < 0;
            
            return (
              <div key={stock.symbol} className="card p-4 hover:bg-[var(--color-bg-hover)] transition-colors">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="font-semibold text-[var(--color-text-primary)]">{stock.symbol}</h3>
                    <p className="text-xs text-[var(--color-text-tertiary)] truncate max-w-[150px]">{stock.name}</p>
                  </div>
                  <button
                    onClick={() => removeFromWatchlist(stock.symbol)}
                    className="text-[var(--color-text-tertiary)] hover:text-red-400 transition-colors"
                    title="Remove from watchlist"
                  >
                    <svg width="16" height="16" className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                <div className="flex items-end justify-between">
                  <div>
                    <p className="text-xl font-mono font-bold text-[var(--color-text-primary)]">
                      ₦{stock.price?.toFixed(2)}
                    </p>
                    <p className={`text-sm font-mono ${
                      isPositive ? 'text-emerald-400' : isNegative ? 'text-red-400' : 'text-[var(--color-text-tertiary)]'
                    }`}>
                      {isPositive ? '+' : ''}{stock.change_percent?.toFixed(2)}%
                    </p>
                  </div>

                  <div className="text-right">
                    <p className="text-xs text-[var(--color-text-tertiary)]">{stock.sector || 'N/A'}</p>
                    <p className="text-xs text-[var(--color-text-tertiary)]">
                      Vol: {((stock.volume ?? 0) / 1000).toFixed(0)}K
                    </p>
                  </div>
                </div>

                {stock.recommendation && (
                  <div className={`mt-3 px-2 py-1 rounded text-xs font-medium inline-block ${
                    stock.recommendation === 'STRONG_BUY' || stock.recommendation === 'BUY' 
                      ? 'bg-emerald-500/10 text-emerald-400'
                      : stock.recommendation === 'SELL' || stock.recommendation === 'STRONG_SELL'
                        ? 'bg-red-500/10 text-red-400'
                        : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)]'
                  }`}>
                    {stock.recommendation.replace('_', ' ')}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="card p-4 animate-pulse">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="h-5 w-16 bg-[var(--color-bg-tertiary)] rounded mb-2" />
                  <div className="h-3 w-24 bg-[var(--color-bg-tertiary)] rounded" />
                </div>
              </div>
              <div className="h-7 w-24 bg-[var(--color-bg-tertiary)] rounded mb-2" />
              <div className="h-4 w-16 bg-[var(--color-bg-tertiary)] rounded" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Watchlist;
