# NGX Trader

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14+-black.svg)](https://nextjs.org/)
[![Tests](https://img.shields.io/badge/Tests-550+-brightgreen.svg)](#testing)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Nigerian Stock Exchange Investment Intelligence Platform**
FastAPI · Next.js · PostgreSQL/SQLite · Alembic · 550+ tests · MIT

NGX Trader is an institutional-grade **decision-support** platform for the Nigerian equity market (NGX). It combines **market data**, **fundamental quality scoring**, **total return (dividends/splits)**, **portfolio tracking**, and **strict safety governance** to help investors identify high-quality Nigerian stocks.

> **Disclaimer:** NGX Trader provides informational and analytical insights only. It is **not** financial advice and does **not** execute trades.

---

## Table of Contents

- [Features](#features)
- [Quick Start (Docker)](#quick-start-docker)
- [Quick Start (Local Dev)](#quick-start-local-dev)
- [Architecture](#architecture)
- [Quality Scanner](#quality-scanner)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Configuration](#configuration)
- [Security](#security)
- [Data Sources & Provenance](#data-sources--provenance)
- [Contributing](#contributing)
- [License](#license)

---

## Features

| Feature | Description |
|---------|-------------|
| **Quality Scanner** | Fundamental-driven stock ranking with explainability, reproducibility, automation, and health monitoring |
| **Live Market Data** | Market prices from NGN Market with multi-source validation (NGX Official List PDFs) and safe-mode resilience |
| **Probabilistic Signals** | Bias expressed as probability, never certainty; `NO_TRADE` is first-class |
| **Market Regime Detection** | Trending, mean-reverting, volatile, low-liquidity classification |
| **Portfolio Tracking** | Holdings, performance, decomposition, time series, summary with NGN/USD/Real NGN reporting |
| **Corporate Actions + TRI** | Dividends, splits, bonuses with Total Return Index computation |
| **FX + Inflation Awareness** | Nigeria currency reality: NGN nominal vs USD vs Real NGN (CPI) reporting + decomposition |
| **Audit Trail** | Full provenance, queryable audit logs, compliance-style traceability |

---

## Quick Start (Docker)

> Recommended if you want a one-command environment with PostgreSQL.

```bash
git clone https://github.com/Tadekola/nse_trader.git
cd nse_trader

# Build & start services
docker-compose up --build
```

Then open:

| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:3000 |
| **API docs (Swagger)** | http://localhost:8000/docs |

If your compose setup includes automatic migrations, you're done. If not, run migrations once:

```bash
docker-compose exec backend alembic upgrade head
```

---

## Quick Start (Local Dev)

### Prerequisites

- **Python** 3.11+
- **Node.js** 18+

### 1) Backend

```bash
cd backend

# Create venv
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install deps
pip install -r requirements.txt

# Configure env
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux

# Seed (choose one)
python seed_demo.py          # demo data for UI testing
python seed_real.py          # production-like seeding pipeline (may require network)

# Start API
uvicorn app.main:app --port 8000
```

### 2) Frontend

```bash
cd ../frontend-next
npm install

# Configure frontend env
echo BACKEND_URL=http://127.0.0.1:8000 > .env.local

# Start dev server
npm run dev
```

Open:

| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:3000 |
| **API docs** | http://localhost:8000/docs |

---

## Architecture

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy (async), Alembic |
| **Frontend** | Next.js 14+, TypeScript, Tailwind CSS (terminal dark theme) |
| **Database** | PostgreSQL (production) / SQLite (local dev) |
| **Containerization** | Docker / Docker Compose |

### Project Structure (high level)

```
nse_trader/
├── backend/
│   ├── app/
│   │   ├── api/v1/               # REST API routers
│   │   ├── scanner/              # Quality Scanner engine
│   │   ├── services/             # Business logic
│   │   ├── db/                   # SQLAlchemy models & engine
│   │   ├── middleware/           # Provenance enforcement
│   │   ├── cli/                  # CLI tools
│   │   └── main.py              # FastAPI app
│   ├── data/                     # Fundamentals CSV data
│   ├── tests/                    # 550+ unit tests
│   ├── seed_real.py              # Production-ish seeding
│   └── seed_demo.py              # Demo seeding
├── frontend-next/                # Next.js frontend (primary)
├── frontend/                     # Legacy Vite/React frontend
├── docs/                         # Planning & audit docs
├── docker-compose.yml
└── README.md
```

---

## Quality Scanner

The NGX Quality Scanner ranks liquid NGX stocks using fundamentals, liquidity, and governance guardrails.

### How It Works

1. **Universe Selection** — Top N stocks by liquidity (avg daily value from OHLCV)
2. **Fundamentals Fetch** — Imported into `FundamentalsPeriodic`
3. **Derived Metrics** — ROE/ROIC, margins, stability, red flags (`FundamentalsDerived`)
4. **Multi-Factor Scoring** — Profitability, cash flow, balance sheet, stability, shareholder return, liquidity
5. **Guardrails & Penalties** — Confidence penalties for stale/insufficient data
6. **Explainability** — Full breakdown: raw → winsorized → percentile → score
7. **Monitoring** — Coverage, staleness, anomaly thresholds, actionable remediation hints

### Scanner Pages (Next.js)

| Page | Route | Description |
|------|-------|-------------|
| **Dashboard** | `/scanner` | Health badge, hero stats, distribution, tier breakdown, top/bottom |
| **Quality Table** | `/scanner/table` | Sortable table with filters + pagination |
| **Explain** | `/scanner/explain/[symbol]` | Full score explanation + guardrails + penalties |
| **Scan Runs** | `/scanner/runs` | Historical run list |
| **Run Detail** | `/scanner/runs/[id]` | Results for a specific run |

---

## API Reference

### Scanner API (9 endpoints)

- `GET /api/v1/scanner/dashboard`
- `GET /api/v1/scanner/table`
- `GET /api/v1/scanner/explain/{symbol}`
- `GET /api/v1/scanner/health`
- `GET /api/v1/scanner/universe`
- `GET /api/v1/scanner/runs`
- `GET /api/v1/scanner/runs/{id}`
- `GET /api/v1/scanner/runs/{id}/results`
- `GET /api/v1/scanner/buylist`

### Portfolio API (10 endpoints)

- `POST /api/v1/portfolios`
- `GET /api/v1/portfolios`
- `GET /api/v1/portfolios/{id}`
- `POST /api/v1/portfolios/{id}/transactions`
- `GET /api/v1/portfolios/{id}/transactions`
- `GET /api/v1/portfolios/{id}/holdings`
- `GET /api/v1/portfolios/{id}/performance`
- `GET /api/v1/portfolios/{id}/decomposition`
- `GET /api/v1/portfolios/{id}/summary`
- `GET /api/v1/portfolios/{id}/timeseries`

### Total Return API

- `GET /api/v1/tickers/{symbol}/total-return`
- `GET /api/v1/tickers/{symbol}/corporate-actions`
- `GET /api/v1/tickers/{symbol}/price-discontinuities`

### Audit API (+ CSV variants)

- `GET /api/v1/audit/events` and `/events/csv`
- `GET /api/v1/audit/signals` and `/signals/csv`
- `GET /api/v1/audit/no-trade` and `/no-trade/csv`

---

## Testing

```bash
cd backend

# Run all tests
python -m pytest tests/ -v
```

Scanner tests only:

```bash
python -m pytest tests/test_beta_security.py tests/test_universe_pipeline.py \
  tests/test_fundamentals.py tests/test_quality_scorer.py \
  tests/test_scanner_workflow.py tests/test_scanner_api.py \
  tests/test_explainability.py tests/test_reproducibility.py \
  tests/test_scanner_health.py tests/test_scanner_scheduled.py \
  tests/test_scanner_dashboard.py -v
```

Portfolio tests:

```bash
python -m pytest tests/test_portfolio_core.py tests/test_portfolio_api.py \
  tests/test_performance_engine.py tests/test_decomposition.py \
  tests/test_summary_service.py tests/test_timeseries_service.py -v
```

Frontend build verification:

```bash
cd ../frontend-next
npx next build
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

---

## Security

- **API key auth** protects scanner endpoints (beta-style control).
- **CORS whitelist** blocks untrusted origins.
- **Rate limiting** (slowapi) prevents abuse.
- **Next.js server-side proxy** so API keys never appear in the browser.

---

## Data Sources & Provenance

- **NGN Market** — primary market data source
- **NGX Official Daily List PDFs** — reconciliation/canonical close
- **CSV imports** — fundamentals, FX, CPI (MVP correctness-first; web providers can be added later)

Every computation is provenance-tagged and audit-logged. Degraded/missing data is never silent.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Write tests for new features
4. Ensure all tests pass
5. Open a Pull Request

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- **NGN Market** — market data source
- **Nigerian Exchange Group (NGX)** — market infrastructure

---

<p align="center">
  <strong>Built for the Nigerian market. Designed for trust.</strong><br>
  Version 3.0
</p>