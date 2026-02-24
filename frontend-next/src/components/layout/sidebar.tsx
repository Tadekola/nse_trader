"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/api/utils";

const MAIN_NAV = [
  { href: "/", label: "Top Picks", icon: "★" },
  { href: "/screener", label: "Screener", icon: "◫" },
] as const;

const SCANNER_NAV = [
  { href: "/scanner", label: "Dashboard", icon: "◉" },
  { href: "/scanner/table", label: "Quality Table", icon: "▤" },
  { href: "/scanner/runs", label: "Scan Runs", icon: "▶" },
] as const;

const SECONDARY_NAV = [
  { href: "/portfolios", label: "Portfolios", icon: "◈" },
  { href: "/audit", label: "Audit Trail", icon: "⊞" },
] as const;

export function Sidebar() {
  const pathname = usePathname();

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  function navLink(item: { href: string; label: string; icon: string }) {
    return (
      <Link
        key={item.href}
        href={item.href}
        className={cn(
          "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
          isActive(item.href)
            ? "bg-terminal-accent/15 text-terminal-accent"
            : "text-terminal-muted hover:text-terminal-text hover:bg-terminal-border/30",
        )}
      >
        <span className="text-base font-mono">{item.icon}</span>
        {item.label}
      </Link>
    );
  }

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-56 bg-terminal-surface border-r border-terminal-border flex flex-col z-40">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-terminal-border">
        <div className="flex items-center gap-2">
          <span className="text-terminal-green font-mono font-bold text-lg">NGX</span>
          <span className="text-terminal-dim font-mono text-xs">TRADER</span>
        </div>
        <p className="text-[10px] text-terminal-dim mt-0.5 font-mono">
          Stock Intelligence
        </p>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {MAIN_NAV.map(navLink)}

        <div className="pt-3 pb-1 px-3">
          <span className="text-[10px] text-terminal-dim font-mono uppercase tracking-wider">Scanner</span>
        </div>
        {SCANNER_NAV.map(navLink)}

        <div className="pt-3 pb-1 px-3">
          <span className="text-[10px] text-terminal-dim font-mono uppercase tracking-wider">Tools</span>
        </div>
        {SECONDARY_NAV.map(navLink)}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-terminal-border">
        <p className="text-[10px] text-terminal-dim font-mono">
          v2.0 · Nigerian Stock Exchange
        </p>
      </div>
    </aside>
  );
}
