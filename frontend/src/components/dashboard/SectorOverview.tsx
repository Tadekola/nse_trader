/**
 * SectorOverview - Sector performance breakdown
 * 
 * Shows which sectors are leading/lagging.
 * Critical for Nigerian market context where sector rotation matters.
 */

import React from 'react';
import type { Stock } from '../../core';

interface SectorOverviewProps {
  stocks: Stock[];
  loading?: boolean;
  onSectorClick?: (sector: string) => void;
}

interface SectorData {
  name: string;
  stockCount: number;
  avgChange: number;
  totalVolume: number;
  leadingStock: Stock | null;
}

const SectorOverview: React.FC<SectorOverviewProps> = ({
  stocks,
  loading = false,
  onSectorClick,
}) => {
  // Calculate sector performance
  const sectorData = React.useMemo(() => {
    const sectorMap = new Map<string, Stock[]>();
    
    stocks.forEach(stock => {
      const sector = stock.sector || 'Other';
      if (!sectorMap.has(sector)) {
        sectorMap.set(sector, []);
      }
      sectorMap.get(sector)!.push(stock);
    });

    const sectors: SectorData[] = [];
    
    sectorMap.forEach((sectorStocks, name) => {
      const avgChange = sectorStocks.reduce((sum, s) => sum + (s.change_percent || 0), 0) / sectorStocks.length;
      const totalVolume = sectorStocks.reduce((sum, s) => sum + (s.volume || 0), 0);
      const leadingStock = [...sectorStocks].sort((a, b) => 
        (b.change_percent || 0) - (a.change_percent || 0)
      )[0] || null;

      sectors.push({
        name,
        stockCount: sectorStocks.length,
        avgChange,
        totalVolume,
        leadingStock,
      });
    });

    return sectors.sort((a, b) => b.avgChange - a.avgChange);
  }, [stocks]);

  if (loading) {
    return (
      <div className="card p-4">
        <div className="h-4 w-32 bg-[var(--color-bg-tertiary)] rounded mb-4 animate-pulse"></div>
        <div className="space-y-3">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="flex items-center justify-between animate-pulse">
              <div className="h-4 w-24 bg-[var(--color-bg-tertiary)] rounded"></div>
              <div className="h-4 w-16 bg-[var(--color-bg-tertiary)] rounded"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wide">
          Sector Performance
        </h3>
        <span className="text-xs text-[var(--color-text-tertiary)]">
          {sectorData.length} sectors
        </span>
      </div>

      <div className="space-y-2">
        {sectorData.slice(0, 6).map((sector) => {
          const isPositive = sector.avgChange > 0;
          const isNegative = sector.avgChange < 0;
          
          return (
            <button
              key={sector.name}
              onClick={() => onSectorClick?.(sector.name)}
              className="w-full flex items-center justify-between py-2 px-2 rounded hover:bg-[var(--color-bg-hover)] transition-colors text-left group"
            >
              <div className="flex items-center gap-3 min-w-0">
                {/* Performance bar */}
                <div className="w-1 h-6 rounded-full overflow-hidden bg-[var(--color-bg-tertiary)]">
                  <div 
                    className={`w-full transition-all ${
                      isPositive ? 'bg-emerald-400' : isNegative ? 'bg-red-400' : 'bg-[var(--color-text-tertiary)]'
                    }`}
                    style={{ 
                      height: `${Math.min(100, Math.abs(sector.avgChange) * 10 + 30)}%`,
                      marginTop: isNegative ? 'auto' : 0 
                    }}
                  />
                </div>
                
                <div className="min-w-0">
                  <span className="text-sm font-medium text-[var(--color-text-primary)] group-hover:text-[var(--color-accent-primary)] transition-colors">
                    {sector.name}
                  </span>
                  <div className="flex items-center gap-2 text-xs text-[var(--color-text-tertiary)]">
                    <span>{sector.stockCount} stocks</span>
                    {sector.leadingStock && (
                      <>
                        <span>•</span>
                        <span className="truncate">{sector.leadingStock.symbol}</span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              <div className="text-right">
                <span className={`font-mono text-sm font-medium ${
                  isPositive ? 'text-emerald-400' : isNegative ? 'text-red-400' : 'text-[var(--color-text-tertiary)]'
                }`}>
                  {isPositive ? '+' : ''}{sector.avgChange.toFixed(2)}%
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {sectorData.length > 6 && (
        <button className="w-full mt-3 py-2 text-xs font-medium text-[var(--color-text-tertiary)] hover:text-[var(--color-accent-primary)] transition-colors">
          View all {sectorData.length} sectors →
        </button>
      )}
    </div>
  );
};

export default SectorOverview;
