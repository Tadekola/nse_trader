"""
Tests for Signal Audit Queryability (P3-2).

Uses an in-memory SQLite async engine to test:
  1. Signals — filtering by symbol, status, direction, date range + pagination
  2. No-Trade events — filtering by symbol, reason_code, scope, date range
  3. Audit events — filtering by component, event_type, level, date range
  4. CSV export — correct headers, row count, content-type
  5. Pagination — limit/offset, total count accuracy
  6. Helper functions — _row_to_dict, _build_csv, _clamp_limit
"""

import csv
import io
import json
import sys
import os
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Render JSONB as JSON (TEXT) on SQLite so models with JSONB columns can be created
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"

from app.db.models import AuditEvent, Base, NoTradeEvent, Signal
from app.api.v1.audit import _build_csv, _clamp_limit, _row_to_dict


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def async_engine():
    """Create an in-memory SQLite async engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    # SQLite needs PRAGMA for FK support
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(async_engine):
    """Provide a fresh async session for each test."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest_asyncio.fixture
async def seeded_session(session):
    """Seed the DB with test data and return the session."""
    now = datetime.utcnow()

    # Signals
    for i in range(25):
        sig = Signal(
            id=i + 1,
            signal_id=f"sig_{i:03d}",
            symbol="DANGCEM" if i < 15 else "GTCO",
            as_of=now - timedelta(days=i),
            strategy="momentum",
            horizon="short_term",
            direction="bullish" if i % 2 == 0 else "bearish",
            confidence=0.8,
            bias_probability=70 if i % 2 == 0 else 30,
            status="ACTIVE" if i < 20 else "SUPPRESSED",
            params={"version": 1},
            provenance={"source": "ngnmarket", "ingested_at": now.isoformat()},
            created_at=now - timedelta(days=i),
        )
        session.add(sig)

    # No-Trade events
    for i in range(10):
        nte = NoTradeEvent(
            id=i + 1,
            ts=now - timedelta(days=i),
            scope="symbol" if i < 7 else "system",
            symbol="ZENITH" if i < 5 else None,
            reason_code="STALE_DATA" if i < 6 else "CIRCUIT_BREAKER_ACTIVE",
            detail=f"Test detail {i}",
            confidence=0.3,
            provenance={"source": "test"},
        )
        session.add(nte)

    # Audit events
    for i in range(15):
        ae = AuditEvent(
            id=i + 1,
            ts=now - timedelta(days=i),
            component="reconciliation" if i < 8 else "scheduler",
            level="INFO" if i < 10 else "WARN",
            event_type="RECONCILIATION_UPDATE" if i < 8 else "SCHEDULED_RUN",
            message=f"Test audit message {i}",
            payload={"index": i},
        )
        session.add(ae)

    await session.commit()
    return session


@pytest_asyncio.fixture
async def app_with_session(seeded_session):
    """Create a FastAPI test app with overridden DB session dependency."""
    from fastapi import FastAPI
    from app.api.v1.audit import router
    from app.db.engine import get_async_session

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    async def override_session():
        yield seeded_session

    test_app.dependency_overrides[get_async_session] = override_session
    return test_app


# ── 1. Helper unit tests ────────────────────────────────────────────


class TestHelpers:

    def test_clamp_limit_within_range(self):
        assert _clamp_limit(50) == 50

    def test_clamp_limit_too_high(self):
        assert _clamp_limit(1000) == 500

    def test_clamp_limit_too_low(self):
        assert _clamp_limit(0) == 1
        assert _clamp_limit(-5) == 1

    def test_build_csv_basic(self):
        rows = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        output = _build_csv(rows, ["name", "age"])
        reader = csv.DictReader(io.StringIO(output))
        data = list(reader)
        assert len(data) == 2
        assert data[0]["name"] == "Alice"
        assert data[1]["age"] == "25"

    def test_build_csv_nested_json(self):
        rows = [{"name": "X", "meta": {"key": "val"}}]
        output = _build_csv(rows, ["name", "meta"])
        reader = csv.DictReader(io.StringIO(output))
        data = list(reader)
        assert json.loads(data[0]["meta"]) == {"key": "val"}

    def test_build_csv_empty(self):
        output = _build_csv([], ["a", "b"])
        lines = output.strip().split("\n")
        assert len(lines) == 1  # header only


