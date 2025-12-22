/**
 * ExplainerTooltip - Beginner-friendly contextual help
 * 
 * Provides plain-English explanations for financial terms
 * without being condescending or intrusive.
 */

import React, { useState } from 'react';

interface ExplainerTooltipProps {
  term: string;
  explanation: string;
  learnMoreLink?: string;
  children: React.ReactNode;
}

const ExplainerTooltip: React.FC<ExplainerTooltipProps> = ({
  term,
  explanation,
  learnMoreLink,
  children,
}) => {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <span className="relative inline-flex">
      <span
        className="cursor-help border-b border-dashed border-[var(--color-text-tertiary)]"
        onMouseEnter={() => setIsVisible(true)}
        onMouseLeave={() => setIsVisible(false)}
      >
        {children}
      </span>
      
      {isVisible && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50">
          <div className="bg-[var(--color-bg-tertiary)] border border-[var(--color-border-default)] rounded-lg shadow-lg p-3 w-64">
            <div className="font-medium text-sm text-[var(--color-text-primary)] mb-1">
              {term}
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
              {explanation}
            </p>
            {learnMoreLink && (
              <a 
                href={learnMoreLink}
                className="inline-block mt-2 text-xs text-[var(--color-accent-primary)] hover:underline"
              >
                Learn more →
              </a>
            )}
          </div>
          {/* Arrow */}
          <div className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-l-8 border-r-8 border-t-8 border-l-transparent border-r-transparent border-t-[var(--color-border-default)]" />
        </div>
      )}
    </span>
  );
};

export default ExplainerTooltip;
