# Phase 2 Roadmap — Production-Grade NGX Terminal

**Prerequisite:** All P0 gates (G1–G6) pass. Backfill complete. Smoke cycle verified.

---

## P0.5 — Data Resiliency (do before anything else in P2)

### P0.5-1: Second EOD Source — NGX Official Daily List
- Parse NGX Daily Official List PDFs (official closing prices)
- Store as secondary source with `source = "NGX_OFFICIAL_PDF"`
- Reconcile against ngnmarket.com on each ingestion run
- If divergence > threshold → flag in `audit_events`, use official as truth
- **Files:** `backend/app/data/sources/ngx_official.py`, ingestion update
- **Test:** reconciliation test with known divergence fixture

### P0.5-2: Deep Backfill (252+ sessions)
- Re-run backfill with `--min-sessions 252` for 1-year coverage
- Stretch goal: 500+ sessions (2 years) for regime engine stability
- Add `--start-date` flag to CLI for targeted historical windows
- **Files:** `backend/app/cli/backfill.py` (extend), universe config

---

## P1 — Ingestion Hardening

### P1-1: Circuit Breakers + Safe Mode
- Per-source circuit breaker: `CLOSED → OPEN → HALF_OPEN`
- Triggers: 3 consecutive failures OR error rate > 50% in 5-min window
- When open: skip source, use last-known-good cache, emit `STALE_DATA` reason code
- System-wide safe mode: if ALL sources tripped → all symbols → `NO_TRADE`
- **Files:** `backend/app/data/circuit_breaker.py` (NEW), provider chain update
- **Test:** mock source failures, verify breaker opens, signals go NO_TRADE

### P1-2: Retry + Jitter + Timeout Discipline
- All httpx calls: `timeout=10s`, 3 retries, exponential backoff + jitter
- Centralize in `backend/app/core/http.py` — single httpx client factory
- Replace all ad-hoc httpx.AsyncClient() with factory
- **Files:** `backend/app/core/http.py` (NEW), provider updates
- **Test:** timeout and retry behavior with mock server

### P1-3: Source Health Dashboard
- Per-source metrics table: `source_health` (name, last_success, last_error, error_rate, stale_rate, circuit_state)
- API endpoint: `GET /api/v1/health/sources`
- UI status bar: "Data OK / Degraded / Safe Mode"
- **Files:** `backend/app/db/models.py` (add table), health endpoint update, frontend component
- **Test:** health endpoint returns correct states

### P1-4: Daily Scheduler (Incremental EOD Ingestion)
- Async scheduler: run backfill incrementally each evening (NGX close 14:30 WAT + 2h buffer)
- Store raw source artifacts (HTML snapshots) for audit reproducibility
- Write `audit_events` on each run: symbols updated, errors, artifacts stored
- **Files:** `backend/app/cli/scheduler.py` (NEW), `backend/app/data/artifacts/` (NEW dir)
- **Test:** scheduler runs, writes artifacts, audit trail complete

---

## P2 — Frontend Migration

### P2-1: Next.js Migration (Vite → Next.js)
- Standalone milestone — do NOT mix with data resiliency work
- Keep terminal-style UI aesthetic, port existing React components
- Add SSR for SEO-relevant pages (dashboard, stock detail)
- Wire to existing FastAPI backend via API routes
- **Scope:** `frontend/` rewrite, keep `backend/` untouched
- **Gate:** All existing UI functionality works, Lighthouse score ≥ 80

---

## P3 — Governance Hardening

### P3-1: Authentication + RBAC
- JWT auth with refresh tokens
- Role-based access: `viewer`, `analyst`, `admin`
- Replace `allow_origins=["*"]` with explicit origin list
- **Files:** `backend/app/core/auth.py`, middleware, user model

### P3-2: Signal Audit Queryability
- API endpoints for querying `no_trade_events`, `signals`, `audit_events`
- Filters: symbol, date range, reason code, component
- Pagination, export to CSV
- **Files:** `backend/app/api/v1/audit.py` (NEW)

### P3-3: Provenance Completeness Enforcement
- Middleware/decorator that validates every API response carries provenance fields
- Reject internal calls that produce signals without `source` + `ingested_at`
- **Test:** provenance completeness assertions on all recommendation paths

---

## Implementation Checklist (ordered)

