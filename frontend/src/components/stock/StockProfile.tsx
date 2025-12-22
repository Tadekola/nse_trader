/**
 * StockProfile - Institutional-style stock detail view
 * 
 * Comprehensive stock analysis with clear separation between:
 * - Facts (price, volume, fundamentals)
 * - Signals (technical indicators, patterns)
 * - Opinions (recommendations, ratings)
 */

import React, { useState, useEffect } from 'react';
import { stocksService, recommendationsService, type Stock, type Recommendation } from '../../core';

interface StockProfileProps {
  symbol: string;
  onClose?: () => void;
}

type TabType = 'overview' | 'technicals' | 'fundamentals' | 'signals';

const StockProfile: React.FC<StockProfileProps> = ({ symbol, onClose }) => {
  const [stock, setStock] = useState<Stock | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [indicators, setIndicators] = useState<Record<string, any> | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const [stockData, recData, indicatorData] = await Promise.allSettled([
          stocksService.get(symbol),
          recommendationsService.get(symbol, 'swing', 'intermediate'),
          stocksService.getIndicators(symbol),
        ]);

        if (stockData.status === 'fulfilled') setStock(stockData.value);
        if (recData.status === 'fulfilled') setRecommendation(recData.value);
        if (indicatorData.status === 'fulfilled') setIndicators(indicatorData.value);

        if (stockData.status === 'rejected') {
          throw new Error('Failed to load stock data');
        }
      } catch (err) {
        console.error('Failed to fetch stock profile:', err);
        setError('Failed to load stock profile');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [symbol]);

  const tabs: { id: TabType; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'technicals', label: 'Technicals' },
    { id: 'fundamentals', label: 'Fundamentals' },
    { id: 'signals', label: 'Signals' },
  ];

  const isPositive = (stock?.change_percent || 0) > 0;
  const isNegative = (stock?.change_percent || 0) < 0;

  if (loading) {
    return (
      <div className="card p-6 animate-pulse">
        <div className="flex items-center gap-4 mb-6">
          <div className="h-8 w-24 bg-[var(--color-bg-tertiary)] rounded"></div>
          <div className="h-6 w-48 bg-[var(--color-bg-tertiary)] rounded"></div>
        </div>
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-20 bg-[var(--color-bg-tertiary)] rounded-lg"></div>
          ))}
        </div>
      </div>
    );
  }

  if (error || !stock) {
    return (
      <div className="card p-6 text-center">
        <svg width="16" height="16" className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="text-[var(--color-text-secondary)]">{error || 'Stock not found'}</p>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-[var(--color-border-subtle)]">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h2 className="text-2xl font-bold text-[var(--color-text-primary)]">
                {stock.symbol}
              </h2>
              {recommendation && (
                <span className={`px-3 py-1 rounded-lg text-sm font-medium ${
                  recommendation.action.includes('BUY') 
                    ? 'bg-emerald-500/15 text-emerald-400' 
                    : recommendation.action.includes('SELL')
                      ? 'bg-red-500/15 text-red-400'
                      : 'bg-amber-500/15 text-amber-400'
                }`}>
                  {recommendation.action.replace('_', ' ')}
                </span>
              )}
            </div>
            <p className="text-[var(--color-text-secondary)]">{stock.name}</p>
            {stock.sector && (
              <p className="text-xs text-[var(--color-text-tertiary)] mt-1">{stock.sector}</p>
            )}
          </div>
          
          {onClose && (
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-[var(--color-bg-hover)] transition-colors"
            >
              <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {/* Price Display */}
        <div className="mt-4 flex items-end gap-4">
          <div>
            <p className="text-3xl font-mono font-bold text-[var(--color-text-primary)]">
              ₦{stock.price?.toFixed(2)}
            </p>
          </div>
          <div className={`flex items-center gap-2 pb-1 ${
            isPositive ? 'text-emerald-400' : isNegative ? 'text-red-400' : 'text-[var(--color-text-tertiary)]'
          }`}>
            <span className="font-mono text-lg">
              {isPositive ? '+' : ''}₦{stock.change?.toFixed(2)}
            </span>
            <span className={`px-2 py-0.5 rounded text-sm font-mono ${
              isPositive ? 'bg-emerald-500/15' : isNegative ? 'bg-red-500/15' : 'bg-[var(--color-bg-tertiary)]'
            }`}>
              {isPositive ? '+' : ''}{stock.change_percent?.toFixed(2)}%
            </span>
          </div>
        </div>
      </div>

      {/* Key Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-[var(--color-bg-tertiary)]">
        <div>
          <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">Volume</p>
          <p className="font-mono text-lg text-[var(--color-text-primary)]">
            {stock.volume ? `${(stock.volume / 1_000_000).toFixed(2)}M` : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">Open</p>
          <p className="font-mono text-lg text-[var(--color-text-primary)]">
            ₦{stock.open?.toFixed(2) || '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">High</p>
          <p className="font-mono text-lg text-emerald-400">
            ₦{stock.high?.toFixed(2) || '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-[var(--color-text-tertiary)] uppercase tracking-wide">Low</p>
          <p className="font-mono text-lg text-red-400">
            ₦{stock.low?.toFixed(2) || '—'}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[var(--color-border-subtle)]">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-[var(--color-accent-primary)] border-b-2 border-[var(--color-accent-primary)]'
                : 'text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="p-6">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Recommendation Summary */}
            {recommendation && (
              <div className="p-4 bg-[var(--color-bg-tertiary)] rounded-lg">
                <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-2">
                  Signal Summary
                </h3>
                <p className="text-sm text-[var(--color-text-secondary)]">
                  {recommendation.primary_reason}
                </p>
                <div className="flex items-center gap-4 mt-3 text-xs text-[var(--color-text-tertiary)]">
                  <span>Confidence: <strong className="text-[var(--color-text-primary)]">{recommendation.confidence}%</strong></span>
                  <span>Risk: <strong className="text-[var(--color-text-primary)]">{recommendation.risk_level}</strong></span>
                  <span>Horizon: <strong className="text-[var(--color-text-primary)]">{recommendation.horizon.replace('_', ' ')}</strong></span>
                </div>
              </div>
            )}

            {/* Liquidity Warning */}
            {stock.liquidity_tier && stock.liquidity_tier !== 'high' && (
              <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg flex items-start gap-3">
                <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div>
                  <p className="text-sm font-medium text-amber-400">Low Liquidity Warning</p>
                  <p className="text-xs text-amber-400/80 mt-1">
                    This stock has {stock.liquidity_tier} liquidity. You may experience difficulty executing large orders or wider bid-ask spreads.
                  </p>
                </div>
              </div>
            )}

            {/* Entry/Exit Points */}
            {recommendation?.entry_exit && (
              <div>
                <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3">Entry & Exit Points</h3>
                <div className="grid grid-cols-4 gap-4">
                  <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                    <p className="text-xs text-[var(--color-text-tertiary)]">Entry</p>
                    <p className="font-mono text-lg text-[var(--color-text-primary)]">
                      ₦{recommendation.entry_exit.entry_price?.toFixed(2)}
                    </p>
                  </div>
                  <div className="p-3 bg-red-500/10 rounded-lg">
                    <p className="text-xs text-red-400">Stop Loss</p>
                    <p className="font-mono text-lg text-red-400">
                      ₦{recommendation.entry_exit.stop_loss?.toFixed(2)}
                    </p>
                  </div>
                  <div className="p-3 bg-emerald-500/10 rounded-lg">
                    <p className="text-xs text-emerald-400">Target</p>
                    <p className="font-mono text-lg text-emerald-400">
                      ₦{recommendation.entry_exit.target_1?.toFixed(2)}
                    </p>
                  </div>
                  <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                    <p className="text-xs text-[var(--color-text-tertiary)]">R:R Ratio</p>
                    <p className="font-mono text-lg text-[var(--color-text-primary)]">
                      {recommendation.entry_exit.risk_reward?.toFixed(2)}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'technicals' && indicators && (
          <div className="space-y-6">
            {/* Momentum */}
            <div>
              <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3">Momentum</h3>
              <div className="grid grid-cols-3 gap-4">
                <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                  <p className="text-xs text-[var(--color-text-tertiary)]">RSI (14)</p>
                  <p className={`font-mono text-lg ${
                    indicators.rsi > 70 ? 'text-red-400' : indicators.rsi < 30 ? 'text-emerald-400' : 'text-[var(--color-text-primary)]'
                  }`}>
                    {indicators.rsi?.toFixed(1) || '—'}
                  </p>
                  <p className="text-xs text-[var(--color-text-tertiary)]">
                    {indicators.rsi > 70 ? 'Overbought' : indicators.rsi < 30 ? 'Oversold' : 'Neutral'}
                  </p>
                </div>
                <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                  <p className="text-xs text-[var(--color-text-tertiary)]">MACD</p>
                  <p className={`font-mono text-lg ${
                    indicators.macd_histogram > 0 ? 'text-emerald-400' : 'text-red-400'
                  }`}>
                    {indicators.macd?.toFixed(2) || '—'}
                  </p>
                  <p className="text-xs text-[var(--color-text-tertiary)]">
                    {indicators.macd_histogram > 0 ? 'Bullish' : 'Bearish'}
                  </p>
                </div>
                <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                  <p className="text-xs text-[var(--color-text-tertiary)]">ADX</p>
                  <p className="font-mono text-lg text-[var(--color-text-primary)]">
                    {indicators.adx?.toFixed(1) || '—'}
                  </p>
                  <p className="text-xs text-[var(--color-text-tertiary)]">
                    {indicators.adx > 25 ? 'Trending' : 'Ranging'}
                  </p>
                </div>
              </div>
            </div>

            {/* Moving Averages */}
            <div>
              <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3">Moving Averages</h3>
              <div className="grid grid-cols-3 gap-4">
                <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                  <p className="text-xs text-[var(--color-text-tertiary)]">SMA 20</p>
                  <p className="font-mono text-lg text-[var(--color-text-primary)]">
                    ₦{indicators.sma_20?.toFixed(2) || '—'}
                  </p>
                </div>
                <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                  <p className="text-xs text-[var(--color-text-tertiary)]">SMA 50</p>
                  <p className="font-mono text-lg text-[var(--color-text-primary)]">
                    ₦{indicators.sma_50?.toFixed(2) || '—'}
                  </p>
                </div>
                <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                  <p className="text-xs text-[var(--color-text-tertiary)]">SMA 200</p>
                  <p className="font-mono text-lg text-[var(--color-text-primary)]">
                    ₦{indicators.sma_200?.toFixed(2) || '—'}
                  </p>
                </div>
              </div>
            </div>

            {/* Volatility */}
            <div>
              <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3">Volatility</h3>
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                  <p className="text-xs text-[var(--color-text-tertiary)]">ATR (14)</p>
                  <p className="font-mono text-lg text-[var(--color-text-primary)]">
                    ₦{indicators.atr?.toFixed(2) || '—'}
                  </p>
                  <p className="text-xs text-[var(--color-text-tertiary)]">
                    {indicators.atr_percent?.toFixed(1) || '—'}% of price
                  </p>
                </div>
                <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                  <p className="text-xs text-[var(--color-text-tertiary)]">Bollinger Position</p>
                  <p className="font-mono text-lg text-[var(--color-text-primary)]">
                    {indicators.bollinger_position || '—'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'fundamentals' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                <p className="text-xs text-[var(--color-text-tertiary)]">P/E Ratio</p>
                <p className="font-mono text-lg text-[var(--color-text-primary)]">
                  {stock.pe_ratio?.toFixed(1) || '—'}
                </p>
              </div>
              <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                <p className="text-xs text-[var(--color-text-tertiary)]">Dividend Yield</p>
                <p className="font-mono text-lg text-[var(--color-text-primary)]">
                  {stock.dividend_yield ? `${stock.dividend_yield.toFixed(2)}%` : '—'}
                </p>
              </div>
              <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                <p className="text-xs text-[var(--color-text-tertiary)]">Market Cap</p>
                <p className="font-mono text-lg text-[var(--color-text-primary)]">
                  {stock.market_cap ? `₦${(stock.market_cap / 1_000_000_000).toFixed(1)}B` : '—'}
                </p>
              </div>
              <div className="p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                <p className="text-xs text-[var(--color-text-tertiary)]">Liquidity</p>
                <p className={`font-mono text-lg ${
                  stock.liquidity_tier === 'high' ? 'text-emerald-400' :
                  stock.liquidity_tier === 'medium' ? 'text-amber-400' : 'text-red-400'
                }`}>
                  {stock.liquidity_tier?.toUpperCase() || '—'}
                </p>
              </div>
            </div>

            <div className="p-4 bg-[var(--color-bg-tertiary)] rounded-lg">
              <p className="text-xs text-[var(--color-text-tertiary)] mb-2">Note</p>
              <p className="text-sm text-[var(--color-text-secondary)]">
                Fundamental data is sourced from public filings and may not reflect the most recent quarter. 
                Always verify critical metrics before making investment decisions.
              </p>
            </div>
          </div>
        )}

        {activeTab === 'signals' && recommendation && (
          <div className="space-y-6">
            {/* Signal Summary */}
            <div className={`p-4 rounded-lg ${
              recommendation.action.includes('BUY') ? 'bg-emerald-500/10' :
              recommendation.action.includes('SELL') ? 'bg-red-500/10' : 'bg-amber-500/10'
            }`}>
              <div className="flex items-center justify-between mb-3">
                <span className={`px-3 py-1 rounded-lg text-sm font-semibold ${
                  recommendation.action.includes('BUY') ? 'bg-emerald-500/20 text-emerald-400' :
                  recommendation.action.includes('SELL') ? 'bg-red-500/20 text-red-400' :
                  'bg-amber-500/20 text-amber-400'
                }`}>
                  {recommendation.action.replace('_', ' ')}
                </span>
                <span className="text-sm text-[var(--color-text-tertiary)]">
                  {recommendation.confidence}% confidence
                </span>
              </div>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {recommendation.explanation || recommendation.primary_reason}
              </p>
            </div>

            {/* Supporting Reasons */}
            {recommendation.supporting_reasons?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3">Supporting Factors</h3>
                <ul className="space-y-2">
                  {recommendation.supporting_reasons.map((reason, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-[var(--color-text-secondary)]">
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
                <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3">Risk Factors</h3>
                <ul className="space-y-2">
                  {recommendation.risk_warnings.map((warning, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-amber-400">
                      <span className="mt-0.5">⚠</span>
                      {warning}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Technical Signals */}
            {recommendation.signals?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3">Technical Signals</h3>
                <div className="grid grid-cols-2 gap-3">
                  {recommendation.signals.map((signal, i) => (
                    <div 
                      key={i}
                      className={`p-3 rounded-lg ${
                        signal.direction === 'bullish' ? 'bg-emerald-500/10' :
                        signal.direction === 'bearish' ? 'bg-red-500/10' : 'bg-[var(--color-bg-tertiary)]'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-[var(--color-text-primary)]">
                          {signal.name}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          signal.direction === 'bullish' ? 'bg-emerald-500/20 text-emerald-400' :
                          signal.direction === 'bearish' ? 'bg-red-500/20 text-red-400' :
                          'bg-[var(--color-bg-hover)] text-[var(--color-text-tertiary)]'
                        }`}>
                          {signal.direction}
                        </span>
                      </div>
                      <p className="text-xs text-[var(--color-text-tertiary)]">
                        {signal.description}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'technicals' && !indicators && (
          <p className="text-center text-[var(--color-text-tertiary)] py-8">
            Technical indicators not available for this stock.
          </p>
        )}

        {activeTab === 'signals' && !recommendation && (
          <p className="text-center text-[var(--color-text-tertiary)] py-8">
            No signals available for this stock.
          </p>
        )}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-[var(--color-border-subtle)] text-xs text-[var(--color-text-tertiary)]">
        <div className="flex items-center justify-between">
          <span>Source: {stock.source}</span>
          <span>Last updated: {new Date(stock.timestamp).toLocaleString()}</span>
        </div>
      </div>
    </div>
  );
};

export default StockProfile;
