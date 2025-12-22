/**
 * Standardized Loading State Component
 * 
 * Consistent loading indicators across the app.
 * Supports different variants for different contexts.
 */

import React from 'react';

type LoadingVariant = 'spinner' | 'skeleton' | 'dots' | 'pulse';
type LoadingSize = 'sm' | 'md' | 'lg';

interface LoadingStateProps {
  variant?: LoadingVariant;
  size?: LoadingSize;
  text?: string;
  className?: string;
}

const sizeMap = {
  sm: { spinner: 'w-4 h-4', text: 'text-xs' },
  md: { spinner: 'w-6 h-6', text: 'text-sm' },
  lg: { spinner: 'w-8 h-8', text: 'text-base' },
};

const Spinner: React.FC<{ size: LoadingSize }> = ({ size }) => (
  <svg 
    className={`animate-spin ${sizeMap[size].spinner} text-[var(--color-accent-primary)]`}
    fill="none" 
    viewBox="0 0 24 24"
  >
    <circle 
      className="opacity-25" 
      cx="12" 
      cy="12" 
      r="10" 
      stroke="currentColor" 
      strokeWidth="4"
    />
    <path 
      className="opacity-75" 
      fill="currentColor" 
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
    />
  </svg>
);

const Dots: React.FC<{ size: LoadingSize }> = ({ size }) => {
  const dotSize = size === 'sm' ? 'w-1.5 h-1.5' : size === 'md' ? 'w-2 h-2' : 'w-2.5 h-2.5';
  return (
    <div className="flex items-center gap-1">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className={`${dotSize} rounded-full bg-[var(--color-accent-primary)] animate-pulse`}
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </div>
  );
};

const LoadingState: React.FC<LoadingStateProps> = ({
  variant = 'spinner',
  size = 'md',
  text,
  className = '',
}) => {
  const renderLoader = () => {
    switch (variant) {
      case 'spinner':
        return <Spinner size={size} />;
      case 'dots':
        return <Dots size={size} />;
      case 'pulse':
        return (
          <div className={`${sizeMap[size].spinner} rounded-full bg-[var(--color-bg-tertiary)] animate-pulse`} />
        );
      default:
        return <Spinner size={size} />;
    }
  };

  return (
    <div className={`flex items-center justify-center gap-2 ${className}`}>
      {renderLoader()}
      {text && (
        <span className={`${sizeMap[size].text} text-[var(--color-text-tertiary)]`}>
          {text}
        </span>
      )}
    </div>
  );
};

// Skeleton variants for common patterns
export const SkeletonCard: React.FC<{ lines?: number }> = ({ lines = 3 }) => (
  <div className="card p-4 animate-pulse">
    <div className="h-4 w-1/3 bg-[var(--color-bg-tertiary)] rounded mb-3" />
    {Array.from({ length: lines }).map((_, i) => (
      <div 
        key={i} 
        className="h-3 bg-[var(--color-bg-tertiary)] rounded mb-2"
        style={{ width: `${100 - i * 15}%` }}
      />
    ))}
  </div>
);

export const SkeletonTable: React.FC<{ rows?: number; cols?: number }> = ({ 
  rows = 5, 
  cols = 4 
}) => (
  <div className="animate-pulse">
    <div className="flex gap-4 py-3 border-b border-[var(--color-border-subtle)]">
      {Array.from({ length: cols }).map((_, i) => (
        <div key={i} className="h-3 bg-[var(--color-bg-tertiary)] rounded flex-1" />
      ))}
    </div>
    {Array.from({ length: rows }).map((_, rowIndex) => (
      <div key={rowIndex} className="flex gap-4 py-3 border-b border-[var(--color-border-subtle)]">
        {Array.from({ length: cols }).map((_, colIndex) => (
          <div 
            key={colIndex} 
            className="h-4 bg-[var(--color-bg-tertiary)] rounded flex-1"
            style={{ opacity: 1 - rowIndex * 0.1 }}
          />
        ))}
      </div>
    ))}
  </div>
);

export const SkeletonList: React.FC<{ items?: number }> = ({ items = 3 }) => (
  <div className="space-y-3 animate-pulse">
    {Array.from({ length: items }).map((_, i) => (
      <div key={i} className="flex items-center gap-3 p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
        <div className="w-10 h-10 rounded-lg bg-[var(--color-bg-hover)]" />
        <div className="flex-1">
          <div className="h-4 w-24 bg-[var(--color-bg-hover)] rounded mb-2" />
          <div className="h-3 w-32 bg-[var(--color-bg-hover)] rounded" />
        </div>
      </div>
    ))}
  </div>
);

export default LoadingState;