| # | Item | Priority | Depends On | Est. Size |
|---|------|----------|------------|-----------|
| 1 | **P0.5-1** Second EOD source (NGX PDF) | HIGH | P0 done | M |
| 2 | **P0.5-2** Deep backfill 252+ sessions | HIGH | P0 done | S |
| 3 | **P1-1** Circuit breakers + safe mode | HIGH | P0.5-1 | M |
| 4 | **P1-2** Retry/jitter/timeout discipline | HIGH | — | S |
| 5 | **P1-3** Source health dashboard | MEDIUM | P1-1 | M |
| 6 | **P1-4** Daily scheduler | MEDIUM | P0.5, P1-1 | M |
| 7 | **P2-1** Next.js migration | MEDIUM | — (parallel) | L |
| 8 | **P3-1** Auth + RBAC | MEDIUM | — | M |
| 9 | **P3-2** Signal audit queryability | LOW | P0 G3 | S |
| 10 | **P3-3** Provenance enforcement | LOW | P3-2 | S |

**Size key:** S = 1–2 files, < 1 day | M = 3–6 files, 1–2 days | L = full directory, 3–5 days

---

## Smoke Cycle Procedure (run after P0 backfill)

```bash
# 1. Start infra
docker-compose up -d postgres
cd backend

# 2. Run migration
alembic upgrade head

# 3. Backfill
python -m app.cli.backfill --min-sessions 60

# 4. Start API
uvicorn app.main:app --port 8000

# 5. Hit a single symbol endpoint
curl http://localhost:8000/api/v1/recommendations/MTNN

# 6. Verify DB rows
psql -U nse_trader -d nse_trader -c "SELECT count(*) FROM ohlcv_prices WHERE symbol='MTNN';"
psql -U nse_trader -d nse_trader -c "SELECT count(*) FROM ohlcv_prices WHERE symbol='ASI';"
psql -U nse_trader -d nse_trader -c "SELECT * FROM signals ORDER BY created_at DESC LIMIT 5;"
psql -U nse_trader -d nse_trader -c "SELECT * FROM no_trade_events ORDER BY ts DESC LIMIT 5;"
psql -U nse_trader -d nse_trader -c "SELECT * FROM audit_events ORDER BY ts DESC LIMIT 5;"

# 7. Restart API and verify persistence
# Stop uvicorn, restart it, hit the same endpoint
# Confirm historical signals/audit rows are still present
```

---

## P0.5-1 Status: IMPLEMENTED

**Files created:**
- `backend/app/data/sources/ngx_official_list.py` — Downloader + Parser + Provider
- `backend/app/data/sources/reconciliation.py` — Source comparison + audit events
- `backend/tests/test_ngx_official_list.py` — 43 tests (parser, reconciliation, downloader, quality)
- `backend/tests/fixtures/README.md` — Instructions for adding real PDF fixtures

**Files modified:**
- `pyproject.toml` — added `pdfplumber ^0.11.0`
- `backend/app/core/config.py` — added `NGX_PDF_CACHE_DIR`, `NGX_PDF_URL_TEMPLATE`
- `backend/app/market_data/providers/base.py` — added `NGX_OFFICIAL_LIST_PDF` to `DataSource`
- `backend/app/data/historical/storage.py` — added `update_ohlcv()` for reconciliation
- `backend/app/cli/backfill.py` — added `--source` flag (`ngnmarket | ngx_pdf | auto`), `--days-back`

---

## Ops Notes — Daily EOD Ingest After Market Close

### NGX Trading Hours
- NGX closes at **14:30 WAT** (13:30 UTC)
- PDFs typically available on doclib.ngxgroup.com by **16:00–17:00 WAT**

### Recommended Schedule (cron)
```bash
# Run daily at 18:00 WAT (17:00 UTC) — gives 1.5h buffer after close
0 17 * * 1-5  cd /opt/nse_trader/backend && python -m app.cli.backfill --source auto --days-back 5

# Weekly deep sync (Saturday) — catch any missed days
0 6 * * 6  cd /opt/nse_trader/backend && python -m app.cli.backfill --source auto --days-back 30
```

### What `--source auto` does
1. Fetches per-symbol history from ngnmarket.com (primary)
2. Checks which symbols have < `--min-sessions` sessions
3. For insufficient symbols, downloads NGX PDFs for the `--days-back` window
4. Runs reconciliation: if close prices diverge > 2%, updates to NGX Official value + writes audit event

