"""
Tests for Portfolio Core — holdings computation + transaction validation (Milestone B — PR2).

Covers:
  1. Transaction validation — type-specific rules, missing fields
  2. Holdings computation — BUY, SELL, weighted average cost
  3. Cash balance — CASH_IN/OUT, dividends, fees
  4. As-of computation — replay to a specific date
  5. Valuation — market value, gain/loss, quality flags
  6. Daily value series — multi-day portfolio value
  7. Edge cases — empty portfolio, full sell, negative cash
  8. DB round-trip — Portfolio + PortfolioTransaction persist
"""

import os
import sys
import pytest
import pytest_asyncio
from datetime import date, datetime

from sqlalchemy import event, select, func
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

from app.db.models import Base, Portfolio, PortfolioTransaction
from app.services.portfolio import (
    PortfolioService, Holding, PortfolioSnapshot, Valuation,
    TxValidationError, VALID_TX_TYPES,
)


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def svc():
    return PortfolioService()


SAMPLE_TRANSACTIONS = [
    {"ts": date(2024, 1, 2), "tx_type": "CASH_IN", "amount_ngn": 1_000_000, "fees_ngn": 0},
    {"ts": date(2024, 1, 3), "tx_type": "BUY", "symbol": "DANGCEM", "quantity": 100,
     "price_ngn": 350.0, "amount_ngn": 35000, "fees_ngn": 175.0},
    {"ts": date(2024, 1, 3), "tx_type": "BUY", "symbol": "GTCO", "quantity": 500,
     "price_ngn": 40.0, "amount_ngn": 20000, "fees_ngn": 100.0},
    {"ts": date(2024, 1, 10), "tx_type": "BUY", "symbol": "DANGCEM", "quantity": 50,
     "price_ngn": 360.0, "amount_ngn": 18000, "fees_ngn": 90.0},
    {"ts": date(2024, 1, 15), "tx_type": "DIVIDEND", "symbol": "DANGCEM",
     "amount_ngn": 1500.0, "fees_ngn": 0},
    {"ts": date(2024, 1, 20), "tx_type": "SELL", "symbol": "GTCO", "quantity": 200,
     "price_ngn": 45.0, "amount_ngn": 9000, "fees_ngn": 45.0},
    {"ts": date(2024, 2, 1), "tx_type": "FEE", "amount_ngn": 500.0, "fees_ngn": 0},
    {"ts": date(2024, 2, 15), "tx_type": "CASH_OUT", "amount_ngn": 50_000, "fees_ngn": 0},
]


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


# ── 1. Transaction Validation ────────────────────────────────────────


