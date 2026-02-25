"""
Tests for Portfolio API (Milestone B — PR4).

Covers:
  1. POST /portfolios — create portfolio
  2. GET /portfolios — list portfolios
  3. GET /portfolios/{id} — get portfolio, 404
  4. POST /portfolios/{id}/transactions — add bulk, validation errors
  5. GET /portfolios/{id}/transactions — list with filters
  6. GET /portfolios/{id}/holdings — holdings + valuation
  7. GET /portfolios/{id}/performance — NGN, USD, REAL_NGN modes + quality flags
  8. Governance — DEGRADED when FX/CPI missing, audit trail
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
    """Seed with portfolio, transactions, prices, FX, CPI."""
    now = datetime.now(timezone.utc)

    # Portfolio
    session.add(Portfolio(id=1, name="Test Portfolio", base_currency="NGN"))

    # Transactions
    txs = [
        PortfolioTransaction(id=1, portfolio_id=1, ts=date(2024, 1, 2),
            tx_type="CASH_IN", amount_ngn=1_000_000, fees_ngn=0),
        PortfolioTransaction(id=2, portfolio_id=1, ts=date(2024, 1, 3),
            symbol="DANGCEM", tx_type="BUY", quantity=100, price_ngn=350.0,
            amount_ngn=-35000, fees_ngn=175),
        PortfolioTransaction(id=3, portfolio_id=1, ts=date(2024, 1, 3),
            symbol="GTCO", tx_type="BUY", quantity=500, price_ngn=40.0,
            amount_ngn=-20000, fees_ngn=100),
        PortfolioTransaction(id=4, portfolio_id=1, ts=date(2024, 1, 5),
            symbol="DANGCEM", tx_type="DIVIDEND", amount_ngn=1000, fees_ngn=0),
    ]
    for tx in txs:
        session.add(tx)

    # OHLCV Prices (5 days)
    for i in range(5):
        d = date(2024, 1, 2 + i)
        session.add(OHLCVPrice(
            id=i + 1, symbol="DANGCEM", ts=d,
            open=345, high=360, low=340, close=350.0 + i * 2,
            volume=100000, source="TEST",
        ))
        session.add(OHLCVPrice(
            id=10 + i, symbol="GTCO", ts=d,
            open=39, high=42, low=38, close=40.0 + i,
            volume=50000, source="TEST",
        ))

    # AdjustedPrices
    for i in range(5):
        d = date(2024, 1, 2 + i)
        session.add(AdjustedPrice(
            id=i + 1, symbol="DANGCEM", ts=d,
            close_raw=350 + i * 2, adj_factor=1.0, adj_close=350 + i * 2,
            tri=1000 + i * 5, tri_quality="FULL", computed_at=now,
        ))
        session.add(AdjustedPrice(
            id=10 + i, symbol="GTCO", ts=d,
            close_raw=40 + i, adj_factor=1.0, adj_close=40 + i,
            tri=1000 + i * 3, tri_quality="PRICE_ONLY", computed_at=now,
        ))

    # FX rates
    for i in range(5):
        d = date(2024, 1, 2 + i)
        session.add(FxRate(
            id=i + 1, pair="USDNGN", ts=d,
            rate=900.0 + i * 10, source="CBN", ingested_at=now,
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
    """App with empty DB (no seed data)."""
    from fastapi import FastAPI
    from app.api.v1.portfolios import router
    from app.db.engine import get_async_session

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    async def override():
        yield session

    test_app.dependency_overrides[get_async_session] = override
    return test_app


# ── 1. Create Portfolio ──────────────────────────────────────────────


class TestCreatePortfolio:

    @pytest.mark.asyncio
    async def test_create_portfolio(self, empty_app):
        async with AsyncClient(
            transport=ASGITransport(app=empty_app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/portfolios", json={
                "name": "My Portfolio", "base_currency": "NGN"
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "My Portfolio"
        assert body["base_currency"] == "NGN"

    @pytest.mark.asyncio
    async def test_create_portfolio_usd_base(self, empty_app):
        async with AsyncClient(
            transport=ASGITransport(app=empty_app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/portfolios", json={
                "name": "USD Portfolio", "base_currency": "usd"
            })
        assert resp.json()["base_currency"] == "USD"


# ── 2. List Portfolios ──────────────────────────────────────────────


class TestListPortfolios:

    @pytest.mark.asyncio
    async def test_list_portfolios(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios")
        body = resp.json()
        assert body["total"] == 1
        assert body["data"][0]["name"] == "Test Portfolio"

    @pytest.mark.asyncio
    async def test_list_empty(self, empty_app):
        async with AsyncClient(
            transport=ASGITransport(app=empty_app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios")
        assert resp.json()["total"] == 0


# ── 3. Get Portfolio ─────────────────────────────────────────────────


class TestGetPortfolio:

    @pytest.mark.asyncio
    async def test_get_portfolio(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios/1")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Portfolio"

    @pytest.mark.asyncio
    async def test_get_portfolio_404(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios/999")
        assert resp.status_code == 404


# ── 4. Add Transactions ─────────────────────────────────────────────


class TestAddTransactions:

    @pytest.mark.asyncio
    async def test_add_valid_transaction(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/portfolios/1/transactions", json={
                "transactions": [
                    {"ts": "2024-01-10", "tx_type": "BUY", "symbol": "ZENITHBA",
                     "quantity": 200, "price_ngn": 30.0, "amount_ngn": -6000, "fees_ngn": 30},
                ]
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["added"] == 1
        assert body["rejected"] == 0

    @pytest.mark.asyncio
    async def test_add_bulk_transactions(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/portfolios/1/transactions", json={
                "transactions": [
                    {"ts": "2024-02-01", "tx_type": "CASH_IN", "amount_ngn": 50000},
                    {"ts": "2024-02-02", "tx_type": "BUY", "symbol": "DANGCEM",
                     "quantity": 10, "price_ngn": 360.0, "amount_ngn": -3600, "fees_ngn": 18},
                ]
            })
        body = resp.json()
        assert body["added"] == 2

    @pytest.mark.asyncio
    async def test_add_invalid_transaction(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/portfolios/1/transactions", json={
                "transactions": [
                    {"ts": "2024-01-10", "tx_type": "BUY", "amount_ngn": -5000},
                ]
            })
        # Should be 422 (all invalid)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_add_to_nonexistent_portfolio(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/portfolios/999/transactions", json={
                "transactions": [
                    {"ts": "2024-01-10", "tx_type": "CASH_IN", "amount_ngn": 1000},
                ]
            })
        assert resp.status_code == 404


# ── 5. List Transactions ─────────────────────────────────────────────


class TestListTransactions:

    @pytest.mark.asyncio
    async def test_list_all(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios/1/transactions")
        body = resp.json()
        assert body["total"] == 4

    @pytest.mark.asyncio
    async def test_filter_by_symbol(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios/1/transactions?symbol=DANGCEM")
        body = resp.json()
        assert body["total"] == 2  # BUY + DIVIDEND
        for row in body["data"]:
            assert row["symbol"] == "DANGCEM"

    @pytest.mark.asyncio
    async def test_filter_by_type(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios/1/transactions?tx_type=BUY")
        body = resp.json()
        assert body["total"] == 2


# ── 6. Holdings ──────────────────────────────────────────────────────


class TestHoldings:

    @pytest.mark.asyncio
    async def test_get_holdings(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios/1/holdings")
        assert resp.status_code == 200
        body = resp.json()
        assert "DANGCEM" in body["holdings"]
        assert "GTCO" in body["holdings"]
        assert body["holdings"]["DANGCEM"]["quantity"] == 100
        assert body["holdings"]["GTCO"]["quantity"] == 500
        assert "valuation" in body

    @pytest.mark.asyncio
    async def test_holdings_as_of(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios/1/holdings?as_of=2024-01-02")
        body = resp.json()
        # Before buys, only cash
        assert len(body["holdings"]) == 0

    @pytest.mark.asyncio
    async def test_holdings_404_no_transactions(self, app_with_session):
        """Portfolio 999 doesn't exist → 404."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios/999/holdings")
        assert resp.status_code == 404