### Monitoring
- Check `data/backfill_report.txt` after each run
- Query audit events for reconciliation discrepancies:
  ```sql
  SELECT * FROM audit_events
  WHERE component = 'reconciliation'
  ORDER BY ts DESC LIMIT 20;
  ```
- Monitor PDF cache disk usage: `du -sh data/ngx_pdfs/`

### PDF Cache Management
- PDFs cached in `data/ngx_pdfs/` (configurable via `NGX_PDF_CACHE_DIR`)
- Each PDF is ~200KB–1MB; 252 trading days ≈ 50–250MB
- Safe to prune PDFs older than 1 year: `find data/ngx_pdfs/ -mtime +365 -delete`

### Failure Modes
| Failure | Behavior | Action |
|---------|----------|--------|
| doclib.ngxgroup.com down | PDF download returns None; missing_dates logged | Retry next run; `--days-back 30` weekly catches gaps |
| PDF format changes | Parser finds no header → 0 rows parsed; logged | Update `_COLUMN_MAP` in `ngx_official_list.py` |
| ngnmarket.com down | Primary backfill fails; auto falls back to PDF | System continues with PDF-only data |
| Both sources down | All symbols fail; NO_TRADE enforced (existing G1/G2 governance) | Manual intervention; check source health |

---

## P0.5-2 Status: IMPLEMENTED — Deep Backfill CLI

**Files modified:**
- `backend/app/cli/backfill.py` — `--start-date`, `--end-date`, `resolve_date_window()`, `generate_coverage_report()`, `persist_coverage_report()`

**Files created:**
- `backend/tests/test_backfill_cli.py` — 12 tests (flag precedence, coverage report, gap detection, thresholds)

**Usage:**
```bash
# 1-year deep backfill
python -m app.cli.backfill --source auto --start-date 2025-02-23 --end-date 2026-02-23

# Coverage report written to data/coverage_report.json after every run
```

---

## P1-2 Status: IMPLEMENTED — Centralized HTTP Client

**Files created:**
- `backend/app/core/http.py` — `http_fetch()`, `http_fetch_text()`, `http_fetch_bytes()`, `get_http_client()`
- `backend/tests/test_http_client.py` — 15 tests (retry, backoff, jitter, timeout, 4xx/5xx, 429)

**Files modified (provider refactors):**
- `backend/app/market_data/providers/ngx_provider.py`
- `backend/app/market_data/providers/ngnmarket_provider.py`
- `backend/app/market_data/providers/kwayisi_provider.py`
- `backend/app/market_data/providers/apt_securities_provider.py`
- `backend/app/data/sources/ngx_official_list.py`
- `backend/app/data/historical/ingestion.py`
- `backend/app/services/ngnmarket_service.py`

**Env vars:**
| Variable | Default | Description |
|----------|---------|-------------|
| `HTTP_TIMEOUT_SECONDS` | `10.0` | Global HTTP timeout |
| `HTTP_MAX_RETRIES` | `3` | Max retry attempts |
| `HTTP_BACKOFF_BASE` | `0.5` | Exponential backoff base (seconds) |
| `HTTP_BACKOFF_MAX` | `30.0` | Max backoff cap |
| `HTTP_USER_AGENT` | Mozilla/5.0... | User-Agent header |

---

## P1-1 Status: IMPLEMENTED — Circuit Breakers + Safe Mode

**Files created:**
- `backend/app/data/circuit_breaker.py` — `CircuitBreaker`, `CircuitBreakerRegistry`, `CircuitState`
- `backend/tests/test_circuit_breaker.py` — 21 tests (state transitions, error rate, snapshot, registry, safe mode)
- `backend/tests/drill_circuit_breaker.py` — 5-run operational drill (happy path, forced failure, error rate trip, observability, never_called)

**Policy:**
- OPEN after 3 consecutive failures OR >50% error rate in 5-min window
- HALF_OPEN probe after cooldown (configurable, default 60s; 1 call allowed)
- Safe Mode = all registered sources OPEN → NO_TRADE for all symbols

**Production caveats (queued, not blockers):**
- **Multi-worker memory scope:** Each Uvicorn worker has its own in-memory breaker state. For multi-worker deployments, migrate to shared state (Redis) or force single-worker for ingestion paths.
- **Cooldown tuning:** Default 60s; recommended 30–120s in production to avoid thrashing. Configurable via `CircuitBreakerConfig.cooldown_seconds`.

---

