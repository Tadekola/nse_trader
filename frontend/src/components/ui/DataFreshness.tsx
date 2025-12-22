/**
 * DataFreshness - Trust signal showing data recency
 * 
 * Critical for institutional credibility - users need to know
 * when data was last updated and from what source.
 */

import React from 'react';

interface DataFreshnessProps {
  timestamp: string | Date | null;
  source?: string;
  showSource?: boolean;
  compact?: boolean;
}

const DataFreshness: React.FC<DataFreshnessProps> = ({
  timestamp,
  source,
  showSource = true,
  compact = false,
}) => {
  const getTimeAgo = (ts: string | Date): string => {
    const date = typeof ts === 'string' ? new Date(ts) : ts;
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);

    if (diffSec < 60) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHour < 24) return `${diffHour}h ago`;
    return date.toLocaleDateString();
  };

  const getFreshnessStatus = (ts: string | Date): { 
    status: 'fresh' | 'stale' | 'old'; 
    color: string;
  } => {
    const date = typeof ts === 'string' ? new Date(ts) : ts;
    const now = new Date();
    const diffMin = Math.floor((now.getTime() - date.getTime()) / 60000);

    if (diffMin < 5) return { status: 'fresh', color: 'text-emerald-400' };
    if (diffMin < 30) return { status: 'stale', color: 'text-amber-400' };
    return { status: 'old', color: 'text-red-400' };
  };

  if (!timestamp) {
    return (
      <span className="text-xs text-[var(--color-text-tertiary)]">
        No data
      </span>
    );
  }

  const freshness = getFreshnessStatus(timestamp);
  const timeAgo = getTimeAgo(timestamp);

  if (compact) {
    return (
      <div className="flex items-center gap-1.5 text-xs">
        <span className={`w-1.5 h-1.5 rounded-full ${
          freshness.status === 'fresh' ? 'bg-emerald-400 animate-pulse' :
          freshness.status === 'stale' ? 'bg-amber-400' : 'bg-red-400'
        }`} />
        <span className="text-[var(--color-text-tertiary)] font-mono">{timeAgo}</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 text-xs">
      <div className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full ${
          freshness.status === 'fresh' ? 'bg-emerald-400 animate-pulse' :
          freshness.status === 'stale' ? 'bg-amber-400' : 'bg-red-400'
        }`} />
        <span className={freshness.color}>
          {freshness.status === 'fresh' ? 'Live' : 
           freshness.status === 'stale' ? 'Delayed' : 'Outdated'}
        </span>
      </div>
      <span className="text-[var(--color-text-tertiary)] font-mono">{timeAgo}</span>
      {showSource && source && (
        <>
          <span className="text-[var(--color-text-tertiary)]">•</span>
          <span className="text-[var(--color-text-tertiary)]">{source}</span>
        </>
      )}
    </div>
  );
};

export default DataFreshness;