# ── 7. Performance ───────────────────────────────────────────────────


class TestPerformance:

    @pytest.mark.asyncio
    async def test_performance_ngn(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/performance?start_date=2024-01-02&end_date=2024-01-06&reporting=NGN"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["reporting_mode"] == "NGN"
        assert "metrics" in body
        assert "quality" in body
        assert "series" in body
        assert body["quality"]["fx_mode"] == "FX_NOT_REQUESTED"

    @pytest.mark.asyncio
    async def test_performance_usd(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/performance?start_date=2024-01-02&end_date=2024-01-06&reporting=USD"
            )
        body = resp.json()
        assert body["reporting_mode"] == "USD"
        assert body["quality"]["fx_mode"] == "FX_FULL"

    @pytest.mark.asyncio
    async def test_performance_real_ngn(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/performance?start_date=2024-01-02&end_date=2024-01-06&reporting=REAL_NGN"
            )
        body = resp.json()
        assert body["reporting_mode"] == "REAL_NGN"
        assert body["quality"]["inflation_mode"] == "CPI_FULL"

    @pytest.mark.asyncio
    async def test_performance_invalid_mode(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/performance?reporting=BITCOIN"
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_performance_404_no_transactions(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/portfolios/999/performance")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_performance_has_quality_flags(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/performance?start_date=2024-01-02&end_date=2024-01-06"
            )
        body = resp.json()
        q = body["quality"]
        assert "data_mode" in q
        assert "fx_mode" in q
        assert "inflation_mode" in q
        assert "overall_quality" in q

    @pytest.mark.asyncio
    async def test_performance_series_has_value_and_ngn(self, app_with_session):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_session), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/performance?start_date=2024-01-02&end_date=2024-01-06&reporting=USD"
            )
        series = resp.json()["series"]
        assert len(series) > 0
        for entry in series:
            assert "value" in entry
            assert "value_ngn" in entry


