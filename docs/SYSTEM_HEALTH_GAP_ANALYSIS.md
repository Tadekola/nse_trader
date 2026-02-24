# NSE Trader — System Health & Gap Analysis (Phase 1)

**Date:** 2025-02-23  
**Auditor:** Lead Quant Systems Architect  
**Scope:** Full codebase — `backend/`, `frontend/`, configs, tests, CI  

---

## 1) Executive Summary (≤10 bullets)

1. **Solid governance skeleton exists.** `NO_TRADE`, `SUPPRESSED`, signal lifecycle with TTL, and data confidence scoring are all implemented server-side (`signal_lifecycle.py`, `confidence_scoring.py`, `data_confidence.py`).
2. **CRITICAL: Price data fed to indicators is fabricated.** `recommendation.py:558-582` generates synthetic DataFrames with `np.random.normal` noise instead of using real historical OHLCV — every indicator, regime classification, and bias probability downstream is non-deterministic garbage.
3. **CRITICAL: Market regime engine also runs on fake data.** `recommendation.py:584-604` fabricates a 250-row constant ASI DataFrame with random noise for `_get_market_dataframe()`. The `classify_session()` path is poisoned.
4. **No persistent database exists.** All state (watchlists, audit logs, NO_TRADE decisions, signal history, performance metrics) lives in in-memory Python dicts/lists lost on every restart.
5. **Frontend is React/Vite, NOT Next.js.** `package.json` declares Vite + React 18. The master prompt mandates Next.js. This is a full rewrite.
6. **Web scraping is the only ingestion method.** Both `ngnmarket_provider.py` and `kwayisi_provider.py` parse `__NEXT_DATA__` from HTML pages — fragile, no rate limiting, no circuit breakers, will break on any DOM change.
7. **No authentication/authorization.** CORS is `allow_origins=["*"]`, no auth middleware, no user model, no API keys.
8. **Redis and RabbitMQ are configured but unused.** `docker-compose.yml` provisions them; zero code imports or connects to either.
9. **Historical OHLCV storage exists (SQLite)** in `data/historical/storage.py` — but is never wired into the recommendation pipeline.
10. **CI is minimal.** Single GitHub Actions job runs `pytest --cov`, `flake8`, `mypy` — no frontend build, no integration tests, no security scanning.

---

## 2) Current Architecture

### Components & Responsibilities

| Layer | Component | File(s) | Responsibility |
|-------|-----------|---------|----------------|
| **Ingestion** | `NgnMarketProvider` | `market_data/providers/ngnmarket_provider.py` | Tier 0: scrapes ngnmarket.com stock pages for live OHLC |
| **Ingestion** | `NgxEquitiesPriceListProvider` | `market_data/providers/ngx_provider.py` | Tier 1: scrapes NGX official price list PDF/HTML |
| **Ingestion** | `KwayisiNGXProvider` | `market_data/providers/kwayisi_provider.py` | Tier 2: secondary validation source |
| **Ingestion** | `SimulatedProvider` | `market_data/providers/simulated_provider.py` | Tier 3: static registry fallback (flagged as simulated) |
| **Ingestion** | `NgnMarketService` | `services/ngnmarket_service.py` | Market-level data: ASI, breadth (estimated), trending, regime input |
| **Orchestration** | `ProviderChain` | `market_data/providers/chain.py` | Multi-tier fallback with in-memory cache (2min TTL) |
| **Orchestration** | `MarketDataServiceV2` | `services/market_data_v2.py` | Unified data service; enriches with registry metadata |
| **Validation** | `ValidationService` | `services/validation_service.py` | Parallel primary+secondary fetch; delegates to `DataConfidenceScorer` |
| **Confidence** | `DataConfidenceScorer` (x2) | `services/confidence_scoring.py`, `services/data_confidence.py` | Two separate scorers — one for multi-source validation, one for recommendation suppression |
| **Regime** | `MarketRegimeEngine` | `services/market_regime_engine.py` | Classifies session into 5 regimes; caches per day |
| **Bias** | `ProbabilisticBiasCalculator` | `services/probabilistic_bias.py` | Converts deterministic actions → probabilistic bias with regime overlay |
| **Lifecycle** | `SignalLifecycleManager` | `services/signal_lifecycle.py` | TTL enforcement, NO_TRADE evaluation, in-memory audit log |
| **Recommendation** | `RecommendationService` | `services/recommendation.py` | Orchestrates: data→indicators→engine→bias→regime→lifecycle |
| **Indicators** | `base`, `composite`, `momentum`, `trend`, `volatility`, `volume` | `indicators/*.py` | Technical indicator computation (SMA, RSI, MACD, BB, ADX, OBV, etc.) |
| **Core Engine** | `RecommendationEngine`, `MarketRegimeDetector`, `RiskCalculator` | `core/*.py` | Signal generation, risk scoring, entry/exit computation |
| **Knowledge** | `KnowledgeBase`, `LessonsSystem` | `knowledge/*.py` | Educational content for investor education |
| **Fundamentals** | `dividends`, `sector`, `valuation` | `fundamentals/*.py` | Static fundamental data modules |
| **Historical** | `HistoricalOHLCVStorage`, `HistoricalIngestionService` | `data/historical/storage.py`, `ingestion.py` | SQLite OHLCV storage — exists but NOT connected to recommendation pipeline |
| **API** | FastAPI routers | `api/v1/*.py` | REST endpoints: stocks, recommendations, market, health, knowledge, UI |
| **Frontend** | React + Vite + TailwindCSS | `frontend/src/` | SPA with Dashboard, Screener, Signals, Watchlist, Learn pages |

