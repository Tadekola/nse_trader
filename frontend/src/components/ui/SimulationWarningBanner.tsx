/**
 * Simulation Warning Banner
 * 
 * Displays a visible warning when ANY stock data is simulated.
 * This is critical for investor protection - simulated data must
 * never be mistaken for real market prices.
 */

import React from 'react';

interface SimulationWarningBannerProps {
  simulatedCount: number;
  simulatedSymbols?: string[];
  totalCount: number;
  onDismiss?: () => void;
}

const SimulationWarningBanner: React.FC<SimulationWarningBannerProps> = ({
  simulatedCount,
  simulatedSymbols = [],
  totalCount,
  onDismiss,
}) => {
  if (simulatedCount === 0) {
    return null;
  }

  const isFullSimulation = simulatedCount === totalCount;
  const symbolsPreview = simulatedSymbols.slice(0, 5).join(', ');
  const hasMoreSymbols = simulatedSymbols.length > 5;

  return (
    <div className={`
      rounded-lg p-4 mb-4 border-l-4
      ${isFullSimulation 
        ? 'bg-red-500/10 border-red-500 text-red-400' 
        : 'bg-amber-500/10 border-amber-500 text-amber-400'
      }
    `}>
      <div className="flex items-start gap-3">
        {/* Warning Icon */}
        <svg 
          width="24" 
          height="24" 
          className="w-6 h-6 flex-shrink-0 mt-0.5" 
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path 
            strokeLinecap="round" 
            strokeLinejoin="round" 
            strokeWidth={2} 
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" 
          />
        </svg>

        <div className="flex-1">
          {/* Main Warning */}
          <h4 className="font-semibold text-sm mb-1">
            {isFullSimulation 
              ? '⚠️ Simulation Mode Active' 
              : `⚠️ Partial Simulation Active (${simulatedCount} of ${totalCount} stocks)`
            }
          </h4>

          {/* Description */}
          <p className="text-xs opacity-90 mb-2">
            {isFullSimulation 
              ? 'All market data is currently simulated. Real-time data sources are temporarily unavailable.'
              : `${simulatedCount} stock${simulatedCount > 1 ? 's are' : ' is'} using simulated prices due to data source limitations.`
            }
          </p>

          {/* Affected Symbols */}
          {simulatedSymbols.length > 0 && !isFullSimulation && (
            <p className="text-xs opacity-75 font-mono">
              Affected: {symbolsPreview}{hasMoreSymbols ? ` +${simulatedSymbols.length - 5} more` : ''}
            </p>
          )}

          {/* Critical Warning */}
          <div className={`
            mt-3 p-2 rounded text-xs font-medium
            ${isFullSimulation ? 'bg-red-500/20' : 'bg-amber-500/20'}
          `}>
            ⛔ Do NOT use for live trading decisions
          </div>
        </div>

        {/* Dismiss Button (optional) */}
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="p-1 rounded hover:bg-white/10 transition-colors"
            aria-label="Dismiss warning"
          >
            <svg width="16" height="16" className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
};

export default SimulationWarningBanner;