class TestTransactionValidation:

    def test_valid_buy(self, svc):
        errors = svc.validate_transaction({
            "ts": date(2024, 1, 1), "tx_type": "BUY", "symbol": "DANGCEM",
            "quantity": 100, "price_ngn": 350.0, "amount_ngn": 35000, "fees_ngn": 0,
        })
        assert errors == []

    def test_valid_sell(self, svc):
        errors = svc.validate_transaction({
            "ts": date(2024, 1, 1), "tx_type": "SELL", "symbol": "GTCO",
            "quantity": 50, "price_ngn": 45.0, "amount_ngn": 2250, "fees_ngn": 0,
        })
        assert errors == []

    def test_valid_cash_in(self, svc):
        errors = svc.validate_transaction({
            "ts": date(2024, 1, 1), "tx_type": "CASH_IN", "amount_ngn": 100000, "fees_ngn": 0,
        })
        assert errors == []

    def test_valid_dividend(self, svc):
        errors = svc.validate_transaction({
            "ts": date(2024, 1, 1), "tx_type": "DIVIDEND", "symbol": "DANGCEM",
            "amount_ngn": 500, "fees_ngn": 0,
        })
        assert errors == []

    def test_invalid_tx_type(self, svc):
        errors = svc.validate_transaction({"ts": date(2024, 1, 1), "tx_type": "BOGUS"})
        assert len(errors) == 1
        assert errors[0].field == "tx_type"

    def test_buy_missing_symbol(self, svc):
        errors = svc.validate_transaction({
            "ts": date(2024, 1, 1), "tx_type": "BUY",
            "quantity": 100, "price_ngn": 350.0, "amount_ngn": 35000,
        })
        assert any(e.field == "symbol" for e in errors)

    def test_buy_missing_quantity(self, svc):
        errors = svc.validate_transaction({
            "ts": date(2024, 1, 1), "tx_type": "BUY", "symbol": "DANGCEM",
            "price_ngn": 350.0, "amount_ngn": 35000,
        })
        assert any(e.field == "quantity" for e in errors)

    def test_buy_missing_price(self, svc):
        errors = svc.validate_transaction({
            "ts": date(2024, 1, 1), "tx_type": "BUY", "symbol": "DANGCEM",
            "quantity": 100, "amount_ngn": 35000,
        })
        assert any(e.field == "price_ngn" for e in errors)

    def test_dividend_missing_symbol(self, svc):
        errors = svc.validate_transaction({
            "ts": date(2024, 1, 1), "tx_type": "DIVIDEND", "amount_ngn": 500,
        })
        assert any(e.field == "symbol" for e in errors)

    def test_cash_in_missing_amount(self, svc):
        errors = svc.validate_transaction({
            "ts": date(2024, 1, 1), "tx_type": "CASH_IN",
        })
        assert any(e.field == "amount_ngn" for e in errors)

    def test_fee_missing_amount(self, svc):
        errors = svc.validate_transaction({
            "ts": date(2024, 1, 1), "tx_type": "FEE",
        })
        assert any(e.field == "amount_ngn" for e in errors)

    def test_missing_date(self, svc):
        errors = svc.validate_transaction({
            "tx_type": "CASH_IN", "amount_ngn": 1000,
        })
        assert any(e.field == "ts" for e in errors)

    def test_error_to_dict(self):
        e = TxValidationError("symbol", "missing")
        assert e.to_dict() == {"field": "symbol", "message": "missing"}


# ── 2. Holdings Computation ──────────────────────────────────────────


class TestHoldingsComputation:

    def test_single_buy(self, svc):
        txs = [
            {"ts": date(2024, 1, 2), "tx_type": "CASH_IN", "amount_ngn": 100000, "fees_ngn": 0},
            {"ts": date(2024, 1, 3), "tx_type": "BUY", "symbol": "DANGCEM",
             "quantity": 100, "price_ngn": 350.0, "amount_ngn": 35000, "fees_ngn": 0},
        ]
        snap = svc.compute_holdings(txs)
        assert "DANGCEM" in snap.holdings
        assert snap.holdings["DANGCEM"].quantity == 100
        assert snap.holdings["DANGCEM"].avg_cost_ngn == 350.0

    def test_two_buys_weighted_average(self, svc):
        txs = [
            {"ts": date(2024, 1, 2), "tx_type": "CASH_IN", "amount_ngn": 500000, "fees_ngn": 0},
            {"ts": date(2024, 1, 3), "tx_type": "BUY", "symbol": "DANGCEM",
             "quantity": 100, "price_ngn": 300.0, "amount_ngn": 30000, "fees_ngn": 0},
            {"ts": date(2024, 1, 4), "tx_type": "BUY", "symbol": "DANGCEM",
             "quantity": 100, "price_ngn": 400.0, "amount_ngn": 40000, "fees_ngn": 0},
        ]
        snap = svc.compute_holdings(txs)
        h = snap.holdings["DANGCEM"]
        assert h.quantity == 200
        # avg = (100*300 + 100*400) / 200 = 350
        assert abs(h.avg_cost_ngn - 350.0) < 0.01

    def test_buy_with_fees_increases_cost_basis(self, svc):
        txs = [
            {"ts": date(2024, 1, 2), "tx_type": "CASH_IN", "amount_ngn": 500000, "fees_ngn": 0},
            {"ts": date(2024, 1, 3), "tx_type": "BUY", "symbol": "DANGCEM",
             "quantity": 100, "price_ngn": 350.0, "amount_ngn": 35000, "fees_ngn": 175.0},
        ]
        snap = svc.compute_holdings(txs)
        h = snap.holdings["DANGCEM"]
        # total_cost = 100 * 350 + 175 = 35175
        assert abs(h.total_cost_ngn - 35175.0) < 0.01
        # avg_cost = 35175 / 100 = 351.75
        assert abs(h.avg_cost_ngn - 351.75) < 0.01

    def test_sell_reduces_holdings(self, svc):
        txs = [
            {"ts": date(2024, 1, 2), "tx_type": "CASH_IN", "amount_ngn": 500000, "fees_ngn": 0},
            {"ts": date(2024, 1, 3), "tx_type": "BUY", "symbol": "GTCO",
             "quantity": 500, "price_ngn": 40.0, "amount_ngn": 20000, "fees_ngn": 0},
            {"ts": date(2024, 1, 5), "tx_type": "SELL", "symbol": "GTCO",
             "quantity": 200, "price_ngn": 45.0, "amount_ngn": 9000, "fees_ngn": 0},
        ]
        snap = svc.compute_holdings(txs)
        h = snap.holdings["GTCO"]
        assert h.quantity == 300

    def test_full_sell_removes_position(self, svc):
        txs = [
            {"ts": date(2024, 1, 2), "tx_type": "CASH_IN", "amount_ngn": 500000, "fees_ngn": 0},
            {"ts": date(2024, 1, 3), "tx_type": "BUY", "symbol": "GTCO",
             "quantity": 100, "price_ngn": 40.0, "amount_ngn": 4000, "fees_ngn": 0},
            {"ts": date(2024, 1, 5), "tx_type": "SELL", "symbol": "GTCO",
             "quantity": 100, "price_ngn": 45.0, "amount_ngn": 4500, "fees_ngn": 0},
        ]
        snap = svc.compute_holdings(txs)
        assert "GTCO" not in snap.holdings

    def test_multiple_symbols(self, svc):
        snap = svc.compute_holdings(SAMPLE_TRANSACTIONS)
        assert "DANGCEM" in snap.holdings
        assert "GTCO" in snap.holdings
        assert snap.holdings["DANGCEM"].quantity == 150  # 100 + 50
        assert snap.holdings["GTCO"].quantity == 300     # 500 - 200