### Data Flow (Current)
```
ngnmarket.com HTML → NgnMarketProvider (scrape) → ProviderChain (cache 2min)
                                                         ↓
                                          MarketDataServiceV2 (enrich w/ registry)
                                                         ↓
                                          RecommendationService.get_recommendation()
                                                         ↓
                                    ┌─────── _build_price_dataframe() ← FABRICATED DATA ⚠️
                                    │        _get_market_dataframe()  ← FABRICATED DATA ⚠️
                                    ↓
                              RecommendationEngine.generate_recommendation()
                                    ↓
                              ProbabilisticBiasCalculator.calculate_bias()
                                    ↓
                              MarketRegimeEngine (adjust bias)
                                    ↓
                              SignalLifecycleManager (TTL + NO_TRADE check)
                                    ↓
                              API Response → Frontend (React/Vite)
```

---

## 3) Risk Register

| # | Risk | Severity | Evidence (file:line) | Impact | Fix |
|---|------|----------|---------------------|--------|-----|
| R1 | **Fabricated price DataFrames** — indicators computed on synthetic noise, not real prices | **CRITICAL** | `recommendation.py:558-582` — `np.random.normal(1, 0.02, len(df))` | Every recommendation, bias probability, and confidence score is meaningless. Users could act on random signals. | Wire `HistoricalOHLCVStorage` into `_build_price_dataframe()`. Block recommendations when history < 20 sessions. |
| R2 | **Fabricated ASI DataFrame** — market regime runs on constant 50500 + random noise | **CRITICAL** | `recommendation.py:584-604` — hardcoded `[50500] * 250` | Regime classification is random. Regime-based governance (suppress bullish in bearish trend) is inoperative. | Use real ASI history from `NgnMarketService.get_asi_history()` or stored data. |
| R3 | **No persistent database** — all audit logs, NO_TRADE decisions, signal history in-memory | **HIGH** | `signal_lifecycle.py:182` (`self._no_trade_log: List`), `chain.py:84` (`InMemoryCache`), all singletons | Complete data loss on restart. No audit trail. Watchlists, alerts, user state impossible. | Add PostgreSQL/SQLite. Migrate all stateful services. |
| R4 | **Web scraping fragility** — ingestion depends on parsing `__NEXT_DATA__` from HTML | **HIGH** | `ngnmarket_provider.py:183-188`, `ngnmarket_service.py:546-561` | Any DOM change on ngnmarket.com silently breaks all data. No alerting on structural changes. | Add structural validation, circuit breaker, staleness alerts. Consider official API if available. |
| R5 | **No authentication** — all endpoints publicly accessible | **HIGH** | `main.py:66-72` — `allow_origins=["*"]`, no auth middleware anywhere | Anyone can hit recommendation endpoints. No user isolation. No rate limiting. | Add API key auth (minimum), then JWT-based user auth. |
| R6 | **Frontend is React/Vite, not Next.js** | **HIGH** | `frontend/package.json` — Vite 6.2, React 18.3, no next dependency | Violates architecture mandate. No SSR, no API routes, no built-in routing. | Full frontend rewrite to Next.js with App Router. |
| R7 | **Two separate confidence scorers** with divergent logic | **MEDIUM** | `services/confidence_scoring.py` (DataConfidenceScorer #1) vs `services/data_confidence.py` (DataConfidenceScorer #2) | Naming collision (`DataConfidenceScorer` class name used in both). Validation path uses #2, recommendation path uses #1. Threshold misalignment possible. | Consolidate into single scorer with clear interface. |
| R8 | **No retry/circuit-breaker on HTTP calls** | **MEDIUM** | `ngnmarket_provider.py:168` — bare `httpx.AsyncClient` with only timeout | Single transient failure = missing data for that stock. No exponential backoff, no circuit state. | Add `tenacity` or custom retry with jitter + circuit breaker. |
| R9 | **`requests` (sync) in deps, `httpx` (async) in code** — dependency mismatch | **MEDIUM** | `pyproject.toml:19` — `requests = "^2.31.0"`, actual code uses `httpx` (not in deps) | `httpx` installed transitively but not declared. `requests` is unused dead weight. | Remove `requests`, add `httpx` to `[tool.poetry.dependencies]`. |
| R10 | **Redis/RabbitMQ/Celery configured but completely unused** | **LOW** | `core/config.py:13-27`, `docker-compose.yml:41-64`, `pyproject.toml:16-18` | Dead infra cost, confusing architecture, false sense of async capability. | Remove until actually needed, or implement queue-based ingestion. |
| R11 | **`datetime.utcnow()` used throughout** — naive UTC, no NGX timezone awareness | **MEDIUM** | 30+ occurrences across services — e.g., `signal_lifecycle.py:261`, `market_regime_engine.py:169` | No awareness of NGX trading hours (10:00-14:30 WAT). Staleness calculations assume UTC. Cache TTLs don't align with market sessions. | Use `datetime.now(timezone.utc)` (utcnow is deprecated in 3.12). Add NGX session-awareness. |
| R12 | **No look-ahead bias protection** | **MEDIUM** | `recommendation.py:558-582` — generates dates up to `datetime.utcnow()` and applies noise retroactively | If real data is ever wired in, must enforce point-in-time: no future data in historical windows. | Timestamp-gated queries; immutable historical records. |
| R13 | **`tradingview-ta` and `afrimarket` in deps but unused in active code** | **LOW** | `pyproject.toml:22,24` — listed; `data/sources/tradingview.py` exists in sources but not in active providers | Dependency bloat, potential supply-chain risk (`afrimarket ^0.0.0.0`). | Audit usage; remove if dead. |
| R14 | **No structured logging** — `logging.basicConfig(level=logging.INFO)` only | **MEDIUM** | `main.py:21` | No JSON logs, no correlation IDs, no log levels per module, not suitable for production observability. | Implement structured logging (structlog or python-json-logger). |
| R15 | **Singleton pattern everywhere — no dependency injection** | **LOW** | `services/__init__.py`, every `get_*()` function | Hard to test, hard to swap implementations, thread-safety concerns. | Move to FastAPI `Depends()` with proper DI. |
| R16 | **Sync wrapper with ThreadPoolExecutor for async calls** | **MEDIUM** | `validation_service.py:264-285` — `fetch_validated_sync` creates new event loops in threads | Potential deadlocks, hidden threading bugs in a primarily async codebase. | Remove sync path; ensure all callers use `await`. |
| R17 | **`BacktestResult` schema exists but no backtesting engine** | **MEDIUM** | `schemas/recommendation.py:191-206` — schema only, no implementation | Schema suggests backtesting was planned but never built. | Implement backtesting engine (Phase 2 deliverable). |
| R18 | **Market breadth is heuristic-estimated, not exchange-reported** | **MEDIUM** | `ngnmarket_service.py:329-417` — hardcoded advancers/decliners based on ASI direction | Breadth data (60/30/10 split) is fabricated heuristic. Used downstream by regime engine. | Clearly flag as estimated (already partially done). Source real breadth when available. |
| R19 | **No input validation on API path parameters** | **LOW** | `recommendations.py:338-387` — `symbol: str` accepted without sanitization | Injection risk for symbol parameter passed to URL construction in providers. | Add regex validation: `symbol: str = Path(regex=r'^[A-Z]{2,10}$')`. |

---

## 4) Governance & Integrity

### NO_TRADE Enforcement: **CONDITIONAL PASS** ⚠️

**Evidence FOR (server-side implementation exists):**
- `signal_lifecycle.py:222-322` — `evaluate_lifecycle()` checks data_confidence, indicator_agreement, regime_hostility, calibration_confidence against configurable thresholds.
- `signal_lifecycle.py:324-417` — `_evaluate_no_trade()` returns `NoTradeDecision` with reasons, thresholds breached, and human-readable explanations.
- `recommendation.py:213-244` — lifecycle result applied: if `NO_TRADE`, `bias_probability` set to `None`, status set to `'NO_TRADE'`.
- `recommendation.py:137-146` — suppressed recommendation path blocks actionable signals when confidence below 0.75.

**Evidence AGAINST (governance is undermined):**
- **The data feeding governance checks is fake** (R1, R2). `indicator_agreement` computed on random noise. `data_confidence` computed on real fetched prices but `regime_confidence` comes from fabricated ASI. The NO_TRADE gate exists but its inputs are unreliable.
- **NO_TRADE log is in-memory only** (`signal_lifecycle.py:182`). Lost on restart. No durable audit.
- **No API-level enforcement** — a client could directly call `/api/v1/stocks/{symbol}` and get raw price data to trade on, bypassing recommendation governance entirely. Governance only applies to the recommendation path.

**Verdict: CONDITIONAL PASS** — The enforcement code is sound and well-structured, but it operates on fabricated data and has no durable audit trail. Fix R1/R2/R3 to make it trustworthy.

---

### Data Confidence: **PASS** (mechanism exists)

**Evidence:**
- `confidence_scoring.py:162-282` — `calculate_confidence()` computes weighted score from price agreement (0.40), volume agreement (0.20), freshness (0.20), source availability (0.20).
- `data_confidence.py:127-178` — `validate()` compares primary vs secondary price snapshots with graduated thresholds (1% agreement, 3% minor divergence, 5% major, 10% suppress).
- `validation_service.py:176-262` — parallel fetch from primary (ngnmarket) + secondary (kwayisi) with non-blocking secondary failure.
- Suppression chain: low confidence → `is_suppressed=True` → `_create_suppressed_recommendation()` → `bias_probability=None`.

**Gap:** Two separate `DataConfidenceScorer` classes exist with different interfaces (R7). Should be consolidated.

---

### Point-in-Time Correctness: **FAIL** ❌

**Evidence:**
- `recommendation.py:558-582` — fabricates 50 rows of data with `pd.date_range(end=datetime.utcnow(), periods=50)` and applies `np.random.normal` noise. This is fundamentally non-point-in-time: it creates synthetic future data.
- `data/historical/storage.py` — SQLite storage exists with proper date-keyed records and `validate_ohlcv_record()`, but is **never used** by the recommendation pipeline.
- No mechanism to prevent look-ahead bias when real data is eventually connected.
- No survivorship bias handling: no tracking of delistings, ticker changes, or suspensions in the recommendation engine.
- No corporate actions database.

---

## 5) Data & Provenance Gaps

### What exists:
- **Price snapshots** carry `source` (DataSource enum), `timestamp`, `is_simulated` flag, `simulated_reason`.
- **Validation metadata** attached to each snapshot: `confidence_level`, `confidence_score`, `sources_count`, `divergence_pct`.
- **Source breakdown** per fetch: `ngx_official: N, apt_securities: N, simulated: N`.
- **Trust status service** aggregates integrity level, simulation rate, staleness.

### What's missing:

| Gap | What must be stored | Priority |
|-----|-------------------|----------|
| **Real historical OHLCV** | Daily OHLCV for ≥50 symbols × ≥24 months. SQLite schema exists but pipeline isn't connected. | P0 |
| **ASI historical time series** | Real ASI daily values (not fabricated). Only ~30 days from ngnmarket scraping; need 12+ months. | P0 |
| **Provenance per indicator value** | Each computed indicator should carry: input data range, source, computation timestamp, freshness. Currently indicators are computed in-place with no metadata. | P1 |
| **Corporate actions** | Dividends, splits, bonus issues, rights, name changes, suspensions for NGX stocks. None tracked. | P1 |
| **Audit trail (durable)** | Every recommendation: inputs → regime → decision → NO_TRADE reason. Currently in-memory only. | P0 |
| **User/session data** | No user model, no watchlists persistence, no alert storage, no saved layouts. | P1 |
| **Backtest results** | Schema exists (`BacktestResult`) but no storage or engine. | P2 |
| **Ingestion heartbeat** | Per-source last-seen timestamp, consecutive failure count, circuit breaker state. | P1 |
| **NGX trading calendar** | Market holidays, half-days, trading hours (10:00-14:30 WAT). None configured. | P1 |

---

## 6) Performance Findings

### Bottlenecks:

| Issue | Location | Impact | Measurement |
|-------|----------|--------|-------------|
| **Sequential per-stock HTTP scraping** | `ngnmarket_provider.py:122-134` — semaphore(10) concurrent fetches | For 50 stocks: ~50 individual HTTP requests to ngnmarket.com. At 500ms/req = ~2.5s even with concurrency. | Measured via `fetch_time_ms` in `FetchResult`. |
| **No connection pooling** | `ngnmarket_provider.py:168` — creates new `httpx.AsyncClient` per stock | TCP+TLS handshake overhead on every request. | N/A — not measured. |
| **In-memory cache only (2min TTL)** | `chain.py:84-121` — `InMemoryCache` | Cold start requires full re-fetch. Multi-process deployments don't share cache. | Cache hit/miss not logged. |
| **Duplicate computation** | `recommendation.py:92-256` — entire pipeline re-runs per symbol per request | No memoization of indicator computation across requests. | N/A. |
| **Frontend: no routing library** | `App.tsx:19-36` — manual state-based page switching | No code splitting, no lazy loading, full bundle loaded upfront. | Bundle size not measured. |

### Quick Wins:
1. **Connection pooling**: Create a single `httpx.AsyncClient` instance with connection limits, reuse across requests.
2. **Redis cache**: Wire up the already-provisioned Redis for shared caching across workers.
3. **Batch endpoint on ngnmarket**: The `/` page already has all stock data in `__NEXT_DATA__` — fetch once instead of per-symbol.
4. **Pre-compute indicators** on ingestion, not on request.

---

## 7) Recommended Roadmap

### P0 — Must Fix Before Any Other Work

| # | Item | Impact | Effort | Notes |
|---|------|--------|--------|-------|
| P0.1 | **Wire real OHLCV into recommendation pipeline** | Fixes R1. Makes all indicators, signals, and bias computations legitimate. | Medium (2-3 days) | Connect `HistoricalOHLCVStorage` → `_build_price_dataframe()`. Add minimum-history gate. |
| P0.2 | **Wire real ASI data into regime engine** | Fixes R2. Makes regime classification and governance meaningful. | Small (1 day) | Use `NgnMarketService.get_asi_history()` or stored ASI in `_get_market_dataframe()`. |
| P0.3 | **Add persistent database** | Fixes R3. Enables audit trail, watchlists, user state. | Medium (3-4 days) | PostgreSQL or SQLite for: audit_log, no_trade_decisions, signal_history, users, watchlists. Alembic migrations. |
| P0.4 | **Consolidate confidence scorers** | Fixes R7. Single source of truth for data quality. | Small (1 day) | Merge `confidence_scoring.py` and `data_confidence.py` into one module. |
| P0.5 | **Historical data backfill** | Enables P0.1. Need ≥60 sessions for indicators. | Medium (2-3 days) | Run `HistoricalIngestionService` for top 50 symbols. Add scheduled re-ingestion. |

### P1 — Required for Production

| # | Item | Impact | Effort |
|---|------|--------|--------|
| P1.1 | **Ingestion resilience** — retry with jitter, circuit breakers, staleness alerting | Fixes R4, R8 | Medium |
| P1.2 | **Authentication** — API key minimum, then JWT | Fixes R5 | Medium |
| P1.3 | **Next.js frontend rewrite** | Fixes R6. Terminal-style UI with AG-Grid, TradingView charts. | Large (2-3 weeks) |
| P1.4 | **Structured logging + observability** | Fixes R14 | Small |
| P1.5 | **Dependency cleanup** — add httpx, remove requests/afrimarket/tradingview-ta if unused | Fixes R9, R13 | Small |
| P1.6 | **NGX trading calendar + timezone handling** | Fixes R11, R12 | Small-Medium |
| P1.7 | **Input validation hardening** | Fixes R19 | Small |
| P1.8 | **FastAPI dependency injection** | Fixes R15, improves testability | Medium |

### P2 — Institutional-Grade Features

| # | Item | Impact | Effort |
|---|------|--------|--------|
| P2.1 | **Backtesting engine** — run bias logic on 24mo+ data, output hit rate/drawdown/expectancy | High | Large |
| P2.2 | **Macro overlay** — CBN MPR, CPI tracking, regime penalty for hostile macro | Medium | Medium |
| P2.3 | **Liquidity tiers + slippage model** | Medium | Medium |
| P2.4 | **Corporate actions calendar** — dividends, earnings, suspensions | Medium | Medium |
| P2.5 | **WebSocket real-time feed** (if source supports) or efficient polling with conditional requests | Medium | Medium |
| P2.6 | **Bloomberg-style UI** — provenance tooltips, global status bar, keyboard nav, saved layouts | High | Large |

---

## 8) Stop/Go Gate — What MUST Be Fixed Before Phase 2

**The following blockers must be resolved before ANY Phase 2 work begins:**

| Gate | Condition | Status |
|------|-----------|--------|
| **G1: Real price data in indicators** | `_build_price_dataframe()` uses stored OHLCV, not fabricated noise | ❌ BLOCKED |
| **G2: Real ASI data in regime engine** | `_get_market_dataframe()` uses real ASI history | ❌ BLOCKED |
| **G3: Persistent audit trail** | NO_TRADE decisions, signal history survive restart | ❌ BLOCKED |
| **G4: Minimum 60 sessions per symbol** | At least top-20 liquidity symbols have ≥60 days OHLCV | ❌ BLOCKED |
| **G5: Single confidence scorer** | One canonical `DataConfidenceScorer` with clear interface | ❌ BLOCKED |
| **G6: httpx declared in dependencies** | `pyproject.toml` includes `httpx` as explicit dependency | ❌ BLOCKED |

**Recommendation: DO NOT proceed to Phase 2 until all six gates are GREEN.**

The current system produces random outputs dressed in sophisticated governance language. The architecture is excellent in design — the services, lifecycle management, probabilistic bias system, and regime engine are well-engineered — but the data foundation is hollow. P0 work focuses entirely on making the existing architecture trustworthy by feeding it real data and persisting its decisions.

---

*End of Phase 1 Deliverable. Awaiting approval to begin Phase 2 implementation.*