## P1-3 Status: IMPLEMENTED — Source Health Dashboard

**Files created:**
- `backend/app/services/source_health.py` — `SourceHealthService`, per-source tracking + circuit breaker integration
- `backend/tests/test_source_health.py` — 20 tests (recording, 4-state status, staleness, never_called, registry-only sources, API endpoint)

**Files modified:**
- `backend/app/db/models.py` — added `SourceHealth` table
- `backend/app/api/v1/health.py` — added `GET /api/v1/health/sources`

**API:**
```
GET /api/v1/health/sources
→ { "overall_status": "OK|RECOVERING|DEGRADED|SAFE_MODE", "sources": [...], "checked_at": "..." }
```

**4-state overall_status rules:**
| Status | Condition |
|--------|-----------|
| `OK` | All sources CLOSED, no staleness |
| `RECOVERING` | No sources OPEN, but ≥1 HALF_OPEN (probe in progress) |
| `DEGRADED` | Any source OPEN, or any source stale (`stale_count > 0`) |
| `SAFE_MODE` | ALL sources OPEN / unavailable |

**Per-source `never_called` flag:** Sources registered in the breaker registry but never called via the health service show `"never_called": true` so ops can distinguish "healthy" from "assumed healthy (unused)".

---

## P1-4 Status: IMPLEMENTED — Daily Scheduler + Artifact Storage

**Files created:**
- `backend/app/cli/scheduler.py` — `run_scheduled_ingestion()` with manifest + audit
- `backend/app/data/artifacts/manifest.py` — `ManifestWriter`, `RunManifest`, `DateEntry`
- `backend/app/data/artifacts/__init__.py`
- `backend/tests/test_scheduler.py` — 14 tests (manifest CRUD, scheduler run, safe mode flag)

**Usage:**
```bash
# Daily scheduled run (use in cron — no hardcoded TZ)
python -m app.cli.scheduler --source auto --days-back 5

# Cron (18:00 WAT = 17:00 UTC, Mon–Fri)
0 17 * * 1-5  cd /opt/nse_trader/backend && python -m app.cli.scheduler
```

**Artifacts:** stored in `data/artifacts/manifest_YYYYMMDDTHHMMSS.json`

---

## Full Test Suite (161 tests)

| File | Tests | Focus |
|------|-------|-------|
| `test_confidence_consolidated.py` | 18 | Confidence scorer |
| `test_g1_real_ohlcv.py` | 7 | G1 gate |
| `test_g2_real_asi.py` | 8 | G2 gate |
| `test_g4_backfill.py` | 8 | G4 gate |
| `test_ngx_official_list.py` | 43+1 | PDF parser, reconciliation, downloader |
| `test_http_client.py` | 15 | HTTP retry/backoff/jitter |
| `test_backfill_cli.py` | 12 | CLI flags, coverage report |
| `test_circuit_breaker.py` | 21 | Breaker states, safe mode |
| `test_source_health.py` | 15 | Health service, API endpoint |
| `test_scheduler.py` | 14 | Manifest, scheduler run |

```bash
python -m pytest tests/test_confidence_consolidated.py tests/test_g1_real_ohlcv.py tests/test_g2_real_asi.py tests/test_g4_backfill.py tests/test_ngx_official_list.py tests/test_http_client.py tests/test_backfill_cli.py tests/test_circuit_breaker.py tests/test_source_health.py tests/test_scheduler.py -v
```

---

## P3-2 Status: IMPLEMENTED — Signal Audit Queryability

**Files created:**
- `backend/app/api/v1/audit.py` — 6 endpoints: signals, no-trade, audit events (JSON + CSV each)
- `backend/tests/test_audit_query.py` — 25 tests (helpers, filtering, pagination, CSV export, combined filters)

**Files modified:**
- `backend/app/main.py` — registered audit router

**Endpoints:**
| Endpoint | Filters | CSV |
|----------|---------|-----|
| `GET /api/v1/audit/signals` | symbol, status, direction, strategy, date range | `/signals/csv` |
| `GET /api/v1/audit/no-trade` | symbol, reason_code, scope, date range | `/no-trade/csv` |
| `GET /api/v1/audit/events` | component, event_type, level, date range | `/events/csv` |

All endpoints support `limit` (1–500, default 50) and `offset` pagination, and return `total` count.

---

## P3-3 Status: IMPLEMENTED — Provenance Completeness Enforcement

