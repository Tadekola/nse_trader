"""
API tests for Summary Endpoint (Milestone D — PR1).

Covers:
  1. GET /portfolios/{id}/summary — 200 with full response contract
  2. USD reporting with FX data
  3. REAL_NGN reporting with CPI data
  4. Degraded quality when FX/CPI missing
  5. Error handling — 404, invalid reporting mode
  6. Return windows + concentration in response
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
    now = datetime.now(timezone.utc)

    session.add(Portfolio(id=1, name="Test Portfolio", base_currency="NGN"))

    txs = [
        PortfolioTransaction(id=1, portfolio_id=1, ts=date(2024, 1, 2),
            tx_type="CASH_IN", amount_ngn=1_000_000, fees_ngn=0),
        PortfolioTransaction(id=2, portfolio_id=1, ts=date(2024, 1, 3),
            symbol="DANGCEM", tx_type="BUY", quantity=1000, price_ngn=350.0,
            amount_ngn=-350_000, fees_ngn=0),
        PortfolioTransaction(id=3, portfolio_id=1, ts=date(2024, 1, 3),
            symbol="GTCO", tx_type="BUY", quantity=500, price_ngn=40.0,
            amount_ngn=-20_000, fees_ngn=0),
    ]
    for tx in txs:
        session.add(tx)

    # Prices: 5 trading days (2024-01-02 to 2024-01-06)
    for i in range(5):
        d = date(2024, 1, 2 + i)
        session.add(AdjustedPrice(
            id=i + 1, symbol="DANGCEM", ts=d,
            close_raw=350 + i * 5, adj_factor=1.0, adj_close=350 + i * 5,
            tri=1000 + i * 15, tri_quality="FULL", computed_at=now,
        ))
        session.add(AdjustedPrice(
            id=10 + i, symbol="GTCO", ts=d,
            close_raw=40 + i * 0.5, adj_factor=1.0, adj_close=40 + i * 0.5,
            tri=500 + i * 3, tri_quality="FULL", computed_at=now,
        ))

    # FX rates (Naira weakening)
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


# ── 1. NGN Summary ──────────────────────────────────────────────────


class TestNGNSummaryAPI:

    @pytest.mark.asyncio
    async def test_summary_200(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/summary?as_of=2024-01-06&reporting=NGN"
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_response_contract(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/summary?as_of=2024-01-06&reporting=NGN"
            )
        body = resp.json()
        for field in [
            "portfolio_id", "as_of", "reporting", "value_ngn",
            "value_reporting", "cash_ngn", "holdings_value_ngn",
            "total_invested_ngn", "returns", "current_drawdown",
            "top_holdings", "concentration", "freshness", "quality",
            "provenance",
        ]:
            assert field in body, f"Missing field: {field}"

        assert body["portfolio_id"] == 1
        assert body["reporting"] == "NGN"
        assert body["as_of"] == "2024-01-06"

    @pytest.mark.asyncio
    async def test_valuation_correct(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/summary?as_of=2024-01-06&reporting=NGN"
            )
        body = resp.json()
        # DANGCEM: 1000 * 370 = 370000, GTCO: 500 * 42 = 21000
        # Cash: 1M - 350K - 20K = 630K
        # Total: 370K + 21K + 630K = 1021K
        assert abs(body["holdings_value_ngn"] - 391_000) < 1
        assert abs(body["cash_ngn"] - 630_000) < 1
        assert abs(body["value_ngn"] - 1_021_000) < 1

    @pytest.mark.asyncio
    async def test_returns_present(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/summary?as_of=2024-01-06&reporting=NGN"
            )
        returns = resp.json()["returns"]
        labels = {r["label"] for r in returns}
        assert labels == {"YTD", "1Y", "3Y", "SINCE_INCEPTION"}

    @pytest.mark.asyncio
    async def test_concentration_present(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/summary?as_of=2024-01-06&reporting=NGN"
            )
        conc = resp.json()["concentration"]
        assert "hhi" in conc
        assert "max_position_weight" in conc
        assert "max_position_symbol" in conc
        assert "num_positions" in conc
        assert conc["num_positions"] == 2

    @pytest.mark.asyncio
    async def test_top_holdings_present(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/summary?as_of=2024-01-06&reporting=NGN"
            )
        holdings = resp.json()["top_holdings"]
        assert len(holdings) == 2
        assert holdings[0]["symbol"] == "DANGCEM"
        for h in holdings:
            assert "shares" in h
            assert "market_value_ngn" in h
            assert "weight" in h
            assert "tri_quality" in h

    @pytest.mark.asyncio
    async def test_freshness_present(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/summary?as_of=2024-01-06&reporting=NGN"
            )
        fresh = resp.json()["freshness"]
        assert fresh["last_price_date"] is not None


# ── 2. USD Summary ──────────────────────────────────────────────────


class TestUSDSummaryAPI:

    @pytest.mark.asyncio
    async def test_usd_summary_200(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/summary?as_of=2024-01-06&reporting=USD"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["reporting"] == "USD"
        assert body["value_reporting"] is not None
        assert body["quality"]["fx_mode"] == "FX_FULL"

    @pytest.mark.asyncio
    async def test_usd_value_conversion(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/summary?as_of=2024-01-06&reporting=USD"
            )
        body = resp.json()
        # FX rate on 2024-01-06 = 900 + 4*25 = 1000
        # value_reporting = 1021000 / 1000 = 1021
        assert abs(body["value_reporting"] - 1021.0) < 1


# ── 3. REAL_NGN Summary ─────────────────────────────────────────────


class TestRealNGNSummaryAPI:

    @pytest.mark.asyncio
    async def test_real_ngn_summary_200(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/summary?as_of=2024-01-06&reporting=REAL_NGN"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["reporting"] == "REAL_NGN"
        assert body["quality"]["inflation_mode"] == "CPI_FULL"


# ── 4. Degraded ─────────────────────────────────────────────────────


class TestDegradedSummaryAPI:

    @pytest.mark.asyncio
    async def test_usd_degraded_no_fx(self, empty_app, session):
        session.add(Portfolio(id=1, name="Test", base_currency="NGN"))
        session.add(PortfolioTransaction(
            id=1, portfolio_id=1, ts=date(2024, 1, 2),
            tx_type="CASH_IN", amount_ngn=100_000, fees_ngn=0,
        ))
        await session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=empty_app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/summary?as_of=2024-01-06&reporting=USD"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["quality"]["fx_mode"] == "FX_MISSING"
        assert body["quality"]["overall_quality"] == "DEGRADED"
        assert body["value_reporting"] is None


# ── 5. Errors ────────────────────────────────────────────────────────


class TestSummaryErrors:

    @pytest.mark.asyncio
    async def test_invalid_reporting(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/summary?reporting=BITCOIN"
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_404_no_transactions(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios/999/summary")
        assert resp.status_code == 404
