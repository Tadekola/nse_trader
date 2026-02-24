# NSE Trader — Principal Systems Audit Report

**Auditor**: Claude Opus 4.6 (Principal Systems Auditor + Quant Risk Officer)
**Date**: 2026-02-23
**Scope**: Full codebase — backend/, frontend/, frontend-next/, config, migrations, tests

---

# A) CAPABILITIES & FEATURE INVENTORY

## A1) Data Ingestion & Sources

### OHLCV Sources (Multi-tier fallback chain)

| Tier | Provider | File | Method |
|------|----------|------|--------|
| 1 | NGX Official List PDF | `backend/app/data/sources/ngx_official_list.py` | PDF download + parse via pdfplumber |
| 1 | ngnmarket.com | `backend/app/market_data/providers/ngnmarket_provider.py` | HTML scraping via httpx |
| 2 | Apt Securities | `backend/app/market_data/providers/apt_securities_provider.py` | Web scraping |
| 2 | Kwayisi.com | `backend/app/market_data/providers/kwayisi_provider.py` | Web scraping (has rate limiting) |
| 3 | Simulated | `backend/app/market_data/providers/simulated_provider.py` | Random data generation (flagged) |

- **Chain orchestration**: `backend/app/market_data/providers/chain.py` — ProviderChain with in-memory cache (TTL 120s), source breakdown tracking, simulation rate disclosure
- **Reconciliation**: `backend/app/data/sources/reconciliation.py` — Multi-source insert/skip/update/conflict logic with audit events
- **Symbol normalization**: `backend/app/data/sources/symbol_aliases.py` — Alias mapping for inconsistent ticker symbols across sources

### ASI / Market Data Sources

| Source | File |
|--------|------|
| ngnmarket.com (primary) | `backend/app/services/ngnmarket_service.py` — ASI, volume, market cap, trending, breadth estimation |
| Market Data V2 (multi-source) | `backend/app/services/market_data_v2.py` — Aggregated market summary |

### FX / CPI Inputs

| Data | Provider | File | Method |
|------|----------|------|--------|
| FX rates (USDNGN) | CSV import only | `backend/app/data/macro/fx_provider.py` | `CsvFxRateProvider` + `FxRateService` with forward-fill |
| CPI (CPI_NGN) | CSV import only | `backend/app/data/macro/cpi_provider.py` | `CsvCpiProvider` + `CpiService` with monthly→daily forward-fill |

**No automated web source for FX or CPI.** Manual CSV uploads required.

### Corporate Actions

| Data | Provider | File |
|------|----------|------|
| Dividends, splits, bonuses | CSV import only | `backend/app/data/corporate_actions/csv_provider.py` |

### Scheduler & Artifacts

- **Daily scheduler**: `backend/app/cli/scheduler.py` — `run_scheduled_ingestion()`, designed for cron (no hardcoded TZ)
- **Backfill CLI**: `backend/app/cli/backfill.py` — `--source auto|ngnmarket|ngx_pdf`, `--start-date`, `--days-back`, coverage report
- **Corporate actions CLI**: `backend/app/cli/corporate_actions.py` — `import-csv`, `compute-tri`
- **Artifact manifests**: `backend/app/data/artifacts/manifest.py` — `ManifestWriter` produces JSON per run in `data/artifacts/`
- **Universe**: `backend/app/data/universe.py` — Top-20 NGX symbols, configurable via `SYMBOL_UNIVERSE` env var

### Historical Storage

- `backend/app/data/historical/storage.py` — CRUD for OHLCV records (in-memory or DB-backed)
- `backend/app/data/historical/ingestion.py` — `HistoricalIngestionService` pipeline

---

## A2) Data Model & Persistence

### 12 Tables (`backend/app/db/models.py`)

| Table | PK Type | Purpose |
|-------|---------|---------|
| `ohlcv_prices` | BigInteger | Daily OHLCV per stock, UQ(symbol, ts) |
| `market_index` | BigInteger | ASI daily values, UQ(name, ts) |
| `signals` | BigInteger | Generated signal records, UQ(signal_id) |
| `no_trade_events` | BigInteger | NO_TRADE decisions with reason codes |
| `audit_events` | BigInteger | System-wide audit log |
| `source_health` | BigInteger | Per-source health tracking, UQ(name) |
| `corporate_actions` | BigInteger | Dividends/splits/bonuses, UQ(symbol, action_type, ex_date) |
| `adjusted_prices` | BigInteger | Split-adjusted close + TRI, UQ(symbol, ts) |
| `fx_rates` | BigInteger | Daily FX rates, UQ(pair, ts) |
| `macro_series` | BigInteger | CPI/macro indicators, UQ(series_name, ts) |
| `portfolios` | Integer | Named portfolio containers |
| `portfolio_transactions` | Integer | BUY/SELL/DIVIDEND/CASH_IN/CASH_OUT/FEE |