**Files created:**
- `backend/app/middleware/__init__.py`
- `backend/app/middleware/provenance.py` — `ProvenanceEnforcementMiddleware`
- `backend/tests/test_provenance_enforcement.py` — 24 tests (validation, extraction, pass-through, DEV 500, PROD NO_TRADE, audit event)

**Files modified:**
- `backend/app/main.py` — registered middleware

**Behavior:**
- Enforces on `/api/v1/recommendations*` paths
- Required fields: `confidence_score`, `status`, plus at least one of `data_confidence`/`confidence`/`bias_signal`
- **DEV mode** (`ENV != production`): returns HTTP 500 with violation details
- **PROD mode** (`ENV=production`): rewrites response to NO_TRADE fail-safe (200)
- Always writes `PROVENANCE_VIOLATION` audit event on failure
- Disabled via `PROVENANCE_ENFORCEMENT=off`

---

## Milestone A Status: IMPLEMENTED — Corporate Actions + Total Return Series

**Decision:** Option A accepted. Long-term portfolio performance is fundamentally wrong without dividends and splits. Nigerian blue chips pay 5-10% annual dividend yields; ignoring this is a data correctness bug, not a feature gap.

### PR1: Data Models + CSV Import Provider (23 tests)

**Files created:**
- `backend/app/db/models.py` — added `CorporateAction` and `AdjustedPrice` tables
- `backend/app/data/corporate_actions/__init__.py`
- `backend/app/data/corporate_actions/csv_provider.py` — `CsvCorporateActionProvider` with full validation
- `backend/tests/test_corporate_actions.py` — 23 tests (parsing, validation, edge cases, DB round-trip)

**Data model:**
| Table | Key columns | Unique constraint |
|-------|------------|-------------------|
| `corporate_actions` | symbol, action_type, ex_date, amount, ratio_from/to, source, confidence, provenance | (symbol, action_type, ex_date) |
| `adjusted_prices` | symbol, ts, close_raw, adj_factor, adj_close, tri, tri_quality, provenance | (symbol, ts) |

### PR2: TRI Computation Engine + Backfill CLI (19 tests)

**Files created:**
- `backend/app/services/tri_engine.py` — `TRIEngine` (pure computation, no DB)
- `backend/app/cli/corporate_actions.py` — `import-csv` + `compute-tri` commands
- `backend/tests/test_tri_engine.py` — 19 deterministic tests

**TRI algorithm:**
- Forward-pass with cumulative adjustment factor (base=1.0 on earliest date)
- Split/bonus: `adj_factor *= (ratio_to / ratio_from)` → continuous adj_close
- Dividend reinvestment at ex-date close: `dividend_yield = adjusted_div / prev_adj_close`
- TRI base = 1000.0; `tri[t] = tri[t-1] * (1 + price_return + dividend_yield)`
- `tri_quality = FULL` when dividends exist, `PRICE_ONLY` otherwise

**CLI commands:**
```bash
python -m app.cli.corporate_actions import-csv --file actions.csv
python -m app.cli.corporate_actions compute-tri --symbol DANGCEM
python -m app.cli.corporate_actions compute-tri --all --start-date 2023-01-01
```

### PR3: API Endpoints + Governance (15 tests)

**Files created:**
- `backend/app/api/v1/total_return.py` — 3 endpoints
- `backend/tests/test_total_return_api.py` — 15 tests

