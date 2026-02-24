/**
 * Quick Movers Component (Layer 2)
 * 
 * Compact gainers/losers display for the actionable summary layer.
 * Designed for fast scanning and quick decisions.
 */

import React from 'react';
import type { MoverStock } from '../../core/api/uiService';

interface QuickMoversProps {
  gainers: MoverStock[];
  losers: MoverStock[];
  loading?: boolean;
  onStockClick?: (symbol: string) => void;
}

const QuickMovers: React.FC<QuickMoversProps> = ({ 
  gainers, 
  losers, 
  loading,
  onStockClick 
}) => {
  if (loading) {
    return (
      <div className="quick-movers">
        <div className="quick-movers__section">
          <h3 className="quick-movers__title quick-movers__title--up">
            <span className="quick-movers__icon">↑</span> Top Gainers
          </h3>
          <div className="quick-movers__list">
            {[1, 2, 3].map(i => (
              <div key={i} className="quick-movers__item quick-movers__item--skeleton">
                <div className="skeleton skeleton--text" style={{ width: '60px' }} />
                <div className="skeleton skeleton--text" style={{ width: '40px' }} />
              </div>
            ))}
          </div>
        </div>
        <div className="quick-movers__section">
          <h3 className="quick-movers__title quick-movers__title--down">
            <span className="quick-movers__icon">↓</span> Top Losers
          </h3>
          <div className="quick-movers__list">
            {[1, 2, 3].map(i => (
              <div key={i} className="quick-movers__item quick-movers__item--skeleton">
                <div className="skeleton skeleton--text" style={{ width: '60px' }} />
                <div className="skeleton skeleton--text" style={{ width: '40px' }} />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const renderMover = (stock: MoverStock, type: 'gainer' | 'loser') => (
    <button
      key={stock.symbol}
      className={`quick-movers__item quick-movers__item--${type}`}
      onClick={() => onStockClick?.(stock.symbol)}
    >
      <div className="quick-movers__stock">
        <span className="quick-movers__symbol">{stock.symbol}</span>
        <span className="quick-movers__price">₦{stock.price.toFixed(2)}</span>
      </div>
      <span className={`quick-movers__change quick-movers__change--${type}`}>
        {stock.change_pct >= 0 ? '+' : ''}{stock.change_pct.toFixed(2)}%
      </span>
    </button>
  );

  return (
    <div className="quick-movers">
      <div className="quick-movers__section">
        <h3 className="quick-movers__title quick-movers__title--up">
          <span className="quick-movers__icon">↑</span> Top Gainers
        </h3>
        <div className="quick-movers__list">
          {gainers.length > 0 ? (
            gainers.map(stock => renderMover(stock, 'gainer'))
          ) : (
            <div className="quick-movers__empty">No gainers today</div>
          )}
        </div>
      </div>
      
      <div className="quick-movers__section">
        <h3 className="quick-movers__title quick-movers__title--down">
          <span className="quick-movers__icon">↓</span> Top Losers
        </h3>
        <div className="quick-movers__list">
          {losers.length > 0 ? (
            losers.map(stock => renderMover(stock, 'loser'))
          ) : (
            <div className="quick-movers__empty">No losers today</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default QuickMovers;