### Alembic Migrations (`backend/alembic/versions/`)

| Revision | Tables | Status |
|----------|--------|--------|
| `001_initial_schema.py` | ohlcv_prices, market_index, signals, no_trade_events, audit_events | Complete |
| `002_milestone_ab_tables.py` | source_health, corporate_actions, adjusted_prices, fx_rates, macro_series, portfolios, portfolio_transactions | Complete |

### Schema Management

- **DEV**: `create_all` via `Base.metadata.create_all` (`backend/app/db/engine.py:103`)
- **PROD**: Alembic only. `AUTO_CREATE_SCHEMA=off` or `ENV=production` skips create_all
- **SQLite compat**: JSONB→JSON compiler at `backend/app/db/engine.py:29-31`

---

## A3) Governance & Correctness

### NO_TRADE Enforcement

| Layer | File | Mechanism |
|-------|------|-----------|
| Signal model | `backend/app/db/models.py:Signal.status` | ACTIVE / SUPPRESSED / INVALID / NO_TRADE |
| NoTradeEvent table | `backend/app/db/models.py:NoTradeEvent` | Dedicated table with reason_code + provenance |
| Signal lifecycle | `backend/app/services/signal_lifecycle.py` | `SignalLifecycleManager` with TTL, state transitions, `NoTradeReason` enum |
| Circuit breaker safe mode | `backend/app/data/circuit_breaker.py` | All sources OPEN → NO_TRADE |
| Provenance middleware | `backend/app/middleware/provenance.py` | Rewrites to NO_TRADE in PROD on provenance violation |

### Confidence Scoring

| Component | File |
|-----------|------|
| DataConfidenceScorer | `backend/app/services/confidence.py` — 0-1 score, ConfidenceLevel enum |
| Confidence scoring V2 | `backend/app/services/confidence_scoring.py` |
| Data-level confidence | `backend/app/services/data_confidence.py` |

### Provenance Enforcement (`backend/app/middleware/provenance.py`)

- Middleware on `/api/v1/recommendations*` paths only
- Required fields: `confidence_score`, `status`, plus one of `data_confidence`/`confidence`/`bias_signal`
- DEV: HTTP 500 with diagnostic on violation
- PROD: NO_TRADE fail-safe rewrite (HTTP 200)
- Always writes `PROVENANCE_VIOLATION` audit event
- Toggle: `PROVENANCE_ENFORCEMENT=off` disables

### tri_quality & Portfolio Quality Flags

- `AdjustedPrice.tri_quality`: FULL (has dividends) / PRICE_ONLY
- `PerformanceEngine.QualityFlags`: data_mode (TRI_FULL/PRICE_ONLY), fx_mode (FX_FULL/FX_MISSING/FX_NOT_REQUESTED), inflation_mode (CPI_FULL/CPI_MISSING/CPI_NOT_REQUESTED), overall_quality (FULL/DEGRADED)
- Quality flags propagated through Summary, Timeseries, Decomposition endpoints
- DEGRADED audit events logged when FX/CPI missing

---

## A4) Portfolio Engine

| Component | File | Purpose |
|-----------|------|---------|
| PortfolioService | `backend/app/services/portfolio.py` | Transactions → holdings replay, weighted avg cost, valuation, daily values |
| PerformanceEngine | `backend/app/services/performance.py` | TWR, XIRR (Newton-Raphson), CAGR, volatility, drawdown, Sharpe |
| DecompositionEngine | `backend/app/services/decomposition.py` | Multiplicative: equity × FX (USD) or equity / inflation (REAL_NGN) |
| SummaryService | `backend/app/services/summary.py` | Dashboard aggregation: value, returns, concentration (HHI), drawdown, freshness |
| TimeseriesService | `backend/app/services/timeseries.py` | Chart-ready daily series: value, cumulative return, drawdown, rolling vol |
| TRIEngine | `backend/app/services/tri_engine.py` | Split-adjusted close + dividend reinvestment TRI |

### Multi-Currency Reporting (NGN/USD/REAL_NGN) — End-to-End Wiring

