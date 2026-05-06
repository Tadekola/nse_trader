"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listPortfolios, getSummary, createPortfolio, deletePortfolio } from "@/api/client";
import type { Portfolio, SummaryResponse, ReportingMode } from "@/api/types";
import { fmtCurrency, fmtPctSigned, fmtDate, returnColor, cn } from "@/api/utils";

interface PortfolioRow extends Portfolio {
  summary?: SummaryResponse | null;
  loading: boolean;
}

function CreatePortfolioModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (p: Portfolio) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [currency, setCurrency] = useState("NGN");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const p = await createPortfolio({
        name: name.trim(),
        description: description.trim() || undefined,
        base_currency: currency,
      });
      onCreated(p);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create portfolio");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-terminal-bg border border-terminal-border rounded-lg w-full max-w-md p-6 shadow-xl">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-terminal-text">New Portfolio</h2>
          <button onClick={onClose} className="text-terminal-dim hover:text-terminal-text text-xl leading-none">×</button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-terminal-dim mb-1">Portfolio Name *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. My NGX Portfolio"
              className="w-full bg-terminal-surface border border-terminal-border rounded px-3 py-2 text-sm text-terminal-text placeholder-terminal-dim focus:outline-none focus:border-terminal-accent"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-terminal-dim mb-1">Description (optional)</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Long-term dividend stocks"
              className="w-full bg-terminal-surface border border-terminal-border rounded px-3 py-2 text-sm text-terminal-text placeholder-terminal-dim focus:outline-none focus:border-terminal-accent"
            />
          </div>
          <div>
            <label className="block text-xs text-terminal-dim mb-1">Base Currency</label>
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              className="w-full bg-terminal-surface border border-terminal-border rounded px-3 py-2 text-sm text-terminal-text focus:outline-none focus:border-terminal-accent"
            >
              <option value="NGN">NGN — Nigerian Naira</option>
              <option value="USD">USD — US Dollar</option>
            </select>
          </div>
          {error && (
            <p className="text-xs text-terminal-red">{error}</p>
          )}
          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 text-sm border border-terminal-border rounded text-terminal-dim hover:text-terminal-text transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !name.trim()}
              className="flex-1 px-4 py-2 text-sm bg-terminal-accent text-black font-medium rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {submitting ? "Creating..." : "Create Portfolio"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function PortfoliosPage() {
  const [portfolios, setPortfolios] = useState<PortfolioRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [reporting, setReporting] = useState<ReportingMode>("NGN");
  const [showCreate, setShowCreate] = useState(false);

  async function loadPortfolios(mode: ReportingMode) {
    setLoading(true);
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
        list.data.map((p) => getSummary(p.id, mode)),
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

  useEffect(() => {
    loadPortfolios(reporting);
  }, [reporting]);

  function handleCreated(p: Portfolio) {
    setShowCreate(false);
    setPortfolios((prev) => [{ ...p, summary: null, loading: false }, ...prev]);
  }

  async function handleDelete(id: number, name: string) {
    if (!window.confirm(`Delete portfolio "${name}" and all of its transactions?`)) {
      return;
    }
    await deletePortfolio(id);
    setPortfolios((prev) => prev.filter((row) => row.id !== id));
  }

  const MODES: ReportingMode[] = ["NGN", "USD", "REAL_NGN"];

  return (
    <div className="space-y-6">
      {showCreate && (
        <CreatePortfolioModal
          onClose={() => setShowCreate(false)}
          onCreated={handleCreated}
        />
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-terminal-text">Portfolios</h1>
          <p className="text-xs text-terminal-dim mt-0.5">
            {portfolios.length} portfolio{portfolios.length !== 1 ? "s" : ""} tracked
          </p>
        </div>
        <div className="flex items-center gap-3">
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
          <button
            onClick={() => setShowCreate(true)}
            className="px-3 py-1.5 text-xs bg-terminal-accent text-black font-medium rounded hover:opacity-90 transition-opacity"
          >
            + New Portfolio
          </button>
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
              <th className="table-header text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={9} className="table-cell text-center text-terminal-dim py-12">
                  Loading portfolios...
                </td>
              </tr>
            ) : portfolios.length === 0 ? (
              <tr>
                <td colSpan={9} className="table-cell text-center py-16">
                  <p className="text-terminal-dim text-sm">No portfolios yet</p>
                  <button
                    onClick={() => setShowCreate(true)}
                    className="mt-3 px-4 py-2 text-sm bg-terminal-accent text-black font-medium rounded hover:opacity-90 transition-opacity"
                  >
                    + Create your first portfolio
                  </button>
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
                    <td className="table-cell text-right">
                      <button
                        onClick={() => handleDelete(row.id, row.name)}
                        className="px-2 py-1 text-[10px] border border-terminal-red/40 text-terminal-red rounded hover:bg-terminal-red/10 transition-colors"
                      >
                        Delete
                      </button>
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
