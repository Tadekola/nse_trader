"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listPortfolios, getSummary } from "@/api/client";
import type { Portfolio, SummaryResponse, ReportingMode } from "@/api/types";
import { fmtCurrency, fmtPctSigned, fmtDate, returnColor, cn } from "@/api/utils";

interface PortfolioRow extends Portfolio {
  summary?: SummaryResponse | null;
  loading: boolean;
}

export default function PortfoliosPage() {
  const [portfolios, setPortfolios] = useState<PortfolioRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [reporting, setReporting] = useState<ReportingMode>("NGN");

  useEffect(() => {
    async function load() {
      try {
        const list = await listPortfolios();
        const rows: PortfolioRow[] = list.data.map((p) => ({
          ...p,
          summary: null,
          loading: true,
        }));
        setPortfolios(rows);
        setLoading(false);

        const summaries = await Promise.allSettled(
          list.data.map((p) => getSummary(p.id, reporting)),
        );

        setPortfolios((prev) =>
          prev.map((row, i) => ({
            ...row,
            summary:
              summaries[i].status === "fulfilled"
                ? summaries[i].value
                : null,
            loading: false,
          })),
        );
      } catch {
        setLoading(false);
      }
    }
    load();
  }, [reporting]);

  const MODES: ReportingMode[] = ["NGN", "USD", "REAL_NGN"];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-terminal-text">Portfolios</h1>
          <p className="text-xs text-terminal-dim mt-0.5">
            {portfolios.length} portfolio{portfolios.length !== 1 ? "s" : ""} tracked
          </p>
        </div>
        <div className="toggle-group">
          {MODES.map((m) => (
            <button
              key={m}
              onClick={() => setReporting(m)}
              className={cn("toggle-item", reporting === m && "toggle-item-active")}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-terminal-border">
              <th className="table-header">Portfolio</th>
              <th className="table-header text-right">Value ({reporting})</th>
              <th className="table-header text-right">YTD</th>
              <th className="table-header text-right">1Y</th>
              <th className="table-header text-right">Since Inception</th>
              <th className="table-header text-right">Drawdown</th>
              <th className="table-header text-right">Positions</th>
              <th className="table-header text-center">Quality</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="table-cell text-center text-terminal-dim py-12">
                  Loading portfolios...
                </td>
              </tr>
            ) : portfolios.length === 0 ? (
              <tr>
                <td colSpan={8} className="table-cell text-center text-terminal-dim py-12">
                  No portfolios yet
                </td>
              </tr>
            ) : (
              portfolios.map((row) => {
                const s = row.summary;
                const ytd = s?.returns.find((r) => r.label === "YTD");
                const oneY = s?.returns.find((r) => r.label === "1Y");
                const inception = s?.returns.find((r) => r.label === "SINCE_INCEPTION");

                return (
                  <tr key={row.id} className="table-row">
                    <td className="table-cell">
                      <Link
                        href={`/portfolios/${row.id}`}
                        className="text-terminal-accent hover:underline font-medium"
                      >
                        {row.name}
                      </Link>
                      <span className="block text-[10px] text-terminal-dim mt-0.5">
                        {row.base_currency} · Created {fmtDate(row.created_at)}
                      </span>
                    </td>
                    <td className="table-cell text-right">
                      {row.loading ? "..." : s ? fmtCurrency(
                        reporting === "NGN" ? s.value_ngn : s.value_reporting, reporting,
                      ) : "—"}
                    </td>
                    <td className={cn("table-cell text-right", returnColor(ytd?.value))}>
                      {row.loading ? "..." : ytd?.available ? fmtPctSigned(ytd.value) : "—"}
                    </td>
                    <td className={cn("table-cell text-right", returnColor(oneY?.value))}>
                      {row.loading ? "..." : oneY?.available ? fmtPctSigned(oneY.value) : "—"}
                    </td>
                    <td className={cn("table-cell text-right", returnColor(inception?.value))}>
                      {row.loading ? "..." : inception?.available ? fmtPctSigned(inception.value) : "—"}
                    </td>
                    <td className="table-cell text-right text-terminal-red">
                      {row.loading ? "..." : s?.current_drawdown != null
                        ? `${(s.current_drawdown * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td className="table-cell text-right">
                      {row.loading ? "..." : s?.concentration.num_positions ?? "—"}
                    </td>
                    <td className="table-cell text-center">
                      {row.loading ? "..." : s ? (
                        <span className={cn("badge",
                          s.quality.overall_quality === "FULL" ? "badge-green" : "badge-amber"
                        )}>
                          {s.quality.overall_quality}
                        </span>
                      ) : <span className="badge badge-dim">N/A</span>}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
