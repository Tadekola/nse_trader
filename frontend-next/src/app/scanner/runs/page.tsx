"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listScanRuns } from "@/api/scanner-client";
import type { ScanRunListResponse } from "@/api/scanner-types";
import { fmtDate, fmtTimestamp } from "@/api/utils";

export default function ScanRunsPage() {
  const [data, setData] = useState<ScanRunListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listScanRuns({ limit: 50 })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-terminal-dim font-mono animate-pulse">Loading scan runs…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card p-6">
        <p className="text-terminal-red font-mono">Error: {error}</p>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-terminal-text">Scan Runs</h1>
          <p className="text-sm text-terminal-dim font-mono mt-0.5">{data.total} runs</p>
        </div>
        <Link href="/scanner" className="btn-ghost text-xs">← Dashboard</Link>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-terminal-border">
            <tr>
              <th className="table-header">ID</th>
              <th className="table-header">As-of Date</th>
              <th className="table-header">Universe</th>
              <th className="table-header">Scanned</th>
              <th className="table-header">Ranked</th>
              <th className="table-header">Created</th>
              <th className="table-header">Top 5</th>
            </tr>
          </thead>
          <tbody>
            {data.runs.map((run) => {
              const summary = run.summary as Record<string, unknown> | null;
              const top5 = (summary?.top_5 as string[]) || [];
              const avgQ = summary?.avg_quality as number | undefined;

              return (
                <tr key={run.id} className="table-row">
                  <td className="table-cell">
                    <Link
                      href={`/scanner/runs/${run.id}`}
                      className="text-terminal-accent hover:underline font-medium"
                    >
                      #{run.id}
                    </Link>
                  </td>
                  <td className="table-cell">{fmtDate(run.as_of_date)}</td>
                  <td className="table-cell text-terminal-muted">{run.universe_name}</td>
                  <td className="table-cell text-terminal-muted">{run.symbols_scanned}</td>
                  <td className="table-cell text-terminal-muted">{run.symbols_ranked}</td>
                  <td className="table-cell text-terminal-dim text-xs">{fmtTimestamp(run.created_at)}</td>
                  <td className="table-cell text-terminal-dim text-xs">
                    {top5.slice(0, 3).join(", ")}
                    {top5.length > 3 ? "…" : ""}
                    {avgQ != null && (
                      <span className="ml-2 text-terminal-accent">avg {avgQ}</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
