"use client";

import { useEffect, useState } from "react";
import { listAuditEvents } from "@/api/client";
import type { AuditList } from "@/api/types";
import { fmtTimestamp, cn } from "@/api/utils";

export default function AuditPage() {
  const [events, setEvents] = useState<AuditList | null>(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    component: "",
    eventType: "",
    level: "",
  });
  const [page, setPage] = useState(0);
  const LIMIT = 50;

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const data = await listAuditEvents({
          component: filters.component || undefined,
          eventType: filters.eventType || undefined,
          level: filters.level || undefined,
          limit: LIMIT,
          offset: page * LIMIT,
        });
        setEvents(data);
      } catch (err) {
        console.error("Failed to load audit events:", err);
      }
      setLoading(false);
    }
    load();
  }, [filters, page]);

  const levelColor = (level: string) => {
    switch (level.toUpperCase()) {
      case "ERROR": return "badge-red";
      case "WARN": return "badge-amber";
      case "INFO": return "badge-blue";
      default: return "badge-dim";
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-terminal-text">Audit Trail</h1>
          <p className="text-xs text-terminal-dim mt-0.5">
            {events?.total ?? 0} events
          </p>
        </div>
        <div className="flex gap-2">
          <a
            href="/api/v1/audit/events/csv"
            className="btn-ghost text-xs"
            download
          >
            Export CSV
          </a>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 items-center">
        <select
          value={filters.component}
          onChange={(e) => { setFilters((f) => ({ ...f, component: e.target.value })); setPage(0); }}
          className="bg-terminal-surface border border-terminal-border rounded px-2 py-1.5 text-xs font-mono text-terminal-text"
        >
          <option value="">All Components</option>
          <option value="portfolio">portfolio</option>
          <option value="ingestion">ingestion</option>
          <option value="scheduler">scheduler</option>
          <option value="provenance">provenance</option>
        </select>
        <select
          value={filters.level}
          onChange={(e) => { setFilters((f) => ({ ...f, level: e.target.value })); setPage(0); }}
          className="bg-terminal-surface border border-terminal-border rounded px-2 py-1.5 text-xs font-mono text-terminal-text"
        >
          <option value="">All Levels</option>
          <option value="INFO">INFO</option>
          <option value="WARN">WARN</option>
          <option value="ERROR">ERROR</option>
        </select>
        <input
          type="text"
          placeholder="Event type..."
          value={filters.eventType}
          onChange={(e) => { setFilters((f) => ({ ...f, eventType: e.target.value })); setPage(0); }}
          className="bg-terminal-surface border border-terminal-border rounded px-2 py-1.5 text-xs font-mono text-terminal-text w-48 placeholder-terminal-dim"
        />
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-terminal-border">
              <th className="table-header w-36">Timestamp</th>
              <th className="table-header w-16">Level</th>
              <th className="table-header w-24">Component</th>
              <th className="table-header w-40">Event Type</th>
              <th className="table-header">Message</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="table-cell text-center text-terminal-dim py-12">
                  Loading...
                </td>
              </tr>
            ) : !events || events.data.length === 0 ? (
              <tr>
                <td colSpan={5} className="table-cell text-center text-terminal-dim py-12">
                  No audit events found
                </td>
              </tr>
            ) : (
              events.data.map((evt) => (
                <tr key={evt.id} className="table-row">
                  <td className="table-cell text-xs text-terminal-dim">
                    {fmtTimestamp(evt.ts)}
                  </td>
                  <td className="table-cell">
                    <span className={cn("badge", levelColor(evt.level))}>
                      {evt.level}
                    </span>
                  </td>
                  <td className="table-cell text-xs">{evt.component}</td>
                  <td className="table-cell text-xs font-medium text-terminal-accent">
                    {evt.event_type}
                  </td>
                  <td className="table-cell text-xs text-terminal-muted truncate max-w-md">
                    {evt.message}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {events && events.total > LIMIT && (
        <div className="flex items-center justify-between text-xs font-mono text-terminal-dim">
          <span>
            Showing {page * LIMIT + 1}–{Math.min((page + 1) * LIMIT, events.total)} of {events.total}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="btn-ghost disabled:opacity-30"
            >
              ← Prev
            </button>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={(page + 1) * LIMIT >= events.total}
              className="btn-ghost disabled:opacity-30"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
