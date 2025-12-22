/**
 * Professional Empty State Component
 * 
 * Replaces amateur giant icons with compact, informative empty states.
 * Always provides context about WHY it's empty and WHAT to do.
 */

import React from 'react';

type EmptyStateVariant = 'default' | 'signals' | 'watchlist' | 'search' | 'error';

interface EmptyStateProps {
  variant?: EmptyStateVariant;
  title: string;
  description?: string;
  reason?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  compact?: boolean;
}

const variantIcons: Record<EmptyStateVariant, React.ReactNode> = {
  default: (
    <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
    </svg>
  ),
  signals: (
    <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
    </svg>
  ),
  watchlist: (
    <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
    </svg>
  ),
  search: (
    <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  ),
  error: (
    <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
};

const EmptyState: React.FC<EmptyStateProps> = ({
  variant = 'default',
  title,
  description,
  reason,
  action,
  compact = false,
}) => {
  if (compact) {
    return (
      <div className="flex items-center gap-3 py-4 px-3">
        <div className="w-8 h-8 rounded-lg bg-[var(--color-bg-tertiary)] flex items-center justify-center text-[var(--color-text-tertiary)]">
          {variantIcons[variant]}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-[var(--color-text-secondary)]">{title}</p>
          {reason && (
            <p className="text-xs text-[var(--color-text-tertiary)] mt-0.5">{reason}</p>
          )}
        </div>
        {action && (
          <button
            onClick={action.onClick}
            className="text-xs text-[var(--color-accent-primary)] hover:underline"
          >
            {action.label}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="py-8 px-4 text-center">
      <div className="w-10 h-10 mx-auto mb-3 rounded-lg bg-[var(--color-bg-tertiary)] flex items-center justify-center text-[var(--color-text-tertiary)]">
        {variantIcons[variant]}
      </div>
      
      <h3 className="text-sm font-medium text-[var(--color-text-secondary)] mb-1">
        {title}
      </h3>
      
      {description && (
        <p className="text-xs text-[var(--color-text-tertiary)] max-w-xs mx-auto">
          {description}
        </p>
      )}
      
      {reason && (
        <p className="text-xs text-[var(--color-text-tertiary)] mt-2 px-3 py-1.5 bg-[var(--color-bg-tertiary)] rounded inline-block">
          {reason}
        </p>
      )}
      
      {action && (
        <button
          onClick={action.onClick}
          className="mt-3 px-4 py-1.5 text-xs font-medium text-[var(--color-accent-primary)] hover:bg-[var(--color-accent-primary)]/10 rounded-lg transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
};

export default EmptyState;
