"""
Tests for Total Return & Corporate Actions API (Milestone A — PR3).

Covers:
  1. GET /tickers/{symbol}/total-return — series, filtering, pagination, tri_quality
  2. GET /tickers/{symbol}/corporate-actions — listing, filtering by type/date
  3. GET /tickers/{symbol}/price-discontinuities — detection, EXPLAINED vs UNEXPLAINED
  4. Governance: PRICE_ONLY labeling, provenance in responses
  5. 404 when no data
"""

import os
import sys
import pytest
import pytest_asyncio
from datetime import date, datetime, timezone

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

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"

from app.db.models import (
    AdjustedPrice, AuditEvent, Base, CorporateAction, OHLCVPrice,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(async_engine):
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest_asyncio.fixture
async def seeded_session(session):
    """Seed with OHLCV, corporate actions, and adjusted prices for DANGCEM."""
    now = datetime.now(timezone.utc)

    # OHLCV prices: 10 days
    for i in range(10):
        d = date(2024, 1, 2 + i)
        close = 300.0 + i * 5  # 300, 305, ..., 345
        if i == 5:
            close = 155.0  # simulate split day (price halves ~from 325)
        session.add(OHLCVPrice(
            id=i + 1, symbol="DANGCEM", ts=d,
            open=close - 1, high=close + 2, low=close - 2, close=close,
            volume=100000, source="TEST",
        ))

    # Corporate actions
    session.add(CorporateAction(
        id=1, symbol="DANGCEM", action_type="CASH_DIVIDEND",
        ex_date=date(2024, 1, 4), amount=10.0, source="TEST",
        ingested_at=now, provenance={"source": "test"},
    ))
    session.add(CorporateAction(
        id=2, symbol="DANGCEM", action_type="STOCK_SPLIT",
        ex_date=date(2024, 1, 7), ratio_from=1, ratio_to=2,
        source="TEST", ingested_at=now, provenance={"source": "test"},
    ))
    session.add(CorporateAction(
        id=3, symbol="DANGCEM", action_type="CASH_DIVIDEND",
        ex_date=date(2024, 1, 9), amount=5.0, source="TEST",
        ingested_at=now, provenance={"source": "test"},
    ))

    # Adjusted prices (pre-computed by TRI engine)
    for i in range(10):
        d = date(2024, 1, 2 + i)
        close = 300.0 + i * 5
        if i == 5:
            close = 155.0
        af = 1.0 if i < 5 else 2.0
        session.add(AdjustedPrice(
            id=i + 1, symbol="DANGCEM", ts=d,
            close_raw=close, adj_factor=af,
            adj_close=close * af,
            tri=1000.0 + i * 10,  # simplified
            daily_return_price=0.01 if i > 0 else None,
            daily_return_total=0.012 if i > 0 else None,
            tri_quality="FULL",
            computed_at=now,
            provenance={"source": "tri_engine"},
        ))

    # Add some OHLCV for GTCO (no corp actions → PRICE_ONLY)
    for i in range(5):
        d = date(2024, 1, 2 + i)
        session.add(OHLCVPrice(
            id=20 + i, symbol="GTCO", ts=d,
            open=50.0, high=52.0, low=49.0, close=50.0 + i,
            volume=50000, source="TEST",
        ))
    for i in range(5):
        d = date(2024, 1, 2 + i)
        session.add(AdjustedPrice(
            id=20 + i, symbol="GTCO", ts=d,
            close_raw=50.0 + i, adj_factor=1.0,
            adj_close=50.0 + i, tri=1000.0 + i * 5,
            daily_return_price=0.01 if i > 0 else None,
            daily_return_total=0.01 if i > 0 else None,
            tri_quality="PRICE_ONLY",
            computed_at=now,
            provenance={"source": "tri_engine"},
        ))

    await session.commit()
    return session


@pytest_asyncio.fixture
async def app_with_session(seeded_session):
    from fastapi import FastAPI
    from app.api.v1.total_return import router
    from app.db.engine import get_async_session

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    async def override_session():
        yield seeded_session

    test_app.dependency_overrides[get_async_session] = override_session
    return test_app


# ── 1. Total Return endpoint ────────────────────────────────────────


class TestTotalReturnEndpoint:

    @pytest.mark.asyncio
    async def test_get_total_return(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/tickers/DANGCEM/total-return")
        assert resp.status_code == 200
        body = resp.json()
        assert body["symbol"] == "DANGCEM"
        assert body["total"] == 10
        assert body["tri_quality"] == "FULL"
        assert len(body["data"]) == 10
        assert "provenance" in body

    @pytest.mark.asyncio
    async def test_total_return_date_filter(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                "/api/v1/tickers/DANGCEM/total-return?start_date=2024-01-05&end_date=2024-01-08"
            )
        body = resp.json()
        assert body["total"] == 4

    @pytest.mark.asyncio
    async def test_total_return_pagination(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                "/api/v1/tickers/DANGCEM/total-return?limit=3&offset=0"
            )
        body = resp.json()
        assert body["total"] == 10
        assert len(body["data"]) == 3
        assert body["limit"] == 3

    @pytest.mark.asyncio
    async def test_total_return_price_only_quality(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/tickers/GTCO/total-return")
        body = resp.json()
        assert body["tri_quality"] == "PRICE_ONLY"
        assert "PRICE_ONLY" in body["provenance"]["note"]

    @pytest.mark.asyncio
    async def test_total_return_404_missing(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/tickers/NOSYMBOL/total-return")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_total_return_data_fields(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/tickers/DANGCEM/total-return?limit=1")
        row = resp.json()["data"][0]
        expected_keys = {
            "id", "symbol", "ts", "close_raw", "adj_factor", "adj_close",
            "tri", "daily_return_price", "daily_return_total",
            "tri_quality", "computed_at", "provenance",
        }
        assert expected_keys.issubset(set(row.keys()))


# ── 2. Corporate Actions endpoint ───────────────────────────────────


class TestCorporateActionsEndpoint:

    @pytest.mark.asyncio
    async def test_get_all_actions(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/tickers/DANGCEM/corporate-actions")
        body = resp.json()
        assert body["total"] == 3
        assert body["symbol"] == "DANGCEM"

    @pytest.mark.asyncio
    async def test_filter_by_type(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                "/api/v1/tickers/DANGCEM/corporate-actions?action_type=CASH_DIVIDEND"
            )
        body = resp.json()
        assert body["total"] == 2
        for row in body["data"]:
            assert row["action_type"] == "CASH_DIVIDEND"

    @pytest.mark.asyncio
    async def test_filter_by_date_range(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                "/api/v1/tickers/DANGCEM/corporate-actions?start_date=2024-01-06&end_date=2024-01-10"
            )
        body = resp.json()
        # Only split (Jan 7) and dividend (Jan 9) in range
        assert body["total"] == 2

    @pytest.mark.asyncio
    async def test_no_actions_returns_empty(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/tickers/GTCO/corporate-actions")
        body = resp.json()
        assert body["total"] == 0
        assert body["data"] == []


# ── 3. Price Discontinuity Detection ────────────────────────────────


class TestPriceDiscontinuities:

    @pytest.mark.asyncio
    async def test_detects_split_as_explained(self, app_with_session):
        """The ~52% price drop on Jan 7 (split day) should be EXPLAINED."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                "/api/v1/tickers/DANGCEM/price-discontinuities?threshold=0.30"
            )
        body = resp.json()
        assert body["total"] >= 1
        # Find the split-day discontinuity
        split_disc = [d for d in body["discontinuities"] if d["date"] == "2024-01-07"]
        assert len(split_disc) == 1
        assert split_disc[0]["status"] == "EXPLAINED"
        assert split_disc[0]["has_corporate_action"] is True

    @pytest.mark.asyncio
    async def test_no_discontinuities_in_smooth_series(self, app_with_session):
        """GTCO has smooth prices, no discontinuities expected."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/tickers/GTCO/price-discontinuities")
        body = resp.json()
        assert body["total"] == 0

    @pytest.mark.asyncio
    async def test_empty_symbol(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/tickers/NOSYMBOL/price-discontinuities")
        body = resp.json()
        assert body["total"] == 0


# ── 4. Provenance & Governance ───────────────────────────────────────


class TestGovernance:

    @pytest.mark.asyncio
    async def test_provenance_in_total_return(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/tickers/DANGCEM/total-return")
        body = resp.json()
        assert "provenance" in body
        assert body["provenance"]["source"] == "adjusted_prices"
        assert "tri_quality" in body["provenance"]

    @pytest.mark.asyncio
    async def test_price_only_note_in_provenance(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/tickers/GTCO/total-return")
        note = resp.json()["provenance"]["note"]
        assert "PRICE_ONLY" in note
        assert "no dividend data" in note.lower()