Confirmed wired through:
1. `PerformanceEngine.compute()` — accepts fx_service, cpi_service → quality flags
2. `DecompositionEngine` — multiplicative decomposition into equity/FX/inflation components
3. `SummaryService` — reports value_ngn + value_reporting
4. `TimeseriesService` — daily values in all three modes
5. All portfolio API endpoints accept `?reporting=NGN|USD|REAL_NGN` query param
6. DEGRADED quality flags + audit events when FX/CPI data missing

---

## A5) API Catalog — 69 Routes Across 10 Routers + 3 Root

### Stocks — 7 routes (`/api/v1/stocks/`)

| Method | Path | Parameters | Notes |
|--------|------|------------|-------|
| GET | `/` | sector, liquidity | **No pagination** — returns all stocks |
| GET | `/search` | q (required) | Symbol/name search |
| GET | `/sectors` | — | Sector list |
| GET | `/providers` | — | Provider status |
| GET | `/market-summary` | — | ASI + breadth |
| GET | `/{symbol}` | — | Stock detail |
| GET | `/{symbol}/indicators` | — | Technical indicators |

### Recommendations — 6 routes (`/api/v1/recommendations/`)

| Method | Path | Parameters | Notes |
|--------|------|------------|-------|
| GET | `/` | horizon, action, sector, min_liquidity, limit (1-20) | Top recommendations |
| GET | `/buy` | horizon, limit (1-20) | Buy signals |
| GET | `/sell` | horizon, limit (1-20) | Sell signals |
| GET | `/market-regime` | — | Current regime |
| GET | `/{symbol}` | horizon, user_level | Single stock |
| GET | `/{symbol}/all-horizons` | user_level | All 3 horizons |

### Market — 5 routes (`/api/v1/market/`)

| Method | Path | Parameters | Notes |
|--------|------|------------|-------|
| GET | `/snapshot` | — | ASI, volume, market cap |
| GET | `/trending` | — | Top 5 gainers/losers |
| GET | `/breadth` | — | Advancers/decliners (estimated or real) |
| GET | `/regime` | — | Market regime classification |
| GET | `/summary` | — | All-in-one |

### Portfolios — 10 routes (`/api/v1/portfolios/`)

| Method | Path | Parameters | Notes |
|--------|------|------------|-------|
| POST | `/` | body: name, description, base_currency | Create portfolio |
| GET | `/` | limit (1-200), offset | List portfolios |
| GET | `/{id}` | — | Portfolio detail |
| POST | `/{id}/transactions` | body: transactions[] | Add transactions |
| GET | `/{id}/transactions` | tx_type, start_date, end_date, limit, offset | List transactions |
| GET | `/{id}/holdings` | as_of | Current/historical holdings |
| GET | `/{id}/performance` | start_date, end_date, reporting | TWR/XIRR/CAGR |
| GET | `/{id}/decomposition` | start_date, end_date, reporting | Equity/FX/inflation split |
| GET | `/{id}/summary` | as_of, reporting | Dashboard view |
| GET | `/{id}/timeseries` | start, end, reporting | Chart-ready series |

### Total Return — 3 routes (`/api/v1/tickers/`)

| Method | Path | Parameters | Notes |
|--------|------|------------|-------|
| GET | `/{symbol}/total-return` | start, end, limit, offset | Adjusted close + TRI series |
| GET | `/{symbol}/corporate-actions` | action_type, start, end | Dividends/splits/bonuses |
| GET | `/{symbol}/price-discontinuities` | threshold (default 0.4) | >40% moves |

### Audit — 6 routes (`/api/v1/audit/`)

| Method | Path | Parameters | Notes |
|--------|------|------------|-------|
| GET | `/signals` | symbol, status, direction, strategy, date range, limit (1-500), offset | Signal records |
| GET | `/no-trade` | symbol, reason_code, scope, date range, limit, offset | NO_TRADE events |
| GET | `/events` | component, event_type, level, date range, limit, offset | Audit events |
| GET | `/signals/csv` | same filters | CSV export |
| GET | `/no-trade/csv` | same filters | CSV export |
| GET | `/events/csv` | same filters | CSV export |

### Health — 6 routes (`/api/v1/health/`)

| Method | Path | Parameters | Notes |
|--------|------|------------|-------|
| GET | `/trust` | — | System trust status |
| GET | `/trust/banner` | — | Simplified banner |
| GET | `/explain/{status_code}` | — | Educational explanation |
| GET | `/ping` | — | Simple health check |
| GET | `/subsystems` | — | **Hardcoded** — always returns "ok" |
| GET | `/sources` | — | Per-source health + circuit breaker |