# ── 3. Cash Balance ──────────────────────────────────────────────────


class TestCashBalance:

    def test_cash_in(self, svc):
        txs = [{"ts": date(2024, 1, 1), "tx_type": "CASH_IN", "amount_ngn": 100000, "fees_ngn": 0}]
        snap = svc.compute_holdings(txs)
        assert abs(snap.cash_ngn - 100000.0) < 0.01

    def test_cash_in_and_buy(self, svc):
        txs = [
            {"ts": date(2024, 1, 1), "tx_type": "CASH_IN", "amount_ngn": 100000, "fees_ngn": 0},
            {"ts": date(2024, 1, 2), "tx_type": "BUY", "symbol": "DANGCEM",
             "quantity": 100, "price_ngn": 350.0, "amount_ngn": 35000, "fees_ngn": 0},
        ]
        snap = svc.compute_holdings(txs)
        assert abs(snap.cash_ngn - 65000.0) < 0.01

    def test_cash_out(self, svc):
        txs = [
            {"ts": date(2024, 1, 1), "tx_type": "CASH_IN", "amount_ngn": 100000, "fees_ngn": 0},
            {"ts": date(2024, 1, 5), "tx_type": "CASH_OUT", "amount_ngn": 20000, "fees_ngn": 0},
        ]
        snap = svc.compute_holdings(txs)
        assert abs(snap.cash_ngn - 80000.0) < 0.01

    def test_dividend_adds_cash(self, svc):
        txs = [
            {"ts": date(2024, 1, 1), "tx_type": "CASH_IN", "amount_ngn": 100000, "fees_ngn": 0},
            {"ts": date(2024, 1, 5), "tx_type": "DIVIDEND", "symbol": "DANGCEM",
             "amount_ngn": 1500, "fees_ngn": 0},
        ]
        snap = svc.compute_holdings(txs)
        assert abs(snap.cash_ngn - 101500.0) < 0.01

    def test_fee_reduces_cash(self, svc):
        txs = [
            {"ts": date(2024, 1, 1), "tx_type": "CASH_IN", "amount_ngn": 100000, "fees_ngn": 0},
            {"ts": date(2024, 1, 5), "tx_type": "FEE", "amount_ngn": 500, "fees_ngn": 0},
        ]
        snap = svc.compute_holdings(txs)
        assert abs(snap.cash_ngn - 99500.0) < 0.01

    def test_total_invested_tracks_cash_flows(self, svc):
        txs = [
            {"ts": date(2024, 1, 1), "tx_type": "CASH_IN", "amount_ngn": 100000, "fees_ngn": 0},
            {"ts": date(2024, 1, 5), "tx_type": "CASH_OUT", "amount_ngn": 20000, "fees_ngn": 0},
        ]
        snap = svc.compute_holdings(txs)
        assert abs(snap.total_invested_ngn - 80000.0) < 0.01


