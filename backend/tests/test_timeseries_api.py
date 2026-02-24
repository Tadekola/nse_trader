"""
API tests for Timeseries Endpoint (Milestone D — PR2).

Covers:
  1. GET /portfolios/{id}/timeseries — 200 with full response contract
  2. USD reporting with FX data
  3. REAL_NGN reporting with CPI data
  4. Date range filtering
  5. Error handling — 404, invalid reporting mode
"""

import os
import sys
import pytest
import pytest_asyncio
from datetime import date, datetime

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
    AdjustedPrice, Base, FxRate, MacroSeries, OHLCVPrice,
    Portfolio, PortfolioTransaction,
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
    """Seed with portfolio, transactions, prices, FX, CPI for 5 trading days."""
    now = datetime.utcnow()

    session.add(Portfolio(id=1, name="Test Portfolio", base_currency="NGN"))

    txs = [
        PortfolioTransaction(id=1, portfolio_id=1, ts=date(2024, 1, 2),
            tx_type="CASH_IN", amount_ngn=1_000_000, fees_ngn=0),
        PortfolioTransaction(id=2, portfolio_id=1, ts=date(2024, 1, 3),
            symbol="DANGCEM", tx_type="BUY", quantity=1000, price_ngn=350.0,
            amount_ngn=-350_000, fees_ngn=0),
    ]
    for tx in txs:
        session.add(tx)

    # Prices: 5 trading days
    for i in range(5):
        d = date(2024, 1, 2 + i)
        session.add(AdjustedPrice(
            id=i + 1, symbol="DANGCEM", ts=d,
            close_raw=350 + i * 5, adj_factor=1.0, adj_close=350 + i * 5,
            tri=1000 + i * 15, tri_quality="FULL", computed_at=now,
        ))

    # FX rates
    for i in range(5):
        d = date(2024, 1, 2 + i)
        session.add(FxRate(
            id=i + 1, pair="USDNGN", ts=d,
            rate=900.0 + i * 25, source="CBN", ingested_at=now,
        ))

    # CPI data
    session.add(MacroSeries(
        id=1, series_name="CPI_NGN", ts=date(2024, 1, 1),
        value=130.0, frequency="MONTHLY", source="NBS", ingested_at=now,
    ))

    await session.commit()
    return session


@pytest_asyncio.fixture
async def app_with_session(seeded_session):
    from fastapi import FastAPI
    from app.api.v1.portfolios import router
    from app.db.engine import get_async_session

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    async def override_session():
        yield seeded_session

    test_app.dependency_overrides[get_async_session] = override_session
    return test_app


@pytest_asyncio.fixture
async def empty_app(session):
    from fastapi import FastAPI
    from app.api.v1.portfolios import router
    from app.db.engine import get_async_session

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    async def override():
        yield session

    test_app.dependency_overrides[get_async_session] = override
    return test_app


# ── 1. NGN Timeseries ───────────────────────────────────────────────


class TestNGNTimeseriesAPI:

    @pytest.mark.asyncio
    async def test_timeseries_200(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/timeseries?start=2024-01-02&end=2024-01-06&reporting=NGN"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_response_contract(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/timeseries?start=2024-01-02&end=2024-01-06"
            )
        body = resp.json()
        for field in ["reporting", "start_date", "end_date", "num_points",
                       "quality", "series", "provenance"]:
            assert field in body, f"Missing field: {field}"

        assert body["num_points"] == len(body["series"])
        assert body["num_points"] > 0

        point = body["series"][0]
        for field in ["date", "value", "value_ngn", "cumulative_return",
                       "drawdown", "rolling_vol_30d"]:
            assert field in point, f"Missing point field: {field}"

    @pytest.mark.asyncio
    async def test_series_values(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/timeseries?start=2024-01-02&end=2024-01-06&reporting=NGN"
            )
        series = resp.json()["series"]
        # First point: cash 1M, no holdings
        assert abs(series[0]["value"] - 1_000_000) < 1
        # Last point: cash 650K + 1000*370 = 1,020,000
        assert abs(series[-1]["value"] - 1_020_000) < 1

    @pytest.mark.asyncio
    async def test_cumulative_return_starts_zero(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/timeseries?start=2024-01-02&end=2024-01-06"
            )
        series = resp.json()["series"]
        assert series[0]["cumulative_return"] == 0.0

    @pytest.mark.asyncio
    async def test_drawdown_zero_uptrend(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/timeseries?start=2024-01-02&end=2024-01-06"
            )
        series = resp.json()["series"]
        for point in series:
            assert point["drawdown"] < 0.01


# ── 2. USD Timeseries ───────────────────────────────────────────────


class TestUSDTimeseriesAPI:

    @pytest.mark.asyncio
    async def test_usd_timeseries(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/timeseries?start=2024-01-02&end=2024-01-06&reporting=USD"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["reporting"] == "USD"
        assert body["quality"]["fx_mode"] == "FX_FULL"
        # First value: 1M / 900 ≈ 1111.11
        assert abs(body["series"][0]["value"] - 1_000_000 / 900) < 1


# ── 3. REAL_NGN Timeseries ──────────────────────────────────────────


class TestRealNGNTimeseriesAPI:

    @pytest.mark.asyncio
    async def test_real_ngn_timeseries(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/timeseries?start=2024-01-02&end=2024-01-06&reporting=REAL_NGN"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["reporting"] == "REAL_NGN"
        assert body["quality"]["inflation_mode"] == "CPI_FULL"


# ── 4. Errors ────────────────────────────────────────────────────────


class TestTimeseriesErrors:

    @pytest.mark.asyncio
    async def test_invalid_reporting(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/timeseries?reporting=EURO"
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_404_no_transactions(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios/999/timeseries")
        assert resp.status_code == 404