### Performance Tracking — 10 routes (`/api/v1/performance/`)

| Method | Path | Parameters | Notes |
|--------|------|------------|-------|
| GET | `/status` | — | System status |
| GET | `/summary` | days (1-365) | Performance summary |
| GET | `/by-direction` | days | By signal direction |
| GET | `/by-regime` | days | By market regime |
| GET | `/calibration` | days | Calibration analysis |
| GET | `/symbol/{symbol}` | — | Per-symbol performance |
| GET | `/signals` | status, symbol, limit, offset | Tracked signals |
| GET | `/signals/counts` | — | Signal counts by status |
| GET | `/signal/{signal_id}` | — | Signal detail |
| GET | `/hit-rates` | days | Hit rate summary |

### UI Optimized — 5 routes (`/api/v1/ui/`)

| Method | Path | Parameters | Notes |
|--------|------|------------|-------|
| GET | `/pulse` | — | Minimal first-paint data |
| GET | `/summary` | limit (1-20) | UI summary |
| GET | `/stock/{symbol}` | — | Stock detail for UI |
| GET | `/stream` | — | SSE stream (infinite loop) |
| GET | `/explain/{status_code}` | — | Status explanation |

### Knowledge — 11 routes (`/api/v1/knowledge/`)

| Method | Path | Parameters | Notes |
|--------|------|------------|-------|
| GET | `/articles` | category | List articles |
| GET | `/articles/{id}` | — | Article detail |
| GET | `/articles/search` | q | Search articles |
| GET | `/lessons` | level | List lessons |
| GET | `/lessons/{id}` | — | Lesson detail |
| GET | `/lessons/{id}/complete` | — | Mark complete |
| GET | `/paths` | — | Learning paths |
| GET | `/paths/{id}` | — | Path detail |
| GET | `/paths/{id}/progress` | — | Path progress |
| GET | `/categories` | — | Category list |
| GET | `/glossary` | — | Glossary terms |

### Root — 3 routes

| Method | Path | Notes |
|--------|------|-------|
| GET | `/` | API root info |
| GET | `/health` | Simple health check |
| GET | `/api/v1` | API version + endpoint list |

---

## A6) Observability & Operations

| Component | File | Purpose |
|-----------|------|---------|
| Source health | `backend/app/services/source_health.py` + `GET /health/sources` | Per-source health + circuit breaker state |
| Trust status | `backend/app/services/trust_status.py` + `GET /health/trust` | System-wide trust scoring |
| Audit query | `backend/app/api/v1/audit.py` | 6 endpoints for signals, no-trade, events + CSV |
| Artifact manifests | `backend/app/data/artifacts/manifest.py` | JSON manifests per scheduler run |
| Circuit breaker drill | `backend/tests/drill_circuit_breaker.py` | Manual drill script |
| Provenance enforcement | `backend/app/middleware/provenance.py` | Middleware + audit events on violation |

---

## A7) Frontend Status

### Old Vite Frontend (`frontend/`)

- **Stack**: React 18 + TypeScript + Vite + Tailwind
- **Pages**: Dashboard (market overview), Screener, Signals, Watchlist, Learn
- **Deployment**: Has Dockerfile + nginx.conf, referenced in docker-compose.yml
- **Gap**: NOT integrated with portfolio engine (backend Milestones A-D)
- **Status**: Effectively superseded by frontend-next

### New Next.js Frontend (`frontend-next/`)

- **Stack**: Next.js 14.2 + TypeScript + Tailwind CSS + Lightweight Charts
- **Pages** (7 routes, all build clean):
  - `/` — Top Picks: Buy recommendations, market regime banner, trending
  - `/stocks/[symbol]` — Stock Detail: Full recommendation, entry/exit, risk, multi-horizon
  - `/screener` — Sortable/filterable stock table
  - `/portfolios` — Portfolio list with summary metrics
  - `/portfolios/[id]` — Portfolio detail with timeseries, decomposition
  - `/audit` — Audit trail with CSV export
- **API client**: `src/api/client.ts` — ~270 lines covering all backend endpoints
- **Deployment**: No Dockerfile. NOT referenced in docker-compose.yml
- **Status**: Active development. Functional but not production-packaged.

---

## A8) Test Suite

**43 test files** in `backend/tests/`, covering:

| Area | Files | Approx Tests |
|------|-------|-------------|
| Portfolio core + API | test_portfolio_core.py, test_portfolio_api.py | ~67 |
| Performance engine | test_performance_engine.py, test_performance_tracking.py, test_performance_reenable.py | ~67 |
| Summary + Timeseries | test_summary_service.py, test_summary_api.py, test_timeseries_service.py, test_timeseries_api.py | ~62 |
| Decomposition | test_decomposition.py, test_decomposition_api.py | ~35 |
| Corporate actions + TRI | test_corporate_actions.py, test_tri_engine.py, test_total_return_api.py | ~52 |
| Macro data (FX/CPI) | test_macro_data.py | ~42 |
| Confidence scoring | test_confidence_consolidated.py, test_confidence_scoring.py | ~30+ |
| Probabilistic bias | test_probabilistic_bias.py | ~20+ |
| Signal lifecycle | test_signal_lifecycle.py | ~19 |
| Audit + Provenance | test_audit_query.py, test_provenance_enforcement.py | ~49 |
| Ingestion | test_historical_storage.py, test_historical_coverage.py, test_ingestion_hardening.py | ~50+ |
| NGX PDF parser | test_ngx_official_list.py | ~22 |
| Circuit breaker | test_circuit_breaker.py | ~21 |
| Source health | test_source_health.py | ~15 |
| Scheduler + Backfill | test_scheduler.py, test_backfill_cli.py | ~26 |
| HTTP client | test_http_client.py | ~15 |
| Market regime | test_market_regime_engine.py | ~23 |
| Alembic smoke | test_alembic_smoke.py | ~10 |
| Symbol aliases | test_symbol_aliases.py | ~14 |
| Validation | test_validation_service.py | ~16 |
| Trust status | test_trust_status.py | ~13 |
| Recommendation | test_recommendation.py | ~9 |
| Phase 0 audit | test_phase0_audit.py | ~12 |
| Gate tests (network) | test_g1_real_ohlcv.py, test_g2_real_asi.py, test_g4_backfill.py | ~15 |

**Notable**: 1 test skipped (real PDF fixture auto-skip). Gate tests (g1, g2, g4) require network access.

---

# B) SYSTEM HEALTH & GAP / PROBLEM LIST — RISK REGISTER