# ── 4. As-of Computation ─────────────────────────────────────────────


class TestAsOfComputation:

    def test_as_of_before_any_tx(self, svc):
        snap = svc.compute_holdings(SAMPLE_TRANSACTIONS, as_of=date(2024, 1, 1))
        assert len(snap.holdings) == 0
        assert snap.cash_ngn == 0.0

    def test_as_of_after_cash_in(self, svc):
        snap = svc.compute_holdings(SAMPLE_TRANSACTIONS, as_of=date(2024, 1, 2))
        assert len(snap.holdings) == 0
        assert abs(snap.cash_ngn - 1_000_000) < 0.01

    def test_as_of_after_first_buys(self, svc):
        snap = svc.compute_holdings(SAMPLE_TRANSACTIONS, as_of=date(2024, 1, 3))
        assert "DANGCEM" in snap.holdings
        assert snap.holdings["DANGCEM"].quantity == 100
        assert "GTCO" in snap.holdings
        assert snap.holdings["GTCO"].quantity == 500

    def test_as_of_after_second_dangcem_buy(self, svc):
        snap = svc.compute_holdings(SAMPLE_TRANSACTIONS, as_of=date(2024, 1, 10))
        assert snap.holdings["DANGCEM"].quantity == 150

    def test_as_of_after_partial_sell(self, svc):
        snap = svc.compute_holdings(SAMPLE_TRANSACTIONS, as_of=date(2024, 1, 20))
        assert snap.holdings["GTCO"].quantity == 300

    def test_snapshot_to_dict(self, svc):
        snap = svc.compute_holdings(SAMPLE_TRANSACTIONS, as_of=date(2024, 1, 3))
        d = snap.to_dict()
        assert d["as_of"] == "2024-01-03"
        assert "DANGCEM" in d["holdings"]
        assert d["num_positions"] == 2


# ── 5. Valuation ─────────────────────────────────────────────────────


class TestValuation:

    def test_valuation_with_prices(self, svc):
        snap = svc.compute_holdings(SAMPLE_TRANSACTIONS, as_of=date(2024, 1, 3))
        prices = {"DANGCEM": 355.0, "GTCO": 42.0}
        val = svc.compute_valuation(snap, prices)
        assert val.data_quality == "FULL"
        # DANGCEM: 100 * 355 = 35500
        # GTCO: 500 * 42 = 21000
        expected_holdings = 35500 + 21000
        assert abs(val.holdings_value_ngn - expected_holdings) < 0.01

    def test_valuation_partial_prices(self, svc):
        snap = svc.compute_holdings(SAMPLE_TRANSACTIONS, as_of=date(2024, 1, 3))
        prices = {"DANGCEM": 355.0}  # missing GTCO
        val = svc.compute_valuation(snap, prices)
        assert val.data_quality == "PARTIAL"

    def test_valuation_no_prices(self, svc):
        snap = svc.compute_holdings(SAMPLE_TRANSACTIONS, as_of=date(2024, 1, 3))
        val = svc.compute_valuation(snap, {})
        assert val.data_quality == "PRICE_MISSING"

    def test_valuation_gain_loss(self, svc):
        txs = [
            {"ts": date(2024, 1, 1), "tx_type": "CASH_IN", "amount_ngn": 100000, "fees_ngn": 0},
            {"ts": date(2024, 1, 2), "tx_type": "BUY", "symbol": "DANGCEM",
             "quantity": 100, "price_ngn": 300.0, "amount_ngn": 30000, "fees_ngn": 0},
        ]
        snap = svc.compute_holdings(txs)
        val = svc.compute_valuation(snap, {"DANGCEM": 360.0})
        pos = val.positions[0]
        # Cost: 100 * 300 = 30000
        # Value: 100 * 360 = 36000
        # Gain: 6000 = 20%
        assert abs(pos["gain_loss_ngn"] - 6000.0) < 0.01
        assert abs(pos["gain_loss_pct"] - 20.0) < 0.01

    def test_valuation_to_dict(self, svc):
        snap = svc.compute_holdings(SAMPLE_TRANSACTIONS, as_of=date(2024, 1, 3))
        val = svc.compute_valuation(snap, {"DANGCEM": 350.0, "GTCO": 40.0})
        d = val.to_dict()
        assert "holdings_value_ngn" in d
        assert "total_value_ngn" in d
        assert "positions" in d
        assert "data_quality" in d


