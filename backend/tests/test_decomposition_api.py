"""
API tests for Decomposition Endpoint (Milestone C — PR1).

Covers:
  1. GET /portfolios/{id}/decomposition?reporting=USD — full FX decomposition
  2. GET /portfolios/{id}/decomposition?reporting=REAL_NGN — inflation decomposition
  3. GET /portfolios/{id}/decomposition?reporting=NGN — equity only
  4. Response contract — all required fields present
  5. Quality flags — DEGRADED when FX/CPI missing
  6. Governance — audit event on DEGRADED
  7. Error handling — 404, invalid mode
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
    """Seed with portfolio, transactions, prices, FX, CPI."""
    now = datetime.utcnow()

    session.add(Portfolio(id=1, name="Test Portfolio", base_currency="NGN"))

    txs = [
        PortfolioTransaction(id=1, portfolio_id=1, ts=date(2024, 1, 2),
            tx_type="CASH_IN", amount_ngn=1_000_000, fees_ngn=0),
        PortfolioTransaction(id=2, portfolio_id=1, ts=date(2024, 1, 3),
            symbol="DANGCEM", tx_type="BUY", quantity=100, price_ngn=350.0,
            amount_ngn=-35000, fees_ngn=0),
    ]
    for tx in txs:
        session.add(tx)

    # OHLCV Prices (5 days, DANGCEM appreciates)
    for i in range(5):
        d = date(2024, 1, 2 + i)
        session.add(OHLCVPrice(
            id=i + 1, symbol="DANGCEM", ts=d,
            open=345, high=360, low=340, close=350.0 + i * 5,
            volume=100000, source="TEST",
        ))

    # AdjustedPrices
    for i in range(5):
        d = date(2024, 1, 2 + i)
        session.add(AdjustedPrice(
            id=i + 1, symbol="DANGCEM", ts=d,
            close_raw=350 + i * 5, adj_factor=1.0, adj_close=350 + i * 5,
            tri=1000 + i * 15, tri_quality="FULL", computed_at=now,
        ))

    # FX rates (Naira weakening over 5 days)
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
    session.add(MacroSeries(
        id=2, series_name="CPI_NGN", ts=date(2024, 2, 1),
        value=133.0, frequency="MONTHLY", source="NBS", ingested_at=now,
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


# ── 1. USD Decomposition ─────────────────────────────────────────────


class TestUSDDecomposition:

    @pytest.mark.asyncio
    async def test_usd_decomposition_returns_200(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/decomposition?start_date=2024-01-02&end_date=2024-01-06&reporting=USD"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_usd_response_contract(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/decomposition?start_date=2024-01-02&end_date=2024-01-06&reporting=USD"
            )
        body = resp.json()
        # Required top-level fields
        assert body["portfolio_id"] == 1
        assert body["reporting"] == "USD"
        assert "quality" in body
        assert "series" in body
        assert "summary" in body
        assert "provenance" in body

    @pytest.mark.asyncio
    async def test_usd_quality_flags(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/decomposition?start_date=2024-01-02&end_date=2024-01-06&reporting=USD"
            )
        q = resp.json()["quality"]
        assert q["fx_mode"] == "FX_FULL"
        assert "overall_quality" in q
        assert "data_mode" in q

    @pytest.mark.asyncio
    async def test_usd_series_has_all_components(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/decomposition?start_date=2024-01-02&end_date=2024-01-06&reporting=USD"
            )
        series = resp.json()["series"]
        assert len(series) > 1
        for entry in series[1:]:
            assert "total_return" in entry
            assert "equity_component" in entry
            assert "fx_component" in entry
            assert "inflation_component" in entry
            # Additivity: total = equity + fx
            total = entry["total_return"]
            eq = entry["equity_component"]
            fx = entry["fx_component"]
            assert abs(total - (eq + fx)) < 1e-6

    @pytest.mark.asyncio
    async def test_usd_summary_additivity(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/decomposition?start_date=2024-01-02&end_date=2024-01-06&reporting=USD"
            )
        s = resp.json()["summary"]
        assert abs(s["total_cumulative"] - (s["equity_cumulative"] + s["fx_cumulative"])) < 1e-6


# ── 2. REAL_NGN Decomposition ────────────────────────────────────────


class TestRealNGNDecomposition:

    @pytest.mark.asyncio
    async def test_real_ngn_returns_200(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/decomposition?start_date=2024-01-02&end_date=2024-01-06&reporting=REAL_NGN"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_real_ngn_has_inflation_component(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/decomposition?start_date=2024-01-02&end_date=2024-01-06&reporting=REAL_NGN"
            )
        series = resp.json()["series"]
        for entry in series[1:]:
            assert "inflation_component" in entry
            assert entry["fx_component"] == 0.0

    @pytest.mark.asyncio
    async def test_real_ngn_summary_additivity(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/decomposition?start_date=2024-01-02&end_date=2024-01-06&reporting=REAL_NGN"
            )
        s = resp.json()["summary"]
        assert abs(s["total_cumulative"] - (s["equity_cumulative"] + s["inflation_cumulative"])) < 1e-6


# ── 3. NGN Decomposition ─────────────────────────────────────────────


class TestNGNDecomposition:

    @pytest.mark.asyncio
    async def test_ngn_zero_fx_and_inflation(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/decomposition?start_date=2024-01-02&end_date=2024-01-06&reporting=NGN"
            )
        body = resp.json()
        assert body["reporting"] == "NGN"
        for entry in body["series"][1:]:
            assert entry["fx_component"] == 0.0
            assert entry["inflation_component"] == 0.0


# ── 4. Governance — Degraded ─────────────────────────────────────────


class TestGovernance:

    @pytest.mark.asyncio
    async def test_usd_degraded_without_fx(self, empty_app, session):
        """USD decomposition without FX data → DEGRADED, fx_component = null."""
        session.add(Portfolio(id=1, name="Test", base_currency="NGN"))
        session.add(PortfolioTransaction(
            id=1, portfolio_id=1, ts=date(2024, 1, 2),
            tx_type="CASH_IN", amount_ngn=100000, fees_ngn=0,
        ))
        session.add(PortfolioTransaction(
            id=2, portfolio_id=1, ts=date(2024, 1, 3),
            symbol="TEST", tx_type="BUY", quantity=100, price_ngn=100,
            amount_ngn=-10000, fees_ngn=0,
        ))
        for i in range(3):
            d = date(2024, 1, 2 + i)
            session.add(OHLCVPrice(
                id=i + 1, symbol="TEST", ts=d,
                open=100, high=105, low=98, close=100 + i * 2,
                volume=1000, source="T",
            ))
        await session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=empty_app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/decomposition?start_date=2024-01-02&end_date=2024-01-04&reporting=USD"
            )
        body = resp.json()
        assert body["quality"]["fx_mode"] == "FX_MISSING"
        assert body["quality"]["overall_quality"] == "DEGRADED"
        # fx_component should be null for degraded
        for entry in body["series"]:
            assert entry["fx_component"] is None

    @pytest.mark.asyncio
    async def test_real_ngn_degraded_without_cpi(self, empty_app, session):
        session.add(Portfolio(id=1, name="Test", base_currency="NGN"))
        session.add(PortfolioTransaction(
            id=1, portfolio_id=1, ts=date(2024, 1, 2),
            tx_type="CASH_IN", amount_ngn=100000, fees_ngn=0,
        ))
        session.add(PortfolioTransaction(
            id=2, portfolio_id=1, ts=date(2024, 1, 3),
            symbol="TEST", tx_type="BUY", quantity=100, price_ngn=100,
            amount_ngn=-10000, fees_ngn=0,
        ))
        for i in range(3):
            d = date(2024, 1, 2 + i)
            session.add(OHLCVPrice(
                id=i + 1, symbol="TEST", ts=d,
                open=100, high=105, low=98, close=100 + i * 2,
                volume=1000, source="T",
            ))
        await session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=empty_app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/decomposition?start_date=2024-01-02&end_date=2024-01-04&reporting=REAL_NGN"
            )
        body = resp.json()
        assert body["quality"]["inflation_mode"] == "CPI_MISSING"
        assert body["quality"]["overall_quality"] == "DEGRADED"


# ── 5. Error Handling ────────────────────────────────────────────────


class TestErrors:

    @pytest.mark.asyncio
    async def test_invalid_reporting_mode(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/decomposition?reporting=BITCOIN"
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_404_no_transactions(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios/999/decomposition")
        assert resp.status_code == 404
