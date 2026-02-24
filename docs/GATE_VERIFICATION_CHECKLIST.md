# P0 Gate Verification Checklist

Run these commands from the repo root to verify each gate passes.

---

## G6 — Dependency Hygiene

```powershell
# Verify httpx is in production deps (not just dev)
Select-String -Path pyproject.toml -Pattern '^httpx'
# Expected: httpx = "^0.27.0" in [tool.poetry.dependencies]

# Verify dead deps removed
Select-String -Path pyproject.toml -Pattern 'redis|celery|pika|requests|tradingview-ta|afrimarket'
# Expected: NO matches

# Verify DB deps present
Select-String -Path pyproject.toml -Pattern 'sqlalchemy|asyncpg|alembic|psycopg2'
# Expected: all four present
```

**PASS criteria:** httpx in prod deps, zero dead deps, DB deps present.

---

## G5 — Single Consolidated Confidence Scorer

```powershell
# Verify single module exists
Test-Path backend/app/services/confidence.py
# Expected: True

# Verify no imports from old modules in active code
Select-String -Path backend/app/services/*.py -Pattern 'from app.services.confidence_scoring import'
# Expected: NO matches (only the old file itself would match, not consumers)

Select-String -Path backend/app/services/*.py -Pattern 'from app.services.data_confidence import'
# Expected: NO matches in recommendation.py, validation_service.py, __init__.py

# Run consolidated confidence tests
cd backend
python -m pytest tests/test_confidence_consolidated.py -v
# Expected: all tests pass
```

**PASS criteria:** Single `confidence.py`, no imports from old modules in active services, all tests green.

---

## G1 — Real OHLCV in Indicator Pipeline

```powershell
# Verify np.random.normal REMOVED from _build_price_dataframe
Select-String -Path backend/app/services/recommendation.py -Pattern 'np.random.normal'
# Expected: NO matches

# Verify fabricated DataFrame REMOVED
Select-String -Path backend/app/services/recommendation.py -Pattern '\* 50.*freq=.D'
# Expected: NO matches

# Verify HistoricalOHLCVStorage is wired in
Select-String -Path backend/app/services/recommendation.py -Pattern 'get_historical_storage'
# Expected: matches in _build_price_dataframe() and _get_market_dataframe()

# Verify governance: MIN_OHLCV_SESSIONS check exists
Select-String -Path backend/app/services/recommendation.py -Pattern 'MIN_OHLCV_SESSIONS'
# Expected: at least 1 match

# Run G1 gate tests
cd backend
python -m pytest tests/test_g1_real_ohlcv.py -v
# Expected: all tests pass
```

**PASS criteria:** No fabrication, real storage wired, min-sessions governance, tests green.

---

## G2 — Real ASI in Regime Engine

```powershell
# Verify fabricated ASI DataFrame REMOVED
Select-String -Path backend/app/services/recommendation.py -Pattern '\[50000\]|\[50500\]|\[51000\]|\[49000\]'
# Expected: NO matches

# Verify real ASI loaded from storage
Select-String -Path backend/app/services/recommendation.py -Pattern 'get_ohlcv_dataframe.*ASI'
# Expected: 1 match in _get_market_dataframe()

# Verify fail-safe: None → NO_TRADE when ASI missing
Select-String -Path backend/app/services/recommendation.py -Pattern 'NO_TRADE\[ASI\]'
# Expected: at least 1 match (log message)
```

**PASS criteria:** No fabricated ASI, real storage read, fail-safe on missing data.

---

## G3 — Persistent Audit Trail (DB)

```powershell
# Verify DB models exist
Test-Path backend/app/db/models.py
Test-Path backend/app/db/engine.py
# Expected: both True

# Verify 5 required tables in models
Select-String -Path backend/app/db/models.py -Pattern '__tablename__'
# Expected: ohlcv_prices, market_index, signals, no_trade_events, audit_events

# Verify Alembic migration exists
Test-Path backend/alembic/versions/001_initial_schema.py
# Expected: True

# Verify audit service exists
Test-Path backend/app/services/audit.py
# Expected: True

# Verify NO_TRADE persisted to DB
Select-String -Path backend/app/services/signal_lifecycle.py -Pattern '_persist_no_trade_async'
# Expected: at least 2 matches (definition + call)

# Verify main.py initializes DB
Select-String -Path backend/app/main.py -Pattern 'init_db'
# Expected: at least 1 match

# Verify docker-compose has postgres
Select-String -Path docker-compose.yml -Pattern 'postgres'
# Expected: multiple matches
```

**PASS criteria:** All 5 tables modeled, migration exists, audit service wired, NO_TRADE persisted, DB in docker-compose.

---

## G4 — Backfill ≥60 Sessions for Top-20 Symbols

```powershell
# Verify universe config has 20 symbols
Select-String -Path backend/app/data/universe.py -Pattern 'DEFAULT_UNIVERSE'
# Expected: list with 20 entries

# Verify backfill CLI exists
Test-Path backend/app/cli/backfill.py
# Expected: True

# Run backfill (requires network access to ngnmarket.com)
cd backend
python -m app.cli.backfill --min-sessions 60
# Expected: verification report showing PASS for each symbol

# Run G4 unit tests (no network required)
python -m pytest tests/test_g4_backfill.py -v
# Expected: all tests pass

# After backfill, verify storage has data
python -c "from app.data.historical.storage import get_historical_storage; s=get_historical_storage(); print(s.get_stats())"
# Expected: total_symbols >= 20, total_records >= 1200
```

**PASS criteria:** 20-symbol universe, backfill CLI runs, verification report shows all PASS, ≥60 sessions per symbol + ASI.

---

## Full Gate Check (all at once)

```powershell
cd backend
python -m pytest tests/test_confidence_consolidated.py tests/test_g1_real_ohlcv.py tests/test_g4_backfill.py -v --tb=short
```

All tests must pass. Then run the backfill to populate real data.