| # | Severity | Problem | Evidence | Impact | Recommended Fix |
|---|----------|---------|----------|--------|----------------|
| 1 | **CRITICAL** | **No authentication or authorization** | No auth middleware, no User table, no JWT/session/API-key. All 69+ endpoints fully public. `backend/app/main.py` has no auth dependency. `schemas/user.py` defines UserPreferences but no User model or auth flow. | Anyone can create portfolios, add transactions, read all data, consume resources. Impossible for multi-user deployment. | Implement API key auth (minimum) or JWT auth with user model. Add auth dependency to all portfolio/write endpoints. |
| 2 | **CRITICAL** | **CORS allows all origins** | `backend/app/main.py:82-88` — `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]` | Any website can make cross-origin API calls. Combined with #1, any malicious site can manipulate portfolios of any user. | Restrict to known frontend origins. Use env var for allowed origins list. |
| 3 | **HIGH** | **No foreign key constraints in DB** | `backend/app/db/models.py` — grep for `ForeignKey` returns 0 matches. `PortfolioTransaction.portfolio_id` is a plain `Integer`, not FK to `Portfolio.id`. | Orphan transactions possible. No referential integrity. Deleting a portfolio leaves dangling transactions. No cascade behavior. | Add `ForeignKey("portfolios.id")` to `portfolio_id`. Add Alembic migration 003. |
| 4 | **HIGH** | **No rate limiting on any endpoint** | Grep for `rate.?limit|throttl|slowapi|RateLimiter` in `backend/app/` returns 0 matches in API code (only in provider internals). No slowapi dependency in `pyproject.toml`. | API vulnerable to abuse, DoS, and resource exhaustion. Recommendation engine does heavy computation per request. | Add slowapi or custom rate limiter. Priority: /recommendations (CPU-heavy), /portfolios (DB-heavy). |
| 5 | **HIGH** | **Circuit breaker state is in-memory, per-process** | `backend/app/data/circuit_breaker.py:19` — "Thread-safe in-memory state (acceptable for single-process deployments)". Uses `threading.Lock`. | With gunicorn workers >1 or multi-container deployment, each process has independent circuit breaker state. One process may trip while others continue hammering a degraded source. | Accept workers=1 limitation (current) or move state to Redis/DB. Document constraint. |
| 6 | **HIGH** | **FX and CPI data are CSV-only — no automated source** | `backend/app/data/macro/fx_provider.py` — `CsvFxRateProvider`. `backend/app/data/macro/cpi_provider.py` — `CsvCpiProvider`. No web API provider exists. | USD and REAL_NGN reporting will silently degrade as CSV data goes stale. Users must manually upload CSVs. No alerting when data becomes stale. | Add CBN/fixer.io/exchangerate API provider for FX. Add NBS/World Bank API for CPI. At minimum, add staleness alerting. |
| 7 | **HIGH** | **docker-compose.yml references old frontend** | `docker-compose.yml:45-55` — builds from `./frontend` (Vite), not `./frontend-next` (Next.js). | Docker deployment will serve the old, non-integrated Vite frontend. Portfolio features and recommender UI absent. | Update docker-compose to build frontend-next. Add Dockerfile to frontend-next/. |
| 8 | **HIGH** | **No Dockerfile for Next.js frontend** | `frontend-next/` directory has no Dockerfile. Only `frontend/` has one. | Cannot deploy the active frontend via Docker. | Create multi-stage Dockerfile (node build → nginx serve). |
| 9 | **MEDIUM** | **GET /stocks returns all stocks with no pagination** | `backend/app/api/v1/stocks.py:77` — `get_all_stocks()` has no limit/offset params. Returns full list. | If universe grows beyond 20 stocks, response size grows unbounded. No protection against large payloads. | Add limit/offset query params with MAX_LIMIT. |
| 10 | **MEDIUM** | **N+1 query pattern in portfolio endpoints** | `backend/app/api/v1/portfolios.py:282-296` — `get_holdings()` loops per-symbol with separate DB queries. Same pattern at lines 355-373 in `get_performance()`. | Each portfolio request triggers N+2 queries (N=number of unique symbols). Latency grows linearly with portfolio size. | Use `WHERE symbol IN (...)` batch query. Single query for all symbols' latest prices. |
| 11 | **MEDIUM** | **Simulated provider can feed fake data into recommendations** | `backend/app/market_data/providers/simulated_provider.py` — generates random prices. Chain falls through to this if all real sources fail. | Recommendations could be based on random data. `is_simulated` flag exists but recommendation engine doesn't check it. | Add simulated-data suppression in recommendation service. If any input is simulated, force NO_TRADE. |
| 12 | **MEDIUM** | **Health /subsystems endpoint returns hardcoded "ok"** | `backend/app/api/v1/health.py:117-131` — returns static `{"database": {"status": "ok"}, "cache": {"status": "ok"}}` | Gives false confidence. Will report "ok" even if PostgreSQL or Redis are down. No Redis is even used. | Implement real health checks (DB ping, cache ping) or remove endpoint. |
| 13 | **MEDIUM** | **Data licensing / redistribution risk** | Scraping ngnmarket.com (`ngnmarket_service.py`), kwayisi.com (`kwayisi_provider.py`), NGX PDFs (`ngx_official_list.py`). No licensing agreements documented. | Serving scraped data through a public API may violate source ToS. Legal risk for SaaS deployment. | Obtain licensing agreements before public deployment. Document data provenance. |
| 14 | **MEDIUM** | **create_all in dev bypasses Alembic** | `backend/app/db/engine.py:103` — `ENV=dev` triggers `Base.metadata.create_all`. | Schema drift between what Alembic knows and what's in the DB. Adding a column to models.py in dev won't generate a migration. | Run Alembic even in dev. Use create_all only for test fixtures. |
| 15 | **MEDIUM** | **Provenance enforcement only covers /recommendations** | `backend/app/middleware/provenance.py:39-41` — `ENFORCED_PATH_PREFIXES = ("/api/v1/recommendations",)` | Portfolio, stocks, market, and TRI endpoints have no provenance validation. Inconsistent governance. | Extend enforcement to portfolio summary/decomposition endpoints (which already carry quality flags). |
| 16 | **MEDIUM** | **Test fixtures depend on network** | `backend/tests/test_g1_real_ohlcv.py`, `test_g2_real_asi.py`, `test_g4_backfill.py` make real HTTP calls. | CI/CD will fail without internet. Flaky tests. | Mock network calls or mark as integration tests excluded from CI by default. |
| 17 | **MEDIUM** | **SSE stream has no connection limit** | `backend/app/api/v1/ui.py:385-413` — `stream_updates()` creates infinite async generator per client. No max connection limit. | Unbounded SSE connections could exhaust server resources. | Add connection counting, max_connections limit, idle timeout. |
| 18 | **MEDIUM** | **aiosqlite not in prod dependencies** | `pyproject.toml` — aiosqlite is not listed. Only asyncpg. | SQLite dev mode (used for dev/testing) would fail on fresh install without manual `pip install aiosqlite`. | Add aiosqlite to dev dependencies group. |
| 19 | **LOW** | **SECRET_KEY commented out in .env.example** | `backend/.env.example:2` — `# SECRET_KEY=your_very_secret_key` | No secret management. Not used currently, but will be needed for auth. | Uncomment and document. Add to Settings class. |
| 20 | **LOW** | **Knowledge base is static in-memory** | `backend/app/knowledge/base.py`, `lessons.py` — Hardcoded articles/lessons, not DB-backed. | Content updates require code deployment. No admin interface. | Acceptable for MVP. Migrate to DB later. |
| 21 | **LOW** | **User preferences schema without persistence** | `backend/app/schemas/user.py` — defines UserPreferences, RiskTolerance, etc. but no User table, no persistence. | Dead code. User-level personalization not functional. | Remove or implement with auth system. |
| 22 | **LOW** | **Old Pydantic model at app root** | `backend/app/models.py` — basic Stock BaseModel, appears unused by actual API. | Dead code confusion. Two `models.py` files (app/ and db/). | Remove or consolidate. |
| 23 | **LOW** | **Workers directory is empty** | `backend/app/workers/__init__.py` — blank file. | Placeholder. No background workers. Scheduler runs via CLI/cron, not in-process. | Remove or document as future use. |
| 24 | **LOW** | **Gunicorn config at repo root** | `gunicorn_config.py` at project root; backend runs from `backend/`. `workers=1`, `bind=0.0.0.0:10000`. | Path mismatch with Docker (which uses uvicorn). Port inconsistency (Docker: 8000, gunicorn: 10000). | Move to backend/ or remove. Standardize on uvicorn for async. |
| 25 | **LOW** | **Recommendation limit capped at 20** | `backend/app/api/v1/recommendations.py:186,232,269` — `limit: int = Query(5, ge=1, le=20)` | With 20-symbol universe this is fine. Would need adjustment if universe grows. | Acceptable for now. |

