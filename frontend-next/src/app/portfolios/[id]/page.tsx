"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  getSummary,
  getTimeseries,
  getDecomposition,
  listTransactions,
} from "@/api/client";
import type {
  SummaryResponse,
  TimeseriesResponse,
  DecompositionResponse,
  TransactionList,
  ReportingMode,
} from "@/api/types";
import {
  fmtCurrency,
  fmtPct,
  fmtPctSigned,
  fmtDate,
  fmtShares,
  fmtNum,
  returnColor,
  qualityColor,
  cn,
} from "@/api/utils";
import { TimeseriesChart } from "@/components/charts/timeseries-chart";

export default function PortfolioDetailPage() {
  const params = useParams();
  const id = Number(params.id);

  const [reporting, setReporting] = useState<ReportingMode>("NGN");
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [timeseries, setTimeseries] = useState<TimeseriesResponse | null>(null);
  const [decomposition, setDecomposition] = useState<DecompositionResponse | null>(null);
  const [transactions, setTransactions] = useState<TransactionList | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, ts, txs] = await Promise.all([
        getSummary(id, reporting),
        getTimeseries(id, reporting),
        listTransactions(id, { limit: 20 }),
      ]);
      setSummary(s);
      setTimeseries(ts);
      setTransactions(txs);

      // Decomposition only for USD/REAL_NGN
      if (reporting !== "NGN") {
        const d = await getDecomposition(id, reporting);
        setDecomposition(d);
      } else {
        setDecomposition(null);
      }
    } catch (err) {
      console.error("Failed to load portfolio:", err);
    }
    setLoading(false);
  }, [id, reporting]);

  useEffect(() => { load(); }, [load]);

  const MODES: ReportingMode[] = ["NGN", "USD", "REAL_NGN"];

  if (loading && !summary) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-terminal-dim font-mono">Loading portfolio {id}...</span>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-terminal-red font-mono">Portfolio {id} not found or has no data</span>
      </div>
    );
  }

  const s = summary;
  const ytd = s.returns.find((r) => r.label === "YTD");
  const oneY = s.returns.find((r) => r.label === "1Y");
  const threeY = s.returns.find((r) => r.label === "3Y");
  const inception = s.returns.find((r) => r.label === "SINCE_INCEPTION");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-terminal-dim hover:text-terminal-text text-sm">
            ← Back
          </Link>
          <h1 className="text-lg font-semibold text-terminal-text">
            Portfolio #{id}
          </h1>
          <span className={cn(
            "badge",
            s.quality.overall_quality === "FULL" ? "badge-green" : "badge-amber",
          )}>
            {s.quality.overall_quality}
          </span>
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

      {/* Summary Cards Row */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <StatCard
          label={`Value (${reporting})`}
          value={fmtCurrency(reporting === "NGN" ? s.value_ngn : s.value_reporting, reporting)}
          sub={reporting !== "NGN" ? `₦${fmtCurrency(s.value_ngn, "NGN")}` : undefined}
        />
        <StatCard
          label="YTD Return"
          value={ytd?.available ? fmtPctSigned(ytd.value) : "—"}
          color={returnColor(ytd?.value)}
        />
        <StatCard
          label="Since Inception"
          value={inception?.available ? fmtPctSigned(inception.value) : "—"}
          color={returnColor(inception?.value)}
          sub={inception?.annualized != null ? `Ann: ${fmtPctSigned(inception.annualized)}` : undefined}
        />
        <StatCard
          label="Current Drawdown"
          value={s.current_drawdown != null ? fmtPct(s.current_drawdown) : "—"}
          color="text-terminal-red"
        />
        <StatCard
          label="Positions"
          value={String(s.concentration.num_positions)}
          sub={`HHI: ${fmtNum(s.concentration.hhi, 0)}`}
        />
      </div>

      {/* Chart */}
      {timeseries && timeseries.num_points > 0 && (
        <div className="card">
          <div className="card-header">
            <h2 className="text-sm font-semibold text-terminal-text">
              Portfolio Value ({reporting})
            </h2>
            <span className="text-[10px] text-terminal-dim font-mono">
              {timeseries.num_points} trading days
            </span>
          </div>
          <div className="p-4" style={{ height: 360 }}>
            <TimeseriesChart data={timeseries} reporting={reporting} />
          </div>
        </div>
      )}

      {/* Returns + Decomposition Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Returns */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-sm font-semibold text-terminal-text">Return Windows</h2>
          </div>
          <div className="card-body">
            <table className="w-full">
              <thead>
                <tr className="border-b border-terminal-border">
                  <th className="table-header">Period</th>
                  <th className="table-header text-right">Return</th>
                  <th className="table-header text-right">Annualized</th>
                  <th className="table-header text-right">Period</th>
                </tr>
              </thead>
              <tbody>
                {[ytd, oneY, threeY, inception].map((w) =>
                  w ? (
                    <tr key={w.label} className="table-row">
                      <td className="table-cell font-medium">{w.label}</td>
                      <td className={cn("table-cell text-right", returnColor(w.value))}>
                        {w.available ? fmtPctSigned(w.value) : "—"}
                      </td>
                      <td className={cn("table-cell text-right", returnColor(w.annualized))}>
                        {w.annualized != null ? fmtPctSigned(w.annualized) : "—"}
                      </td>
                      <td className="table-cell text-right text-terminal-dim text-xs">
                        {w.start_date && w.end_date
                          ? `${fmtDate(w.start_date)} → ${fmtDate(w.end_date)}`
                          : "—"}
                      </td>
                    </tr>
                  ) : null,
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Decomposition */}
        {decomposition && (
          <div className="card">
            <div className="card-header">
              <h2 className="text-sm font-semibold text-terminal-text">
                Return Decomposition ({reporting})
              </h2>
            </div>
            <div className="card-body space-y-3">
              <DecompBar label="Total" value={decomposition.summary.total_return} />
              <DecompBar label="Equity" value={decomposition.summary.equity_component} color="text-terminal-accent" />
              {decomposition.summary.fx_component != null && (
                <DecompBar label="FX" value={decomposition.summary.fx_component} color="text-terminal-cyan" />
              )}
              {decomposition.summary.inflation_component != null && (
                <DecompBar label="Inflation" value={decomposition.summary.inflation_component} color="text-terminal-amber" />
              )}
              <p className="text-[10px] text-terminal-dim mt-2 font-mono">
                Multiplicative: (1+total) = (1+equity) × (1+fx) or (1+nominal)/(1+inflation)
              </p>
            </div>
          </div>
        )}

        {/* Concentration (show when no decomposition) */}
        {!decomposition && (
          <div className="card">
            <div className="card-header">
              <h2 className="text-sm font-semibold text-terminal-text">Concentration</h2>
            </div>
            <div className="card-body space-y-3">
              <div className="flex justify-between">
                <span className="text-sm text-terminal-dim">HHI Index</span>
                <span className="font-mono text-sm">{fmtNum(s.concentration.hhi, 0)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-terminal-dim">Largest Position</span>
                <span className="font-mono text-sm">
                  {s.concentration.max_position_symbol ?? "—"}{" "}
                  ({fmtPct(s.concentration.max_position_weight)})
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-terminal-dim">Cash Weight</span>
                <span className="font-mono text-sm">
                  {s.value_ngn > 0 ? fmtPct(s.cash_ngn / s.value_ngn) : "—"}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Holdings Table */}
      <div className="card">
        <div className="card-header">
          <h2 className="text-sm font-semibold text-terminal-text">
            Top Holdings
          </h2>
          <span className="text-[10px] text-terminal-dim font-mono">
            {s.top_holdings.length} positions
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-terminal-border">
                <th className="table-header">Symbol</th>
                <th className="table-header text-right">Shares</th>
                <th className="table-header text-right">Avg Cost</th>
                <th className="table-header text-right">Market Value</th>
                <th className="table-header text-right">Weight</th>
                <th className="table-header text-right">Gain/Loss</th>
                <th className="table-header text-center">TRI Quality</th>
              </tr>
            </thead>
            <tbody>
              {s.top_holdings.map((h) => (
                <tr key={h.symbol} className="table-row">
                  <td className="table-cell font-medium text-terminal-accent">{h.symbol}</td>
                  <td className="table-cell text-right">{fmtShares(h.shares)}</td>
                  <td className="table-cell text-right">{fmtCurrency(h.avg_cost_ngn, "NGN", true)}</td>
                  <td className="table-cell text-right">
                    {fmtCurrency(
                      reporting === "NGN" ? h.market_value_ngn : h.market_value_reporting,
                      reporting,
                    )}
                  </td>
                  <td className="table-cell text-right">{fmtPct(h.weight)}</td>
                  <td className={cn("table-cell text-right", returnColor(h.gain_loss_pct / 100))}>
                    {h.gain_loss_pct >= 0 ? "+" : ""}{h.gain_loss_pct.toFixed(1)}%
                  </td>
                  <td className="table-cell text-center">
                    <span className={cn(
                      "badge",
                      h.tri_quality === "FULL" ? "badge-green" :
                      h.tri_quality === "PRICE_ONLY" ? "badge-amber" : "badge-dim",
                    )}>
                      {h.tri_quality}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recent Transactions */}
      {transactions && transactions.data.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h2 className="text-sm font-semibold text-terminal-text">Recent Transactions</h2>
            <span className="text-[10px] text-terminal-dim font-mono">
              {transactions.total} total
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-terminal-border">
                  <th className="table-header">Date</th>
                  <th className="table-header">Type</th>
                  <th className="table-header">Symbol</th>
                  <th className="table-header text-right">Qty</th>
                  <th className="table-header text-right">Price</th>
                  <th className="table-header text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {transactions.data.map((tx) => (
                  <tr key={tx.id} className="table-row">
                    <td className="table-cell text-xs">{fmtDate(tx.ts)}</td>
                    <td className="table-cell">
                      <span className={cn(
                        "badge",
                        tx.tx_type === "BUY" ? "badge-green" :
                        tx.tx_type === "SELL" ? "badge-red" :
                        tx.tx_type === "DIVIDEND" ? "badge-blue" : "badge-dim",
                      )}>
                        {tx.tx_type}
                      </span>
                    </td>
                    <td className="table-cell">{tx.symbol ?? "—"}</td>
                    <td className="table-cell text-right">{tx.quantity ? fmtShares(tx.quantity) : "—"}</td>
                    <td className="table-cell text-right">{tx.price_ngn ? fmtCurrency(tx.price_ngn, "NGN", true) : "—"}</td>
                    <td className="table-cell text-right">{fmtCurrency(tx.amount_ngn, "NGN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Quality + Freshness Footer */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card card-body">
          <h3 className="text-xs font-medium text-terminal-dim uppercase tracking-wider mb-2">Quality Flags</h3>
          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <span className="text-terminal-dim">Data:</span>
            <span className={qualityColor(s.quality.data_mode === "TRI_FULL" ? "OK" : "DEGRADED")}>
              {s.quality.data_mode}
            </span>
            <span className="text-terminal-dim">FX:</span>
            <span className={qualityColor(s.quality.fx_mode === "FX_FULL" ? "OK" : s.quality.fx_mode === "FX_MISSING" ? "DEGRADED" : "OK")}>
              {s.quality.fx_mode}
            </span>
            <span className="text-terminal-dim">CPI:</span>
            <span className={qualityColor(s.quality.inflation_mode === "CPI_FULL" ? "OK" : s.quality.inflation_mode === "CPI_MISSING" ? "DEGRADED" : "OK")}>
              {s.quality.inflation_mode}
            </span>
          </div>
        </div>
        <div className="card card-body">
          <h3 className="text-xs font-medium text-terminal-dim uppercase tracking-wider mb-2">Data Freshness</h3>
          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <span className="text-terminal-dim">Last Price:</span>
            <span>{fmtDate(s.freshness.last_price_date)}</span>
            <span className="text-terminal-dim">Last FX:</span>
            <span>{fmtDate(s.freshness.last_fx_date)}</span>
            <span className="text-terminal-dim">Last CPI:</span>
            <span>{fmtDate(s.freshness.last_cpi_date)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="card card-body">
      <p className="stat-label">{label}</p>
      <p className={cn("stat-value mt-1", color)}>{value}</p>
      {sub && <p className="text-[10px] text-terminal-dim mt-0.5 font-mono">{sub}</p>}
    </div>
  );
}

function DecompBar({
  label,
  value,
  color,
}: {
  label: string;
  value: number | null;
  color?: string;
}) {
  if (value == null) return null;
  const pct = value * 100;
  const width = Math.min(Math.abs(pct) * 3, 100); // scale for visibility

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-terminal-dim w-16 text-right">{label}</span>
      <div className="flex-1 h-5 bg-terminal-border/30 rounded overflow-hidden relative">
        <div
          className={cn(
            "h-full rounded",
            value >= 0 ? "bg-terminal-green/40" : "bg-terminal-red/40",
          )}
          style={{ width: `${width}%` }}
        />
        <span className={cn(
          "absolute inset-0 flex items-center px-2 text-xs font-mono",
          color ?? (value >= 0 ? "text-terminal-green" : "text-terminal-red"),
        )}>
          {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
        </span>
      </div>
    </div>
  );
}
