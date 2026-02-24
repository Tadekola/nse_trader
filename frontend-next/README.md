# NSE Trader — Next.js Frontend

Institutional-grade Nigerian stock portfolio analytics dashboard with a terminal-style UI.

## Stack

- **Framework**: Next.js 14.2 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS with custom terminal theme
- **Charts**: TradingView Lightweight Charts
- **Fonts**: JetBrains Mono (monospace), Inter (sans)

## Pages

| Route | Description |
|---|---|
| `/` | Dashboard — portfolios table with summary metrics, reporting toggle (NGN/USD/REAL_NGN) |
| `/portfolios/[id]` | Portfolio detail — summary cards, timeseries chart, return windows, decomposition, holdings grid, transactions, quality flags |
| `/audit` | Audit trail — filterable event log with pagination and CSV export |

## Setup

```bash
npm install
npm run dev       # http://localhost:3000
```

Requires the backend running at `http://localhost:8000`. API calls are proxied via Next.js rewrites (`/api/*` → backend).

## Architecture

```
src/
├── api/
│   ├── types.ts     # TypeScript interfaces matching backend contracts
│   ├── client.ts    # Typed fetch functions for all 10+ endpoints
│   └── utils.ts     # Formatting (currency, %, dates) + color helpers
├── app/
│   ├── layout.tsx   # Root layout with sidebar + status bar
│   ├── page.tsx     # Dashboard (portfolios table)
│   ├── audit/       # Audit trail page
│   └── portfolios/
│       └── [id]/    # Portfolio detail page
└── components/
    ├── charts/      # TradingView Lightweight Charts wrapper
    └── layout/      # Sidebar, StatusBar
```

## API Endpoints Used

- `GET /api/v1/health/sources` — system health for status bar
- `GET /api/v1/portfolios` — list all portfolios
- `GET /api/v1/portfolios/{id}/summary` — valuation, returns, concentration, quality
- `GET /api/v1/portfolios/{id}/timeseries` — chart-ready daily series
- `GET /api/v1/portfolios/{id}/decomposition` — return decomposition (USD/REAL_NGN)
- `GET /api/v1/portfolios/{id}/transactions` — recent transactions
- `GET /api/v1/audit/events` — audit event log

## Reporting Modes

All financial pages support switching between:
- **NGN** — Nominal Naira
- **USD** — US Dollar (via FX conversion)
- **REAL_NGN** — Inflation-adjusted Naira (via CPI deflator)