# ── 2. Signals endpoint tests ───────────────────────────────────────


class TestSignalsEndpoint:

    @pytest.mark.asyncio
    async def test_list_all_signals(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/signals")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 25
        assert len(body["data"]) == 25  # default limit=50 > 25 rows

    @pytest.mark.asyncio
    async def test_filter_by_symbol(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/signals?symbol=DANGCEM")
        body = resp.json()
        assert body["total"] == 15
        for row in body["data"]:
            assert row["symbol"] == "DANGCEM"

    @pytest.mark.asyncio
    async def test_filter_by_status(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/signals?status=SUPPRESSED")
        body = resp.json()
        assert body["total"] == 5

    @pytest.mark.asyncio
    async def test_filter_by_direction(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/signals?direction=bullish")
        body = resp.json()
        # i=0,2,4,...,24 → 13 bullish
        assert body["total"] == 13

    @pytest.mark.asyncio
    async def test_pagination(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/signals?limit=5&offset=0")
        body = resp.json()
        assert body["total"] == 25
        assert body["limit"] == 5
        assert body["offset"] == 0
        assert len(body["data"]) == 5

    @pytest.mark.asyncio
    async def test_pagination_offset(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            page1 = await client.get("/api/v1/audit/signals?limit=5&offset=0")
            page2 = await client.get("/api/v1/audit/signals?limit=5&offset=5")
        ids1 = {r["id"] for r in page1.json()["data"]}
        ids2 = {r["id"] for r in page2.json()["data"]}
        assert ids1.isdisjoint(ids2)  # no overlap

    @pytest.mark.asyncio
    async def test_date_range_filter(self, app_with_session):
        now = datetime.utcnow()
        start = (now - timedelta(days=5)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get(f"/api/v1/audit/signals?start_date={start}&end_date={end}")
        body = resp.json()
        assert body["total"] <= 6  # days 0..5

    @pytest.mark.asyncio
    async def test_signals_csv(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/signals/csv?symbol=DANGCEM")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 15
        assert "signal_id" in rows[0]
        assert "provenance" in rows[0]


# ── 3. No-Trade endpoint tests ──────────────────────────────────────


class TestNoTradeEndpoint:

    @pytest.mark.asyncio
    async def test_list_all(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/no-trade")
        body = resp.json()
        assert body["total"] == 10

    @pytest.mark.asyncio
    async def test_filter_by_reason_code(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/no-trade?reason_code=STALE_DATA")
        body = resp.json()
        assert body["total"] == 6

    @pytest.mark.asyncio
    async def test_filter_by_symbol(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/no-trade?symbol=ZENITH")
        body = resp.json()
        assert body["total"] == 5

    @pytest.mark.asyncio
    async def test_filter_by_scope(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/no-trade?scope=system")
        body = resp.json()
        assert body["total"] == 3

    @pytest.mark.asyncio
    async def test_no_trade_csv(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/no-trade/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 10
        assert "reason_code" in rows[0]


# ── 4. Audit Events endpoint tests ──────────────────────────────────


class TestAuditEventsEndpoint:

    @pytest.mark.asyncio
    async def test_list_all(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/events")
        body = resp.json()
        assert body["total"] == 15

    @pytest.mark.asyncio
    async def test_filter_by_component(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/events?component=reconciliation")
        body = resp.json()
        assert body["total"] == 8

    @pytest.mark.asyncio
    async def test_filter_by_event_type(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/events?event_type=SCHEDULED_RUN")
        body = resp.json()
        assert body["total"] == 7

    @pytest.mark.asyncio
    async def test_filter_by_level(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/events?level=WARN")
        body = resp.json()
        assert body["total"] == 5

    @pytest.mark.asyncio
    async def test_audit_events_csv(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/events/csv?component=scheduler")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 7
        assert "event_type" in rows[0]
        assert "payload" in rows[0]

    @pytest.mark.asyncio
    async def test_combined_filters(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/audit/events?component=scheduler&level=WARN")
        body = resp.json()
        assert body["total"] == 5
        for row in body["data"]:
            assert row["component"] == "scheduler"
            assert row["level"] == "WARN"