# ── 6. Daily Value Series ────────────────────────────────────────────


class TestDailyValueSeries:

    def test_daily_values(self, svc):
        txs = [
            {"ts": date(2024, 1, 1), "tx_type": "CASH_IN", "amount_ngn": 100000, "fees_ngn": 0},
            {"ts": date(2024, 1, 2), "tx_type": "BUY", "symbol": "TEST",
             "quantity": 100, "price_ngn": 100.0, "amount_ngn": 10000, "fees_ngn": 0},
        ]
        prices = {
            "TEST": {
                date(2024, 1, 2): 100.0,
                date(2024, 1, 3): 105.0,
                date(2024, 1, 4): 110.0,
            },
        }
        values = svc.compute_daily_values(
            txs, prices, date(2024, 1, 2), date(2024, 1, 4)
        )
        assert len(values) == 3
        # Day 2: 100 shares * 100 + (100000 - 10000) cash = 100000
        assert abs(values[0]["value_ngn"] - 100000.0) < 0.01
        # Day 3: 100 * 105 + 90000 = 100500
        assert abs(values[1]["value_ngn"] - 100500.0) < 0.01
        # Day 4: 100 * 110 + 90000 = 101000
        assert abs(values[2]["value_ngn"] - 101000.0) < 0.01

    def test_daily_values_empty_range(self, svc):
        txs = [{"ts": date(2024, 1, 1), "tx_type": "CASH_IN", "amount_ngn": 100000, "fees_ngn": 0}]
        values = svc.compute_daily_values(txs, {}, date(2024, 1, 1), date(2024, 1, 5))
        assert values == []


# ── 7. Edge Cases ────────────────────────────────────────────────────


class TestEdgeCases:

    def test_empty_transactions(self, svc):
        snap = svc.compute_holdings([])
        assert len(snap.holdings) == 0
        assert snap.cash_ngn == 0.0

    def test_holding_to_dict(self):
        h = Holding(symbol="DANGCEM", quantity=100, avg_cost_ngn=350.0, total_cost_ngn=35000.0)
        d = h.to_dict()
        assert d["symbol"] == "DANGCEM"
        assert d["quantity"] == 100
        assert d["avg_cost_ngn"] == 350.0


# ── 8. DB Round-Trip ─────────────────────────────────────────────────


class TestDbRoundTrip:

    @pytest.mark.asyncio
    async def test_portfolio_persist(self, session):
        p = Portfolio(id=1, name="Test Portfolio", base_currency="NGN")
        session.add(p)
        await session.commit()

        row = (await session.execute(
            select(Portfolio).where(Portfolio.id == 1)
        )).scalar_one()
        assert row.name == "Test Portfolio"
        assert row.base_currency == "NGN"

    @pytest.mark.asyncio
    async def test_transaction_persist(self, session):
        p = Portfolio(id=1, name="Test Portfolio", base_currency="NGN")
        session.add(p)
        await session.flush()

        tx = PortfolioTransaction(
            id=1, portfolio_id=1, ts=date(2024, 1, 2),
            symbol="DANGCEM", tx_type="BUY",
            quantity=100, price_ngn=350.0,
            amount_ngn=-35000.0, fees_ngn=175.0,
        )
        session.add(tx)
        await session.commit()

        row = (await session.execute(
            select(PortfolioTransaction).where(PortfolioTransaction.id == 1)
        )).scalar_one()
        assert row.symbol == "DANGCEM"
        assert row.tx_type == "BUY"
        assert row.quantity == 100
        assert row.price_ngn == 350.0
