/**
 * MainLayout - Primary application shell
 * 
 * Provides:
 * - Fixed header with navigation
 * - Sidebar for quick access
 * - Main content area with proper grid
 * - Status bar for system health
 */

import React, { useState } from 'react';

interface MainLayoutProps {
  children: React.ReactNode;
  onNavigate?: (page: string) => void;
  currentPage?: string;
}

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  href?: string;
}

const MainLayout: React.FC<MainLayoutProps> = ({ children, onNavigate, currentPage }) => {
  const [activeNav, setActiveNav] = useState(currentPage || 'dashboard');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const navItems: NavItem[] = [
    { 
      id: 'dashboard', 
      label: 'Dashboard',
      icon: (
        <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        </svg>
      )
    },
    { 
      id: 'screener', 
      label: 'Stock Screener',
      icon: (
        <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
        </svg>
      )
    },
    { 
      id: 'recommendations', 
      label: 'Signals',
      icon: (
        <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
      )
    },
    { 
      id: 'watchlist', 
      label: 'Watchlist',
      icon: (
        <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
        </svg>
      )
    },
    { 
      id: 'learn', 
      label: 'Learn',
      icon: (
        <svg width="20" height="20" className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
        </svg>
      )
    },
  ];

  return (
    <div className="min-h-screen bg-[var(--color-bg-primary)] text-[var(--color-text-primary)]">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 h-14 bg-[var(--color-bg-secondary)] border-b border-[var(--color-border-subtle)] z-50">
        <div className="flex items-center justify-between h-full px-4">
          {/* Logo & Brand */}
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              className="p-2 rounded-md hover:bg-[var(--color-bg-hover)] transition-colors"
            >
              <svg width="16" height="16" className="w-4 h-4 text-[var(--color-text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-[var(--color-accent-primary)] flex items-center justify-center">
                <span className="text-white font-bold text-sm">N</span>
              </div>
              <span className="font-semibold text-lg tracking-tight">NSE Trader</span>
            </div>
          </div>

          {/* Center - Search */}
          <div className="hidden md:flex flex-1 max-w-md mx-8">
            <div className="relative w-full">
              <svg width="16" height="16" className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-text-tertiary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                placeholder="Search stocks... (e.g., GTCO, Zenith Bank)"
                className="w-full pl-10 pr-4 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border-subtle)] rounded-lg text-sm text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)] focus:outline-none focus:border-[var(--color-accent-primary)] transition-colors"
              />
              <kbd className="absolute right-3 top-1/2 -translate-y-1/2 hidden sm:inline-flex items-center px-2 py-0.5 text-xs text-[var(--color-text-tertiary)] bg-[var(--color-bg-hover)] rounded border border-[var(--color-border-subtle)]">
                ⌘K
              </kbd>
            </div>
          </div>

          {/* Right - Status & Actions */}
          <div className="flex items-center gap-4">
            {/* Market Status */}
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--color-bg-tertiary)]">
              <span className="w-2 h-2 rounded-full bg-[var(--color-positive)] animate-pulse"></span>
              <span className="text-xs font-medium text-[var(--color-text-secondary)]">Market Open</span>
            </div>
            
            {/* Data Freshness */}
            <div className="text-xs text-[var(--color-text-tertiary)]">
              <span className="hidden lg:inline">Updated: </span>
              <span className="font-mono">Just now</span>
            </div>

            {/* Settings */}
            <button className="p-2 rounded-md hover:bg-[var(--color-bg-hover)] transition-colors">
              <svg width="16" height="16" className="w-4 h-4 text-[var(--color-text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      {/* Sidebar */}
      <aside className={`fixed top-14 left-0 bottom-0 bg-[var(--color-bg-secondary)] border-r border-[var(--color-border-subtle)] transition-all duration-300 z-40 ${sidebarCollapsed ? 'w-16' : 'w-56'}`}>
        <nav className="flex flex-col h-full py-4">
          {/* Main Navigation */}
          <div className="flex-1 px-3 space-y-1">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  setActiveNav(item.id);
                  onNavigate?.(item.id);
                }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  (currentPage || activeNav) === item.id
                    ? 'bg-[var(--color-accent-primary)] text-white'
                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text-primary)]'
                }`}
              >
                {item.icon}
                {!sidebarCollapsed && <span>{item.label}</span>}
              </button>
            ))}
          </div>

          {/* Bottom Section */}
          <div className="px-3 pt-4 border-t border-[var(--color-border-subtle)]">
            {!sidebarCollapsed && (
              <div className="px-3 py-2 rounded-lg bg-[var(--color-bg-tertiary)]">
                <p className="text-xs text-[var(--color-text-tertiary)] mb-1">Experience Level</p>
                <select className="w-full bg-transparent text-sm text-[var(--color-text-primary)] focus:outline-none cursor-pointer">
                  <option value="beginner">Beginner</option>
                  <option value="intermediate">Intermediate</option>
                  <option value="advanced">Advanced</option>
                </select>
              </div>
            )}
          </div>
        </nav>
      </aside>

      {/* Main Content */}
      <main className={`pt-14 min-h-screen transition-all duration-300 ${sidebarCollapsed ? 'pl-16' : 'pl-56'}`}>
        <div className="p-6">
          {children}
        </div>
      </main>

      {/* Status Bar (Footer) */}
      <footer className={`fixed bottom-0 right-0 h-6 bg-[var(--color-bg-secondary)] border-t border-[var(--color-border-subtle)] flex items-center px-4 text-xs transition-all duration-300 ${sidebarCollapsed ? 'left-16' : 'left-56'}`}>
        <div className="flex items-center gap-4 text-[var(--color-text-tertiary)]">
          <span>NGX</span>
          <span className="text-[var(--color-positive)]">●</span>
          <span>TradingView</span>
          <span className="text-[var(--color-positive)]">●</span>
          <span className="ml-auto font-mono">v2.0.0</span>
        </div>
      </footer>
    </div>
  );
};

export default MainLayout;