---

# C) STOP/GO VERDICT

## Level 1: Internal / Dev Use — **GO** (with conditions)

The platform is **suitable for single-developer use** today.

**Conditions**:
- Run with `ENV=dev`, single uvicorn process
- Manually manage FX/CPI CSVs
- Understand that all endpoints are unauthenticated
- Use SQLite or local PostgreSQL
- Run scheduler manually or via local cron
- Treat recommendations as *directional signals*, not investment advice

**Rationale**: The core engines (portfolio, performance, decomposition, TRI, recommendations) are well-tested (~400+ tests). Quality flags and governance are in place. The circuit breaker and provenance enforcement add safety. The frontend surfaces the data effectively.

## Level 2: Small Private Beta (≤10 trusted users) — **CONDITIONAL GO**

**Must-fix before beta** (P0):
1. **Add API key authentication** — at minimum, a shared API key via header. Prevents unauthorized access.
2. **Restrict CORS origins** — whitelist the frontend domain only.
3. **Add rate limiting** — slowapi with 60 req/min per key on /recommendations, 120/min on reads.
4. **Fix docker-compose** — point to frontend-next, add Dockerfile for Next.js.
5. **Add foreign key constraints** — Alembic migration 003.

**Should-fix** (P1):
6. Automate FX data (at least a daily cron that fetches from a free API)
7. Suppress recommendations when simulated data is the input source
8. Fix the hardcoded /health/subsystems endpoint

**Rationale**: With API keys + CORS + rate limiting, the system is safe for a small trusted group. The recommendation engine and portfolio intelligence are the core value — they work. FX staleness is manageable if users understand NGN-only reporting is always reliable.

## Level 3: Production / Public SaaS — **NO-GO**

**Must-fix (P0 blockers)**:
1. Full user authentication + authorization (JWT + user model + RBAC)
2. CORS restricted to production domains
3. Rate limiting + abuse protection
4. Foreign key constraints + data integrity
5. Automated FX/CPI data sources (not CSV-only)
6. Data licensing agreements for all scraped sources
7. Simulated data suppression in recommendations
8. Production Docker stack (frontend-next Dockerfile, updated compose)
9. Health checks that actually verify subsystems
10. Connection limits on SSE endpoint