**Endpoints:**
| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/tickers/{symbol}/total-return` | Adj close + TRI series (filterable, paginated) |
| `GET /api/v1/tickers/{symbol}/corporate-actions` | Dividends, splits, bonuses (filterable) |
| `GET /api/v1/tickers/{symbol}/price-discontinuities` | Detect unexplained >40% moves vs recorded splits |

**Governance:**
- Every response includes `tri_quality` label: `FULL` or `PRICE_ONLY`
- `PRICE_ONLY` provenance note: "no dividend data available, TRI tracks price return only"
- Price discontinuity detector cross-references OHLCV jumps against corporate_actions → `EXPLAINED` vs `UNEXPLAINED`
- Unexplained discontinuities trigger best-effort `PRICE_DISCONTINUITY_DETECTED` audit event (WARN level)

**Acceptance criteria met:**
- ✅ For any symbol + date range: return Close, Adj Close, TRI, daily returns
- ✅ List dividends in-range with provenance
- ✅ Re-running same window produces identical TRI (reproducible — deterministic engine)
- ✅ Missing action data labeled `PRICE_ONLY` (never silently "looks complete")
- ✅ Split adjustment preserves economic continuity (adj_close continuous across splits)
- ✅ Cash dividend reinvestment increases TRI vs price-only

---

## Milestone B Status: IMPLEMENTED — Portfolio Engine + NGN/USD/REAL_NGN Reporting

**Decision: B (Modified Sequencing).** Option A's scope was correct but monolithic. Split into 4 focused PRs. Deferred Alembic to pre-production P0 (no investor value in dev phase). FX/CPI layer built independently first, then Portfolio + Performance on top.

### PR1: FX + CPI Data Layer (42 tests)

**Files created:**
- `backend/app/db/models.py` — added `FxRate` (pair, ts, rate, source, provenance), `MacroSeries` (series_name, ts, value, frequency), `Portfolio`, `PortfolioTransaction`
- `backend/app/data/macro/__init__.py`
- `backend/app/data/macro/fx_provider.py` — `CsvFxRateProvider` + `FxRateService` (forward-fill interpolation for weekends/holidays)
- `backend/app/data/macro/cpi_provider.py` — `CsvCpiProvider` + `CpiService` (monthly→daily forward-fill, deflator computation)
- `backend/tests/test_macro_data.py` — 42 tests (CSV parsing, forward-fill, FX conversion, CPI deflation, devaluation impact, DB round-trip)

**Key design:**
- FX convention: pair = "USDNGN", rate = NGN per 1 USD
- CPI forward-fill: monthly value carried until next publication
- Quality flags: `FX_FULL`/`FX_MISSING`, `CPI_FULL`/`CPI_MISSING`
- Business-critical test: 50% NGN gain + 40% devaluation → -10% USD return

### PR2: Portfolio Core (42 tests)

**Files created:**
- `backend/app/services/portfolio.py` — `PortfolioService` (holdings replay, weighted avg cost, valuation)
- `backend/tests/test_portfolio_core.py` — 42 tests (validation, buy/sell, cash balance, as-of, valuation, daily values)

**Design decisions:**
- Holdings replayed from transactions (not cached) — deterministic, auditable
- Weighted average cost basis for position tracking
- Valuation quality: `FULL`/`PARTIAL`/`PRICE_MISSING`
- All prices in NGN; currency conversion is a reporting-layer concern

### PR3: Performance Engine (36 tests)

**Files created:**
- `backend/app/services/performance.py` — `PerformanceEngine` (TWR, XIRR, CAGR, volatility, drawdown, multi-currency)
- `backend/tests/test_performance_engine.py` — 36 deterministic tests

**Metrics computed:**
| Metric | Method |
|--------|--------|
| TWR | Chain-linked daily returns |
| MWR/XIRR | Newton-Raphson on cash flows |
| CAGR | (end/start)^(1/years) - 1 |
| Volatility | Daily σ × √252 for annualized |
| Max Drawdown | Peak-to-trough with dates |
| Sharpe | TWR_ann / vol_ann (risk-free=0) |

**Reporting modes:**
| Mode | Formula | Quality Flag |
|------|---------|-------------|
| NGN | Raw nominal | data_mode |
| USD | value_ngn / fx_usdngn | fx_mode |
| REAL_NGN | value_ngn / (cpi/cpi_base) | inflation_mode |

**Nigeria-specific tests verified:**
- ✅ 50% NGN gain + 40% Naira devaluation → -10% USD return
- ✅ 20% nominal gain + 30% inflation → -7.7% real return
- ✅ Flat NGN portfolio + 30% CPI rise → -23% real value loss

### PR4: Portfolio API + Governance (25 tests)

**Files created:**
- `backend/app/api/v1/portfolios.py` — 7 endpoints, registered in `main.py`
- `backend/tests/test_portfolio_api.py` — 25 tests

**Endpoints:**
| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/portfolios` | Create portfolio |
| `GET /api/v1/portfolios` | List portfolios (paginated) |
| `GET /api/v1/portfolios/{id}` | Get portfolio detail |
| `POST /api/v1/portfolios/{id}/transactions` | Add bulk transactions (validated) |
| `GET /api/v1/portfolios/{id}/transactions` | List transactions (filtered) |
| `GET /api/v1/portfolios/{id}/holdings` | Holdings + valuation as-of date |
| `GET /api/v1/portfolios/{id}/performance?reporting=NGN\|USD\|REAL_NGN` | Full performance with quality flags |

