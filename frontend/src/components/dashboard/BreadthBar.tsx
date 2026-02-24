/**
 * Breadth Bar Component (Layer 2)
 * 
 * Visual representation of market breadth (advancers vs decliners).
 * Compact, scannable, no numbers required to understand.
 */

import React from 'react';

interface BreadthBarProps {
  advancing: number;
  declining: number;
  unchanged: number;
  loading?: boolean;
}

const BreadthBar: React.FC<BreadthBarProps> = ({ 
  advancing, 
  declining, 
  unchanged,
  loading 
}) => {
  if (loading) {
    return (
      <div className="breadth-bar breadth-bar--loading">
        <div className="breadth-bar__skeleton" />
      </div>
    );
  }

  const total = advancing + declining + unchanged;
  
  if (total === 0) {
    return (
      <div className="breadth-bar breadth-bar--empty">
        <span className="breadth-bar__empty-text">No market data</span>
      </div>
    );
  }

  const advPct = (advancing / total) * 100;
  const decPct = (declining / total) * 100;
  const unchPct = (unchanged / total) * 100;

  // Determine market sentiment label
  const getSentiment = () => {
    if (advancing > declining * 1.5) return { label: 'Strong Buying', class: 'bullish' };
    if (advancing > declining) return { label: 'Buyers Lead', class: 'bullish' };
    if (declining > advancing * 1.5) return { label: 'Strong Selling', class: 'bearish' };
    if (declining > advancing) return { label: 'Sellers Lead', class: 'bearish' };
    return { label: 'Mixed', class: 'neutral' };
  };

  const sentiment = getSentiment();

  return (
    <div className="breadth-bar">
      <div className="breadth-bar__header">
        <span className="breadth-bar__label">Market Breadth</span>
        <span className={`breadth-bar__sentiment breadth-bar__sentiment--${sentiment.class}`}>
          {sentiment.label}
        </span>
      </div>
      
      <div className="breadth-bar__track">
        <div 
          className="breadth-bar__segment breadth-bar__segment--up"
          style={{ width: `${advPct}%` }}
          title={`${advancing} advancing (${advPct.toFixed(1)}%)`}
        />
        <div 
          className="breadth-bar__segment breadth-bar__segment--unchanged"
          style={{ width: `${unchPct}%` }}
          title={`${unchanged} unchanged (${unchPct.toFixed(1)}%)`}
        />
        <div 
          className="breadth-bar__segment breadth-bar__segment--down"
          style={{ width: `${decPct}%` }}
          title={`${declining} declining (${decPct.toFixed(1)}%)`}
        />
      </div>
      
      <div className="breadth-bar__legend">
        <span className="breadth-bar__legend-item">
          <span className="breadth-bar__dot breadth-bar__dot--up" />
          {advancing}
        </span>
        <span className="breadth-bar__legend-item">
          <span className="breadth-bar__dot breadth-bar__dot--unchanged" />
          {unchanged}
        </span>
        <span className="breadth-bar__legend-item">
          <span className="breadth-bar__dot breadth-bar__dot--down" />
          {declining}
        </span>
      </div>
    </div>
  );
};

export default BreadthBar;
