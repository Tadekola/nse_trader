"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/api/client";
import type { HealthResponse } from "@/api/types";
import { cn, qualityColor, healthBgColor } from "@/api/utils";

export function StatusBar() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function poll() {
      try {
        const data = await getHealth();
        if (mounted) { setHealth(data); setError(false); }
      } catch {
        if (mounted) setError(true);
      }
    }
    poll();
    const id = setInterval(poll, 30_000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  const status = health?.overall_status ?? (error ? "UNKNOWN" : "LOADING");

  return (
    <header className="sticky top-0 z-30 h-10 bg-terminal-bg/80 backdrop-blur border-b border-terminal-border flex items-center px-4 gap-4">
      {/* System status */}
      <div className={cn(
        "flex items-center gap-2 px-2.5 py-0.5 rounded text-xs font-mono font-medium border",
        status === "OK" ? healthBgColor("OK") :
        status === "DEGRADED" ? healthBgColor("DEGRADED") :
        status === "SAFE_MODE" ? healthBgColor("SAFE_MODE") :
        "bg-terminal-surface border-terminal-border",
      )}>
        <span className={cn(
          "w-1.5 h-1.5 rounded-full",
          status === "OK" ? "bg-terminal-green animate-pulse" :
          status === "DEGRADED" ? "bg-terminal-amber animate-pulse" :
          status === "SAFE_MODE" ? "bg-terminal-red animate-pulse" :
          "bg-terminal-dim",
        )} />
        <span className={qualityColor(status)}>{status}</span>
      </div>

      {/* Source pills */}
      {health?.sources && (
        <div className="flex items-center gap-1.5 overflow-x-auto">
          {health.sources.map((src) => (
            <span
              key={src.source}
              className={cn(
                "text-[10px] font-mono px-1.5 py-0.5 rounded",
                src.circuit_state === "CLOSED"
                  ? "text-terminal-green/80 bg-terminal-green/5"
                  : src.circuit_state === "HALF_OPEN"
                  ? "text-terminal-amber/80 bg-terminal-amber/5"
                  : "text-terminal-red/80 bg-terminal-red/5",
              )}
            >
              {src.source}
            </span>
          ))}
        </div>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Error indicator */}
      {error && (
        <span className="text-[10px] font-mono text-terminal-red">
          API UNREACHABLE
        </span>
      )}
    </header>
  );
}
