# P0 Work Order — PR Plan (FINAL)

## PR0: Dependency Hygiene (G6) ✅
**Gates closed:** G6  
**Files changed:**
- `pyproject.toml` — added `httpx ^0.27.0`, `sqlalchemy[asyncio] ^2.0`, `asyncpg ^0.29`, `alembic ^1.13`, `psycopg2-binary ^2.9`; removed `redis`, `celery[redis]`, `pika`, `requests`, `tradingview-ta`, `afrimarket`, `types-requests`
- `backend/app/core/config.py` — replaced Redis/RabbitMQ/Celery config with `DATABASE_URL`, `DATABASE_URL_SYNC`, `MIN_OHLCV_SESSIONS`, `MIN_ASI_SESSIONS`, `OHLCV_STALENESS_DAYS`
- `backend/.env.example` — updated to reflect new config

## PR1: Consolidate Confidence Scoring (G5) ✅
**Gates closed:** G5  
**Files changed:**
- `backend/app/services/confidence.py` — **NEW** single authoritative module with `DataConfidenceScorer`, `ConfidenceScore`, `ValidationResult`, `ReasonCode` enum
- `backend/app/services/recommendation.py` — imports switched to `confidence.py`; `_convert_validation_to_confidence()` updated to use `ReasonCode`/`ConfidenceLevel`
- `backend/app/services/validation_service.py` — imports switched to `confidence.py`
- `backend/app/services/__init__.py` — exports switched to `confidence.py`
- `backend/tests/test_confidence_consolidated.py` — **NEW** 18 tests covering stale/missing/gappy/suppression/validation
- `backend/app/services/confidence_scoring.py` — DEPRECATED (old tests still reference it)
- `backend/app/services/data_confidence.py` — DEPRECATED (old tests still reference it)

## PR2+PR3: Wire Real OHLCV + ASI (G1 + G2) ✅
**Gates closed:** G1, G2  
**Files changed:**
- `backend/app/services/recommendation.py` — **`_build_price_dataframe()`** completely rewritten: reads from `HistoricalOHLCVStorage`, enforces `MIN_OHLCV_SESSIONS` + staleness check, returns `None` → NO_TRADE when data insufficient. **`_get_market_dataframe()`** completely rewritten: reads ASI from storage, enforces `MIN_ASI_SESSIONS`, returns `None` → regime=UNKNOWN. Constructor type hint fixed (`ConfidenceConfig`).
- `backend/app/data/historical/storage.py` — added `get_ohlcv_dataframe()` method returning pandas DataFrame
- `backend/tests/test_g1_real_ohlcv.py` — **NEW** 7 tests covering no-history, insufficient, stale, sufficient, NaN-free, ASI, metadata

## PR4: PostgreSQL Persistence + Audit Trail (G3) ✅
**Gates closed:** G3  
**Files changed:**
- `backend/app/db/__init__.py` — **NEW** package init
- `backend/app/db/models.py` — **NEW** SQLAlchemy models: `OHLCVPrice`, `MarketIndex`, `Signal`, `NoTradeEvent`, `AuditEvent`
- `backend/app/db/engine.py` — **NEW** async/sync engine, session factory, `init_db()`, `close_db()`
- `backend/alembic.ini` — **NEW** Alembic config
- `backend/alembic/env.py` — **NEW** migration environment
- `backend/alembic/script.py.mako` — **NEW** migration template
- `backend/alembic/versions/001_initial_schema.py` — **NEW** initial migration with 5 tables
- `backend/app/services/audit.py` — **NEW** audit service: `record_no_trade()`, `record_signal()`, `record_audit()`
- `backend/app/services/signal_lifecycle.py` — added `_persist_no_trade_async()` fire-and-forget DB persistence
- `backend/app/main.py` — wired `init_db()`/`close_db()` into FastAPI lifespan
- `docker-compose.yml` — replaced Redis/RabbitMQ with PostgreSQL 16; backend depends on postgres healthcheck

## PR5: Backfill Historical Data (G4) ✅
**Gates closed:** G4  
**Files changed:**
- `backend/app/data/universe.py` — **NEW** 20-symbol universe config with env override
- `backend/app/cli/__init__.py` — **NEW** package init
- `backend/app/cli/backfill.py` — **NEW** backfill CLI: fetches OHLCV+ASI, writes verification report
- `backend/tests/test_g4_backfill.py` — **NEW** 7 tests covering universe config, batch storage, deduplication, DataFrame output

## Deliverables
- `GATE_VERIFICATION_CHECKLIST.md` — commands to verify each gate locally
- `SYSTEM_HEALTH_GAP_ANALYSIS.md` — Phase 1 audit (from prior session)
- `P0_PR_PLAN.md` — this file
