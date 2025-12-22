/**
 * Screener Page - Dedicated Stock Screening Experience
 * 
 * Full-featured stock screener with advanced filtering,
 * sorting, and analysis capabilities.
 */

import React, { useState, useEffect, useCallback } from 'react';
import StockScreener from '../components/screener/StockScreener';
import { stocksService, type Stock } from '../core';

const Screener: React.FC = () => {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [sectors, setSectors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [stocksData, sectorsData] = await Promise.all([
        stocksService.getAll(),
        stocksService.getSectors(),
      ]);
      setStocks(stocksData);
      setSectors(sectorsData);
    } catch (err) {
      console.error('Failed to fetch screener data:', err);
      setError('Failed to load stocks. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleStockClick = (symbol: string) => {
    console.log('Stock clicked:', symbol);
    // TODO: Open stock detail modal or navigate to stock page
  };

  return (
    <div className="space-y-6 pb-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">
            Stock Screener
          </h1>
          <p className="text-sm text-[var(--color-text-tertiary)] mt-1">
            Filter, sort, and analyze {stocks.length} Nigerian stocks
          </p>
        </div>

        {/* Refresh Button */}
        <button
          onClick={fetchData}
          disabled={loading}
          className="px-4 py-2 bg-[var(--color-bg-tertiary)] text-[var(--color-text-secondary)] text-sm font-medium rounded-lg hover:bg-[var(--color-bg-hover)] transition-colors disabled:opacity-50"
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card p-4">
          <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">Total Stocks</p>
          <p className="text-2xl font-mono font-bold text-[var(--color-text-primary)] mt-1">
            {loading ? '—' : stocks.length}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">Sectors</p>
          <p className="text-2xl font-mono font-bold text-[var(--color-text-primary)] mt-1">
            {loading ? '—' : sectors.length}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">Gainers</p>
          <p className="text-2xl font-mono font-bold text-emerald-400 mt-1">
            {loading ? '—' : stocks.filter(s => (s.change_percent ?? 0) > 0).length}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">Decliners</p>
          <p className="text-2xl font-mono font-bold text-red-400 mt-1">
            {loading ? '—' : stocks.filter(s => (s.change_percent ?? 0) < 0).length}
          </p>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 flex items-center gap-3">
          <svg width="20" height="20" className="w-5 h-5 text-red-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm text-red-400">{error}</p>
          <button 
            onClick={fetchData}
            className="ml-auto text-xs text-red-400 hover:text-red-300 underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Stock Screener Table */}
      <StockScreener
        stocks={stocks}
        loading={loading}
        onStockClick={handleStockClick}
      />
    </div>
  );
};

export default Screener;
