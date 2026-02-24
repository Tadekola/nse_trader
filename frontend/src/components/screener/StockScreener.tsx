/**
 * StockScreener - Professional stock table with advanced filtering
 * 
 * Designed for scanning and comparison.
 * Supports sorting, filtering, and customizable columns.
 */

import React, { useState, useMemo } from 'react';
import type { Stock } from '../../core';

interface StockScreenerProps {
  stocks: Stock[];
  loading?: boolean;
  onStockClick?: (symbol: string) => void;
}

type SortKey = 'symbol' | 'name' | 'price' | 'change_percent' | 'volume' | 'sector';
type SortDirection = 'asc' | 'desc';

interface FilterState {
  search: string;
  sector: string;
  changeFilter: 'all' | 'gainers' | 'losers';
  liquidityFilter: 'all' | 'high' | 'medium' | 'low';
}

const StockScreener: React.FC<StockScreenerProps> = ({
  stocks,
  loading = false,
  onStockClick,
}) => {
  const [sortKey, setSortKey] = useState<SortKey>('change_percent');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [filters, setFilters] = useState<FilterState>({
    search: '',
    sector: 'all',
    changeFilter: 'all',
    liquidityFilter: 'all',
  });

  // Get unique sectors
  const sectors = useMemo(() => {
    const sectorSet = new Set(stocks.map(s => s.sector || 'Other'));
    return ['all', ...Array.from(sectorSet).sort()];
  }, [stocks]);

  // Filter and sort stocks
  const filteredStocks = useMemo(() => {
    let result = [...stocks];

    // Search filter
    if (filters.search) {
      const search = filters.search.toLowerCase();
      result = result.filter(s => 
        s.symbol.toLowerCase().includes(search) ||
        s.name?.toLowerCase().includes(search)
      );
    }

    // Sector filter
    if (filters.sector !== 'all') {
      result = result.filter(s => (s.sector || 'Other') === filters.sector);
    }

    // Change filter
    if (filters.changeFilter === 'gainers') {
      result = result.filter(s => (s.change_percent || 0) > 0);
    } else if (filters.changeFilter === 'losers') {
      result = result.filter(s => (s.change_percent || 0) < 0);
    }

    // Liquidity filter
    if (filters.liquidityFilter !== 'all') {
      result = result.filter(s => s.liquidity_tier === filters.liquidityFilter);
    }

    // Sort
    result.sort((a, b) => {
      let aVal: string | number = 0;
      let bVal: string | number = 0;

      switch (sortKey) {
        case 'symbol':
          aVal = a.symbol;
          bVal = b.symbol;
          break;
        case 'name':
          aVal = a.name || '';
          bVal = b.name || '';
          break;
        case 'price':
          aVal = a.price || 0;
          bVal = b.price || 0;
          break;
        case 'change_percent':
          aVal = a.change_percent || 0;
          bVal = b.change_percent || 0;
          break;
        case 'volume':
          aVal = a.volume || 0;
          bVal = b.volume || 0;
          break;
        case 'sector':
          aVal = a.sector || '';
          bVal = b.sector || '';
          break;
      }

      if (typeof aVal === 'string') {
        return sortDirection === 'asc' 
          ? aVal.localeCompare(bVal as string)
          : (bVal as string).localeCompare(aVal);
      }
      return sortDirection === 'asc' ? aVal - (bVal as number) : (bVal as number) - aVal;
    });

    return result;
  }, [stocks, filters, sortKey, sortDirection]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDirection('desc');
    }
  };

  const SortIcon = ({ column }: { column: SortKey }) => {
    if (sortKey !== column) {
      return (
        <svg width="12" height="12" className="w-3 h-3 text-[var(--color-text-tertiary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
        </svg>
      );
    }
    return sortDirection === 'asc' ? (
      <svg width="12" height="12" className="w-3 h-3 text-[var(--color-accent-primary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
      </svg>
    ) : (
      <svg width="12" height="12" className="w-3 h-3 text-[var(--color-accent-primary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
      </svg>
    );
  };

  const formatVolume = (vol: number) => {
    if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(1)}M`;
    if (vol >= 1_000) return `${(vol / 1_000).toFixed(0)}K`;
    return vol.toString();
  };

  const formatSource = (source: string) => {
    switch (source) {
      case 'ngx_official': return 'NGX';
      case 'ngnmarket': return 'NGN Market';
      case 'apt_securities': return 'Apt Sec';
      case 'kwayisi': return 'Kwayisi';
      case 'simulated': return 'Simulated';
      default: return source;
    }
  };

  return (
    <div className="card overflow-hidden">
      {/* Filters */}
      <div className="p-4 border-b border-[var(--color-border-subtle)]">
        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <svg width="16" height="16" className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-text-tertiary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search stocks..."
              value={filters.search}
              onChange={(e) => setFilters({ ...filters, search: e.target.value })}
              className="w-full pl-10 pr-4 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border-subtle)] rounded-lg text-sm text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)] focus:outline-none focus:border-[var(--color-accent-primary)]"
            />
          </div>

          {/* Sector Filter */}
          <select
            value={filters.sector}
            onChange={(e) => setFilters({ ...filters, sector: e.target.value })}
            className="px-3 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border-subtle)] rounded-lg text-sm text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent-primary)]"
          >
            {sectors.map(sector => (
              <option key={sector} value={sector}>
                {sector === 'all' ? 'All Sectors' : sector}
              </option>
            ))}
          </select>

          {/* Change Filter */}
          <div className="flex items-center gap-1 p-1 bg-[var(--color-bg-tertiary)] rounded-lg">
            {(['all', 'gainers', 'losers'] as const).map((filter) => (
              <button
                key={filter}
                onClick={() => setFilters({ ...filters, changeFilter: filter })}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  filters.changeFilter === filter
                    ? 'bg-[var(--color-accent-primary)] text-white'
                    : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
                }`}
              >
                {filter === 'all' ? 'All' : filter === 'gainers' ? 'Gainers' : 'Losers'}
              </button>
            ))}
          </div>

          {/* Results count */}
          <span className="text-xs text-[var(--color-text-tertiary)] ml-auto">
            {filteredStocks.length} of {stocks.length} stocks
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full">
          <thead>
            <tr className="table-header">
              <th 
                className="table-cell text-left cursor-pointer hover:bg-[var(--color-bg-hover)]"
                onClick={() => handleSort('symbol')}
              >
                <div className="flex items-center gap-1">
                  Symbol <SortIcon column="symbol" />
                </div>
              </th>
              <th 
                className="table-cell text-left cursor-pointer hover:bg-[var(--color-bg-hover)]"
                onClick={() => handleSort('name')}
              >
                <div className="flex items-center gap-1">
                  Name <SortIcon column="name" />
                </div>
              </th>
              <th 
                className="table-cell text-right cursor-pointer hover:bg-[var(--color-bg-hover)]"
                onClick={() => handleSort('price')}
              >
                <div className="flex items-center justify-end gap-1">
                  Price <SortIcon column="price" />
                </div>
              </th>
              <th 
                className="table-cell text-right cursor-pointer hover:bg-[var(--color-bg-hover)]"
                onClick={() => handleSort('change_percent')}
              >
                <div className="flex items-center justify-end gap-1">
                  Change <SortIcon column="change_percent" />
                </div>
              </th>
              <th 
                className="table-cell text-right cursor-pointer hover:bg-[var(--color-bg-hover)]"
                onClick={() => handleSort('volume')}
              >
                <div className="flex items-center justify-end gap-1">
                  Volume <SortIcon column="volume" />
                </div>
              </th>
              <th 
                className="table-cell text-left cursor-pointer hover:bg-[var(--color-bg-hover)]"
                onClick={() => handleSort('sector')}
              >
                <div className="flex items-center gap-1">
                  Sector <SortIcon column="sector" />
                </div>
              </th>
              <th className="table-cell text-right">
                Source
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              // Loading skeleton
              Array.from({ length: 10 }).map((_, i) => (
                <tr key={i} className="table-row animate-pulse">
                  <td className="table-cell"><div className="h-4 w-16 bg-[var(--color-bg-tertiary)] rounded"></div></td>
                  <td className="table-cell"><div className="h-4 w-32 bg-[var(--color-bg-tertiary)] rounded"></div></td>
                  <td className="table-cell text-right"><div className="h-4 w-16 bg-[var(--color-bg-tertiary)] rounded ml-auto"></div></td>
                  <td className="table-cell text-right"><div className="h-4 w-14 bg-[var(--color-bg-tertiary)] rounded ml-auto"></div></td>
                  <td className="table-cell text-right"><div className="h-4 w-14 bg-[var(--color-bg-tertiary)] rounded ml-auto"></div></td>
                  <td className="table-cell"><div className="h-4 w-20 bg-[var(--color-bg-tertiary)] rounded"></div></td>
                  <td className="table-cell text-right"><div className="h-4 w-12 bg-[var(--color-bg-tertiary)] rounded ml-auto"></div></td>
                </tr>
              ))
            ) : filteredStocks.length === 0 ? (
              <tr>
                <td colSpan={7} className="table-cell text-center py-8 text-[var(--color-text-tertiary)]">
                  No stocks match your filters
                </td>
              </tr>
            ) : (
              filteredStocks.map((stock) => {
                const isPositive = (stock.change_percent || 0) > 0;
                const isNegative = (stock.change_percent || 0) < 0;
                
                return (
                  <tr 
                    key={stock.symbol}
                    className="table-row cursor-pointer"
                    onClick={() => onStockClick?.(stock.symbol)}
                  >
                    <td className="table-cell font-medium text-[var(--color-text-primary)]">
                      {stock.symbol}
                    </td>
                    <td className="table-cell text-[var(--color-text-secondary)] truncate max-w-[200px]">
                      {stock.name}
                    </td>
                    <td className="table-cell table-cell-mono text-right text-[var(--color-text-primary)]">
                      ₦{stock.price?.toFixed(2)}
                    </td>
                    <td className={`table-cell table-cell-mono text-right ${
                      isPositive ? 'text-emerald-400' : isNegative ? 'text-red-400' : 'text-[var(--color-text-tertiary)]'
                    }`}>
                      {isPositive ? '+' : ''}{stock.change_percent?.toFixed(2)}%
                    </td>
                    <td className="table-cell table-cell-mono text-right text-[var(--color-text-secondary)]">
                      {formatVolume(stock.volume || 0)}
                    </td>
                    <td className="table-cell text-[var(--color-text-tertiary)] text-xs">
                      {stock.sector || 'Other'}
                    </td>
                    <td className="table-cell text-right">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-medium ${
                        stock.source === 'ngx_official' || stock.source === 'ngnmarket'
                          ? 'bg-emerald-500/10 text-emerald-400'
                          : stock.source === 'kwayisi'
                            ? 'bg-blue-500/10 text-blue-400'
                            : 'bg-amber-500/10 text-amber-400'
                      }`}>
                        {formatSource(stock.source || 'unknown')}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      {!loading && filteredStocks.length > 0 && (
        <div className="p-3 border-t border-[var(--color-border-subtle)] text-xs text-[var(--color-text-tertiary)]">
          Showing {filteredStocks.length} stocks • Click a row for details
        </div>
      )}
    </div>
  );
};

export default StockScreener;
