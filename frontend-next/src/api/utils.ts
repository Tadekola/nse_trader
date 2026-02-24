/**
 * Formatting utilities for the terminal UI.
 * Consistent number/date/currency formatting across all components.
 */

// ── Currency ────────────────────────────────────────────────────────

const NGN = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const NGN_PRECISE = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function fmtCurrency(
  value: number | null | undefined,
  mode: string = "NGN",
  precise = false,
): string {
  if (value == null) return "—";
  if (mode === "USD") return USD.format(value);
  return precise ? NGN_PRECISE.format(value) : NGN.format(value);
}

// ── Numbers ─────────────────────────────────────────────────────────

const COMPACT = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

export function fmtCompact(value: number | null | undefined): string {
  if (value == null) return "—";
  return COMPACT.format(value);
}

export function fmtNum(value: number | null | undefined, decimals = 2): string {
  if (value == null) return "—";
  return value.toFixed(decimals);
}

export function fmtShares(value: number | null | undefined): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en").format(Math.round(value));
}

// ── Percentages ─────────────────────────────────────────────────────

export function fmtPct(value: number | null | undefined, decimals = 2): string {
  if (value == null) return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}

export function fmtPctSigned(value: number | null | undefined, decimals = 2): string {
  if (value == null) return "—";
  const pct = value * 100;
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(decimals)}%`;
}

// ── Dates ───────────────────────────────────────────────────────────

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return iso.slice(0, 10); // YYYY-MM-DD
}

export function fmtDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "2-digit" });
}

export function fmtTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── Color helpers ───────────────────────────────────────────────────

export function returnColor(value: number | null | undefined): string {
  if (value == null) return "text-terminal-muted";
  if (value > 0) return "text-terminal-green";
  if (value < 0) return "text-terminal-red";
  return "text-terminal-muted";
}

export function qualityColor(quality: string): string {
  switch (quality) {
    case "FULL":
    case "OK":
      return "text-terminal-green";
    case "DEGRADED":
    case "RECOVERING":
      return "text-terminal-amber";
    case "SAFE_MODE":
      return "text-terminal-red";
    default:
      return "text-terminal-dim";
  }
}

export function healthBgColor(status: string): string {
  switch (status) {
    case "OK":
      return "bg-terminal-green/10 border-terminal-green/30";
    case "RECOVERING":
      return "bg-terminal-amber/10 border-terminal-amber/30";
    case "DEGRADED":
      return "bg-terminal-amber/10 border-terminal-amber/30";
    case "SAFE_MODE":
      return "bg-terminal-red/10 border-terminal-red/30";
    default:
      return "bg-terminal-surface border-terminal-border";
  }
}

// ── Misc ────────────────────────────────────────────────────────────

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}
