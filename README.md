# NGX Trader

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14.2-black.svg)](https://nextjs.org/)
[![Tests](https://img.shields.io/badge/Tests-550+-brightgreen.svg)](#testing)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Nigerian Stock Exchange Investment Intelligence Platform**

An institutional-grade decision-support system for the Nigerian equity market. NGX Trader combines real-time market data, fundamental quality scoring, probabilistic signal analysis, portfolio tracking, and strict safety governance to help investors identify high-quality Nigerian stocks.

> **NGX Trader is a decision-support system, not financial advice. It does not execute trades.**

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Quality Scanner](#quality-scanner)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Configuration](#configuration)
- [Contributing](#contributing)

---

## Features

| Feature | Description |
|---------|-------------|
| **Quality Scanner** | Fundamental-driven stock ranking with explainability, reproducibility, and health monitoring |
| **Live Market Data** | Real-time prices from NGN Market with multi-source validation |
| **Probabilistic Signals** | Bias expressed as probability, never certainty; NO_TRADE is first-class |
| **Market Regime Detection** | Trending, mean-reverting, volatile, low-liquidity classification |
| **Portfolio Tracking** | Holdings, performance, decomposition, timeseries, summary with currency conversion |
| **Corporate Actions** | Dividends, splits, bonuses with Total Return Index (TRI) computation |
| **Audit Trail** | Full provenance, signal queryability, and compliance logging |

---

## Quick Start

### Prerequisites

- **Python** 3.11+
- **Node.js** 18+

### 1. Clone & Setup Backend

```bash
git clone https://github.com/Tadekola/nse_trader.git
cd nse_trader/backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Copy environment config
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux

# Seed data and run scanner
python seed_real.py

# Start backend
uvicorn app.main:app --port 8000
```

### 2. Setup Frontend

```bash
cd frontend-next
npm install

# Create .env.local
echo BACKEND_URL=http://127.0.0.1:8000 > .env.local

npm run dev
```

### 3. Access the Application

| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:3000 |
| **API Docs** | http://localhost:8000/docs |

---

## Architecture

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy (async), Alembic |
| **Frontend** | Next.js 14.2, TypeScript, Tailwind CSS (terminal dark theme) |
| **Database** | PostgreSQL (production) / SQLite (local dev) |
| **Containerization** | Docker / Docker Compose |

### Project Structure

```
nse_trader/
├── backend/
│   ├── app/
│   │   ├── api/v1/               # REST API routers
│   │   │   ├── scanner.py        #   Quality scanner (9 endpoints)
│   │   │   ├── stocks.py         #   Stock data & recommendations
│   │   │   ├── market.py         #   Live market data
│   │   │   ├── portfolios.py     #   Portfolio management (10 endpoints)
│   │   │   ├── total_return.py   #   TRI & corporate actions
│   │   │   ├── audit.py          #   Audit trail & CSV export
│   │   │   ├── health.py         #   System health
│   │   │   └── recommendations.py
│   │   ├── scanner/              # Quality Scanner engine
│   │   │   ├── universe.py       #   Liquidity-based universe builder
│   │   │   ├── quality_scorer.py #   Multi-factor scoring engine
│   │   │   ├── explainer.py      #   Score explainability
│   │   │   ├── derived_metrics.py#   Financial ratio computation
│   │   │   ├── workflow.py       #   End-to-end scan orchestration
│   │   │   └── scheduled.py      #   Automated daily/weekly scans
│   │   ├── services/             # Business logic
│   │   │   ├── portfolio.py      #   Portfolio service
│   │   │   ├── performance.py    #   Performance engine
│   │   │   ├── summary.py        #   Dashboard summary
│   │   │   ├── timeseries.py     #   Chart-ready series
│   │   │   ├── tri_engine.py     #   Total Return Index
│   │   │   └── ...               #   Signal, regime, validation services
│   │   ├── db/                   # SQLAlchemy models & engine
│   │   ├── middleware/           # Provenance enforcement
│   │   ├── cli/                  # CLI tools (fundamentals, scanner, scheduler)
│   │   └── main.py              # FastAPI application
│   ├── data/                     # Fundamentals CSV data
│   ├── tests/                    # 550+ unit tests
│   ├── seed_real.py              # Production data seeding pipeline
│   └── seed_demo.py              # Demo data for UI testing
├── frontend-next/                # Next.js frontend (primary)
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx          # Top Picks (landing)
│   │   │   ├── screener/         # Stock Screener
│   │   │   ├── scanner/          # Quality Scanner (5 pages)
│   │   │   ├── portfolios/       # Portfolio management
│   │   │   └── audit/            # Audit trail
│   │   ├── api/                  # Typed API clients
│   │   └── components/           # Shared UI components
│   └── next.config.mjs           # API proxy config
├── frontend/                     # Legacy Vite/React frontend
├── docs/                         # Planning & audit documentation
├── docker-compose.yml
└── README.md
```

---

## Quality Scanner

The NGX Quality Scanner is a fundamental-driven stock ranking system that scores all liquid NGX stocks across multiple dimensions.

### How It Works

1. **Universe Selection** — Top N stocks by liquidity (avg daily value from OHLCV data)
2. **Fundamentals Fetch** — Revenue, net income, assets, equity, cash flow, debt from `FundamentalsPeriodic`
3. **Derived Metrics** — ROE, ROIC, margins, stability scores, red flags computed automatically
4. **Multi-Factor Scoring** — Profitability, cash flow, balance sheet, stability, shareholder return, liquidity
5. **Guardrails & Penalties** — Confidence penalties for stale/insufficient data; red flags for negative metrics
6. **Explainability** — Every score is fully decomposable into sub-scores, raw metrics, and reasons

### Scanner Pages

| Page | Route | Description |
|------|-------|-------------|
| **Dashboard** | `/scanner` | Health badge, hero stats, score distribution, tier breakdown, top/bottom 5 |
| **Quality Table** | `/scanner/table` | 14-column sortable table with tier/score/symbol filters |
| **Explain** | `/scanner/explain/[symbol]` | Full score breakdown, guardrails, confidence penalty |
| **Scan Runs** | `/scanner/runs` | Historical scan run list |
| **Run Detail** | `/scanner/runs/[id]` | Detailed results for a specific scan run |

### Scoring Tiers

| Tier | Score Range | Meaning |
|------|-------------|---------|
| **HIGH** | 70–100 | Strong fundamentals across all dimensions |
| **MEDIUM** | 40–70 | Acceptable with some weaknesses |
| **LOW** | 0–40 | Significant fundamental concerns |
| **INSUFFICIENT** | — | Not enough data to score reliably |

### CLI Tools

```bash
# Import fundamentals from CSV
python -m app.cli.fundamentals import-csv --csv data/fundamentals_ngx.csv

# Compute derived metrics
python -m app.cli.fundamentals compute-derived --as-of 2026-02-23

# Run scanner
python -m app.cli.scanner run --force

# Scheduled scan
python -m app.scanner --freq daily --universe top_liquid_50
```

---

## API Reference

### Scanner API (9 endpoints)

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/scanner/dashboard` | Dashboard summary with health, tiers, top/bottom performers |
| `GET /api/v1/scanner/table` | Sortable, filterable results table with pagination |
| `GET /api/v1/scanner/explain/{symbol}` | Detailed score explanation for a symbol |
| `GET /api/v1/scanner/health` | Scanner health status and anomaly detection |
| `GET /api/v1/scanner/universe` | Current universe members and liquidity scores |
| `GET /api/v1/scanner/runs` | List of scan runs |
| `GET /api/v1/scanner/runs/{id}` | Scan run detail |
| `GET /api/v1/scanner/runs/{id}/results` | Results for a specific run |
| `GET /api/v1/scanner/buylist` | Top-ranked stocks meeting quality criteria |

### Market API

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/market/summary` | ASI, volume, breadth, regime in one call |
| `GET /api/v1/market/snapshot` | ASI, volume, deals, market cap |
| `GET /api/v1/market/trending` | Top gainers & losers |
| `GET /api/v1/market/regime` | Market regime classification |

### Stock API

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/stocks` | List all tracked stocks |
| `GET /api/v1/stocks/{symbol}` | Stock detail with indicators |
| `GET /api/v1/recommendations/buy` | Buy recommendations by horizon |
| `GET /api/v1/recommendations/top` | Top-ranked recommendations |

### Portfolio API (10 endpoints)

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/portfolios` | Create portfolio |
| `GET /api/v1/portfolios` | List portfolios |
| `GET /api/v1/portfolios/{id}` | Portfolio detail |
| `POST /api/v1/portfolios/{id}/transactions` | Add transaction |
| `GET /api/v1/portfolios/{id}/transactions` | List transactions |
| `GET /api/v1/portfolios/{id}/holdings` | Current holdings |
| `GET /api/v1/portfolios/{id}/performance` | Return metrics |
| `GET /api/v1/portfolios/{id}/decomposition` | Return decomposition |
| `GET /api/v1/portfolios/{id}/summary` | Dashboard summary |
| `GET /api/v1/portfolios/{id}/timeseries` | Chart-ready time series |

### Total Return API

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/tickers/{symbol}/total-return` | Adjusted close + TRI series |
| `GET /api/v1/tickers/{symbol}/corporate-actions` | Dividends, splits, bonuses |
| `GET /api/v1/tickers/{symbol}/price-discontinuities` | Detect >40% moves |

### Audit API

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/audit/events` | Filterable audit events |
| `GET /api/v1/audit/signals` | Signal audit trail |
| `GET /api/v1/audit/no-trade` | NO_TRADE decisions |
| CSV variants | `/events/csv`, `/signals/csv`, `/no-trade/csv` |

---

## Testing

```bash
cd backend

# Run all tests
python -m pytest tests/ -v

# Scanner tests only (295 tests)
python -m pytest tests/test_beta_security.py tests/test_universe_pipeline.py \
  tests/test_fundamentals.py tests/test_quality_scorer.py \
  tests/test_scanner_workflow.py tests/test_scanner_api.py \
  tests/test_explainability.py tests/test_reproducibility.py \
  tests/test_scanner_health.py tests/test_scanner_scheduled.py \
  tests/test_scanner_dashboard.py -v

# Portfolio tests (252 tests)
python -m pytest tests/test_portfolio_core.py tests/test_portfolio_api.py \
  tests/test_performance_engine.py tests/test_decomposition.py \
  tests/test_summary_service.py tests/test_timeseries_service.py -v

# Frontend build verification
cd ../frontend-next && npx next build
```

### Test Coverage Summary

| Subsystem | Tests |
|-----------|-------|
| Quality Scanner (v1–v1.2) | 295 |
| Portfolio & Performance | 252 |
| Audit & Provenance | 49 |
| Corporate Actions & TRI | 57 |
| **Total** | **550+** |

---

## Configuration

### Backend (`backend/.env`)

```env
ENV=dev                                              # dev | production
DATABASE_URL=sqlite+aiosqlite:///./nse_trader_dev.db # SQLite for local dev
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:3000
```

### Frontend (`frontend-next/.env.local`)

```env
BACKEND_URL=http://127.0.0.1:8000
```

### Docker

```bash
docker-compose up --build
```

---

## Disclaimer

> NGX Trader provides informational and analytical insights only. It does **not** constitute financial advice, investment recommendations, or an offer to buy or sell securities. Always conduct your own research and consult qualified professionals before making investment decisions.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Write tests for new features
4. Ensure all tests pass
5. Open a Pull Request

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- **NGN Market** — Primary market data source
- **Nigerian Exchange Group (NGX)** — Market infrastructure

---

<p align="center">
  <strong>Built for the Nigerian market. Designed for trust.</strong><br>
  Version 3.0
</p>