# ── 8. Governance — Degraded when missing macro data ─────────────────


class TestGovernance:

    @pytest.mark.asyncio
    async def test_usd_degraded_without_fx(self, empty_app, session):
        """USD reporting without FX data → DEGRADED."""
        # Create portfolio + minimal transaction + price
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
        session.add(OHLCVPrice(
            id=1, symbol="TEST", ts=date(2024, 1, 2),
            open=100, high=102, low=98, close=100, volume=1000, source="T",
        ))
        session.add(OHLCVPrice(
            id=2, symbol="TEST", ts=date(2024, 1, 3),
            open=100, high=105, low=99, close=102, volume=1000, source="T",
        ))
        await session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=empty_app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/performance?start_date=2024-01-02&end_date=2024-01-03&reporting=USD"
            )
        body = resp.json()
        assert body["quality"]["fx_mode"] == "FX_MISSING"
        assert body["quality"]["overall_quality"] == "DEGRADED"

    @pytest.mark.asyncio
    async def test_real_ngn_degraded_without_cpi(self, empty_app, session):
        """REAL_NGN reporting without CPI → DEGRADED."""
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
        session.add(OHLCVPrice(
            id=1, symbol="TEST", ts=date(2024, 1, 2),
            open=100, high=102, low=98, close=100, volume=1000, source="T",
        ))
        session.add(OHLCVPrice(
            id=2, symbol="TEST", ts=date(2024, 1, 3),
            open=100, high=105, low=99, close=102, volume=1000, source="T",
        ))
        await session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=empty_app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/portfolios/1/performance?start_date=2024-01-02&end_date=2024-01-03&reporting=REAL_NGN"
            )
        body = resp.json()
        assert body["quality"]["inflation_mode"] == "CPI_MISSING"
        assert body["quality"]["overall_quality"] == "DEGRADED"
