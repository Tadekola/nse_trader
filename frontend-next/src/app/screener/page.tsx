"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listStocks, getStockSectors } from "@/api/client";
import type { Stock } from "@/api/types";
import { cn } from "@/api/utils";

type SortKey = "symbol" | "price" | "change_percent" | "volume" | "market_cap" | "pe_ratio" | "dividend_yield";
type SortDir = "asc" | "desc";

export default function ScreenerPage() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [sectors, setSectors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sectorFilter, setSectorFilter] = useState("");
  const [liquidityFilter, setLiquidityFilter] = useState("");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("change_percent");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // Load sectors once
  useEffect(() => {
    async function loadSectors() {
      try {
        const res = await getStockSectors();
        setSectors(res.sectors || []);
      } catch {
        // optional
      }
    }
    loadSectors();
  }, []);

  // Load stocks on filter change
  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await listStocks({
          sector: sectorFilter || undefined,
          liquidity: liquidityFilter || undefined,
        });
        setStocks(res.data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load stocks");
        setStocks([]);
      }
      setLoading(false);
    }
    load();
  }, [sectorFilter, liquidityFilter]);

  // Filter + sort
  const filtered = stocks
    .filter((s) => {
      if (!search) return true;
      const q = search.toLowerCase();
      return s.symbol.toLowerCase().includes(q) || s.name.toLowerCase().includes(q);
    })
    .sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      if (typeof av === "string" && typeof bv === "string") {
        return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      return sortDir === "asc" ? Number(av) - Number(bv) : Number(bv) - Number(av);
    });

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("desc"); }
  }

  function sortArrow(key: SortKey) {
    if (sortKey !== key) return "";
    return sortDir === "asc" ? " ▲" : " ▼";
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-terminal-text">Stock Screener</h1>
        <p className="text-xs text-terminal-dim mt-0.5">
          {filtered.length} of {stocks.length} stocks · Click any stock for full analysis
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <input
          type="text"
          placeholder="Search symbol or name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-terminal-surface border border-terminal-border rounded px-3 py-1.5 text-xs font-mono text-terminal-text w-56 placeholder-terminal-dim"
        />
        <select
          value={sectorFilter}
          onChange={(e) => setSectorFilter(e.target.value)}
          className="bg-terminal-surface border border-terminal-border rounded px-2 py-1.5 text-xs font-mono text-terminal-text"
        >
          <option value="">All Sectors</option>
          {sectors.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={liquidityFilter}
          onChange={(e) => setLiquidityFilter(e.target.value)}
          className="bg-terminal-surface border border-terminal-border rounded px-2 py-1.5 text-xs font-mono text-terminal-text"
        >
          <option value="">All Liquidity</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {/* Table */}
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-terminal-border">
              <th className="table-header cursor-pointer select-none" onClick={() => toggleSort("symbol")}>
                Symbol{sortArrow("symbol")}
              </th>
              <th className="table-header">Name</th>
              <th className="table-header text-right cursor-pointer select-none" onClick={() => toggleSort("price")}>
                Price{sortArrow("price")}
              </th>
              <th className="table-header text-right cursor-pointer select-none" onClick={() => toggleSort("change_percent")}>
                Change{sortArrow("change_percent")}
              </th>
              <th className="table-header text-right cursor-pointer select-none" onClick={() => toggleSort("volume")}>
                Volume{sortArrow("volume")}
              </th>
              <th className="table-header text-right cursor-pointer select-none" onClick={() => toggleSort("market_cap")}>
                Mkt Cap{sortArrow("market_cap")}
              </th>
              <th className="table-header text-right cursor-pointer select-none" onClick={() => toggleSort("pe_ratio")}>
                P/E{sortArrow("pe_ratio")}
              </th>
              <th className="table-header text-right cursor-pointer select-none" onClick={() => toggleSort("dividend_yield")}>
                Div Yield{sortArrow("dividend_yield")}
              </th>
              <th className="table-header text-center">Liquidity</th>
              <th className="table-header text-center">Sector</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={10} className="table-cell text-center text-terminal-dim py-12">
                  Loading market data...
                </td>
              </tr>
            ) : error ? (
              <tr>
                <td colSpan={10} className="table-cell text-center text-terminal-red py-12">
                  {error}
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={10} className="table-cell text-center text-terminal-dim py-12">
                  No stocks match your filters
                </td>
              </tr>
            ) : (
              filtered.map((s) => (
                <tr key={s.symbol} className="table-row">
                  <td className="table-cell">
                    <Link
                      href={`/stocks/${s.symbol}`}
                      className="text-terminal-accent hover:underline font-semibold"
                    >
                      {s.symbol}
                    </Link>
                  </td>
                  <td className="table-cell text-terminal-muted text-[11px] truncate max-w-[200px]">
                    {s.name}
                  </td>
                  <td className="table-cell text-right font-mono">
                    ₦{s.price.toLocaleString("en", { minimumFractionDigits: 2 })}
                  </td>
                  <td className={cn(
                    "table-cell text-right font-mono",
                    (s.change_percent ?? 0) > 0 ? "text-terminal-green" :
                    (s.change_percent ?? 0) < 0 ? "text-terminal-red" : "text-terminal-muted"
                  )}>
                    {s.change_percent != null
                      ? `${s.change_percent >= 0 ? "+" : ""}${s.change_percent.toFixed(2)}%`
                      : "—"}
                  </td>
                  <td className="table-cell text-right font-mono text-terminal-muted">
                    {s.volume != null
                      ? s.volume.toLocaleString("en", { notation: "compact" } as Intl.NumberFormatOptions)
                      : "—"}
                  </td>
                  <td className="table-cell text-right font-mono text-terminal-muted">
                    {s.market_cap != null
                      ? `₦${(s.market_cap / 1e9).toFixed(1)}B`
                      : "—"}
                  </td>
                  <td className="table-cell text-right font-mono text-terminal-muted">
                    {s.pe_ratio != null ? s.pe_ratio.toFixed(1) : "—"}
                  </td>
                  <td className="table-cell text-right font-mono text-terminal-muted">
                    {s.dividend_yield != null ? `${(s.dividend_yield * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td className="table-cell text-center">
                    <span className={cn(
                      "badge text-[10px]",
                      s.liquidity_tier === "high" ? "badge-green" :
                      s.liquidity_tier === "medium" ? "badge-amber" :
                      s.liquidity_tier === "low" ? "badge-red" : "badge-dim"
                    )}>
                      {s.liquidity_tier || "—"}
                    </span>
                  </td>
                  <td className="table-cell text-center text-[10px] text-terminal-dim">
                    {s.sector || "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