**Governance:**
- Every performance response includes `quality.overall_quality`: `FULL` or `DEGRADED`
- Missing FX → `fx_mode: FX_MISSING`, `overall_quality: DEGRADED` (never silent)
- Missing CPI → `inflation_mode: CPI_MISSING`, `overall_quality: DEGRADED` (never silent)
- DEGRADED reports trigger best-effort `DEGRADED_PERFORMANCE_REPORT` audit event
- Series always includes both `value` (in reporting currency) and `value_ngn` (for cross-reference)

**Acceptance criteria met:**
- ✅ Create portfolio → add transactions → compute performance for a date range
- ✅ Performance available in NGN, USD, and Real NGN with explicit quality flags
- ✅ If FX/CPI missing, response is explicitly DEGRADED and logs audit event
- ✅ Results are reproducible: same inputs → same outputs
- ✅ Transaction validation catches all invalid inputs before persistence
- ✅ Holdings replay is deterministic (no cached state drift)

**Technical note:** Portfolio and PortfolioTransaction use `Integer` PKs (not BigInteger) for SQLite autoincrement compatibility in tests. No functional impact — Integer handles up to ~2B rows.

---

## Decision Log

| Decision | Rationale |
|----------|-----------|
| Keep SQLite storage for now alongside PostgreSQL | Existing ingestion uses it; migrate in P1-4 |
| NGX PDF as second source (not a live API) | Official record, best provenance story, daily-only is fine |
| Next.js migration is standalone P2 | Don't mix frontend rewrite with data integrity work |
| Circuit breaker per-source, not per-symbol | Source-level is the right granularity for NGX (same source serves all symbols) |
| Auth deferred to P3 | Data truthfulness > access control for an internal tool |
| pdfplumber over tabula/camelot | Pure Python, no Java dependency, coordinate-based table detection |
| Local PDF cache over DB blob storage | Simpler, inspectable, configurable path; easy to prune |
| Reconciliation prefers NGX Official close | Official record is canonical; ngnmarket is a scrape of the same source |
| Centralized HTTP client over per-provider ad-hoc | Consistent retry/timeout, testable, single config surface |
| In-memory circuit breakers (not Redis/DB) | Acceptable for single-process; observable via `/health/sources` |
| Scheduler is cron-invoked, not daemon | Simpler, no long-running process to monitor; cron handles schedule |
| Artifact manifests as JSON files | Inspectable, version-controllable, no extra DB table needed |
| Provenance middleware over per-endpoint checks | Single enforcement point, impossible to bypass, auditable |
| JSONB→JSON @compiles for SQLite tests | Avoids needing Postgres for CI; aiosqlite for async test fixtures |
| Corporate Actions before Portfolio Engine | TRI is a data-layer concern below analytics; portfolio on unadjusted prices is garbage |
| Forward-pass TRI with `adj_factor *= (rt/rf)` | Industry-standard backward adjustment applied via forward iteration; adj_close continuous across splits |
| CSV import as primary MVP source | NGX disclosures are inconsistent; admin CSV is reliable, auditable, and sufficient for MVP |
| `tri_quality` FULL vs PRICE_ONLY labeling | Missing dividend data must never silently "look complete"; explicit quality flag + provenance note |
| Best-effort audit writes in API endpoints | Audit should never break the primary response; graceful rollback on failure |
| FX/CPI as standalone data layer before portfolio | Independent value + testable in isolation before mixing with portfolio math |
| Defer Alembic to pre-production P0 | No investor value in dev phase; create_all is correct for active development |
| Forward-fill for FX weekends and CPI monthly→daily | Standard practice; carry last known value until next publication |
| Holdings replayed from transactions (not cached) | Deterministic, auditable; caching is a future optimization layer |
| Integer PKs for Portfolio/PortfolioTransaction | SQLite only auto-increments INTEGER PRIMARY KEY; no production impact (2B row limit) |
| Quality flags on every performance response | Missing FX/CPI must NEVER silently "look complete"; explicit DEGRADED + audit event |
| XIRR via Newton-Raphson (no scipy dependency) | Avoids heavy dependency; converges in <100 iterations for typical portfolios |
| All prices in NGN; currency conversion at reporting layer | Clean separation: data layer is NGN-native; conversion is a view concern |