**Must-fix (P1)**:
11. N+1 query optimization in portfolio endpoints
12. Pagination on all list endpoints
13. Alembic-only schema management (no create_all in any mode)
14. Background job infrastructure (replace CLI cron with proper worker)
15. Monitoring/alerting (FX staleness, source health degradation)
16. Multi-worker circuit breaker state (Redis-backed)

**Rationale**: No authentication is a hard blocker for any multi-user deployment. Combined with permissive CORS, the system is wide open. Data licensing risk makes public redistribution of scraped market data legally questionable. These are not optional — they must be resolved before public launch.

---

# D) ACTION PLAN — PRIORITIZED BACKLOG

## P0 — Must-Fix for Beta (estimated 3-5 days)

| # | Task | Severity | Effort |
|---|------|----------|--------|
| P0-1 | API key authentication (header-based, per-user keys in DB) | CRITICAL | 1 day |
| P0-2 | CORS origin whitelist (env var driven) | CRITICAL | 2 hours |
| P0-3 | Rate limiting via slowapi (60/min recommendations, 120/min reads) | HIGH | 4 hours |
| P0-4 | Alembic migration 003: FK constraints (portfolio_transactions → portfolios) | HIGH | 3 hours |
| P0-5 | frontend-next Dockerfile + docker-compose update | HIGH | 4 hours |
| P0-6 | Suppress recommendations when simulated data is input source | MEDIUM | 3 hours |

## P1 — Should-Fix for Beta / Must-Fix for Prod (estimated 5-8 days)

| # | Task | Severity | Effort |
|---|------|----------|--------|
| P1-1 | Automated FX rate provider (exchangerate.host or similar free API) | HIGH | 1 day |
| P1-2 | N+1 query optimization (batch `WHERE symbol IN (...)`) | MEDIUM | 4 hours |
| P1-3 | Pagination on GET /stocks and all unbounded list endpoints | MEDIUM | 4 hours |
| P1-4 | Fix /health/subsystems to actually check DB connectivity | MEDIUM | 2 hours |
| P1-5 | SSE connection limit + idle timeout | MEDIUM | 3 hours |
| P1-6 | Network-dependent tests marked as integration (excluded from CI default) | MEDIUM | 2 hours |
| P1-7 | Provenance enforcement extended to portfolio summary/decomposition | MEDIUM | 3 hours |
| P1-8 | aiosqlite added to dev dependencies in pyproject.toml | MEDIUM | 15 min |

## P2 — Production Hardening (estimated 2-3 weeks)

| # | Task | Severity | Effort |
|---|------|----------|--------|
| P2-1 | Full JWT auth with user model, registration, RBAC | CRITICAL (for prod) | 3-5 days |
| P2-2 | Data licensing agreements for ngnmarket.com, kwayisi.com, NGX | MEDIUM | External |
| P2-3 | Redis-backed circuit breaker state for multi-worker | HIGH (for scale) | 1-2 days |
| P2-4 | Automated CPI provider (NBS or World Bank API) | MEDIUM | 1 day |
| P2-5 | Background worker infrastructure (Celery/ARQ replacing cron) | MEDIUM | 2-3 days |
| P2-6 | Monitoring/alerting (FX staleness, source degradation, error rates) | MEDIUM | 1-2 days |
| P2-7 | Alembic-only schema management (remove create_all from all non-test paths) | MEDIUM | 3 hours |
| P2-8 | Remove dead code (app/models.py, empty workers/, unused schemas) | LOW | 2 hours |
| P2-9 | Frontend production build optimization (static export, CDN, caching headers) | LOW | 1 day |

---

# Summary

**What works well**: The core platform has substantial engineering depth — multi-currency reporting with quality flags, 6-layer recommendation engine with probabilistic bias signals, TRI computation with corporate action adjustments, provenance enforcement middleware, circuit breakers, and ~400+ deterministic tests. The "Nigeria currency reality" (NGN/USD/REAL_NGN decomposition) is correctly wired end-to-end.

**What's missing**: Authentication (the single biggest gap), automated macro data sources, production deployment packaging, and the standard security hardening (rate limiting, CORS, FK constraints) that separates a dev prototype from a deployable system.

**Bottom line**: This is a well-architected platform that needs security and ops hardening before serving any user other than the developer.
