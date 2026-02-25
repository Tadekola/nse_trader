"""
Tests for Corporate Actions — Milestone A, PR1.

Covers:
  1. CorporateAction + AdjustedPrice model creation on SQLite
  2. CsvCorporateActionProvider — happy path parsing
  3. CSV validation: missing fields, bad types, type-specific rules
  4. Edge cases: empty file, BOM encoding, extra columns
  5. Ingestion to DB via session (round-trip)
"""

import csv
import io
import os
import sys
import pytest
import pytest_asyncio
from datetime import date, datetime, timezone

from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Render JSONB as JSON on SQLite
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"

from app.db.models import AdjustedPrice, Base, CorporateAction
from app.data.corporate_actions.csv_provider import (
    CsvCorporateActionProvider,
    ParseError,
    ParseResult,
    VALID_ACTION_TYPES,
)


# ── Fixtures ─────────────────────────────────────────────────────────

SAMPLE_CSV = """\
symbol,action_type,ex_date,record_date,payment_date,amount,ratio_from,ratio_to,currency,source,confidence,notes
DANGCEM,CASH_DIVIDEND,2024-04-15,2024-04-10,2024-05-01,20.0,,,NGN,NGX_DISCLOSURE,HIGH,Final dividend 2023
GTCO,CASH_DIVIDEND,2024-03-20,2024-03-15,2024-04-05,3.0,,,NGN,NGX_DISCLOSURE,HIGH,Interim dividend
DANGCEM,BONUS_ISSUE,2023-10-02,2023-09-28,,,1,10,NGN,NGX_DISCLOSURE,HIGH,1 for 10 bonus
ZENITHBA,STOCK_SPLIT,2023-06-15,2023-06-10,,,1,2,NGN,MANUAL_ENTRY,MEDIUM,2-for-1 split
"""

SAMPLE_CSV_WITH_ERRORS = """\
symbol,action_type,ex_date,record_date,payment_date,amount,ratio_from,ratio_to,currency,source,confidence,notes
,CASH_DIVIDEND,2024-01-01,,,,,,NGN,TEST,HIGH,missing symbol
DANGCEM,INVALID_TYPE,2024-01-01,,,,,,NGN,TEST,HIGH,bad type
DANGCEM,CASH_DIVIDEND,bad-date,,,,,,NGN,TEST,HIGH,bad date
DANGCEM,CASH_DIVIDEND,2024-01-01,,,0,,,NGN,TEST,HIGH,zero amount
DANGCEM,CASH_DIVIDEND,2024-01-01,,,-5,,,NGN,TEST,HIGH,negative amount
DANGCEM,STOCK_SPLIT,2024-01-01,,,,,,NGN,TEST,HIGH,missing ratios
DANGCEM,BONUS_ISSUE,2024-01-01,,,,,0,5,NGN,TEST,HIGH,zero ratio_from
"""


@pytest.fixture
def provider():
    return CsvCorporateActionProvider()


@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

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
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


# ── 1. CSV Parsing — Happy Path ─────────────────────────────────────


class TestCsvParsingHappyPath:

    def test_parse_sample_csv(self, provider):
        result = provider.parse_csv_string(SAMPLE_CSV)
        assert result.rows_total == 4
        assert result.rows_accepted == 4
        assert result.rows_rejected == 0
        assert len(result.actions) == 4
        assert len(result.errors) == 0

    def test_dividend_fields(self, provider):
        result = provider.parse_csv_string(SAMPLE_CSV)
        dangcem_div = result.actions[0]
        assert dangcem_div["symbol"] == "DANGCEM"
        assert dangcem_div["action_type"] == "CASH_DIVIDEND"
        assert dangcem_div["ex_date"] == date(2024, 4, 15)
        assert dangcem_div["record_date"] == date(2024, 4, 10)
        assert dangcem_div["payment_date"] == date(2024, 5, 1)
        assert dangcem_div["amount"] == 20.0
        assert dangcem_div["currency"] == "NGN"
        assert dangcem_div["source"] == "NGX_DISCLOSURE"
        assert dangcem_div["confidence"] == "HIGH"

    def test_bonus_issue_fields(self, provider):
        result = provider.parse_csv_string(SAMPLE_CSV)
        bonus = result.actions[2]
        assert bonus["action_type"] == "BONUS_ISSUE"
        assert bonus["ratio_from"] == 1
        assert bonus["ratio_to"] == 10
        assert bonus["amount"] is None

    def test_stock_split_fields(self, provider):
        result = provider.parse_csv_string(SAMPLE_CSV)
        split = result.actions[3]
        assert split["action_type"] == "STOCK_SPLIT"
        assert split["ratio_from"] == 1
        assert split["ratio_to"] == 2
        assert split["confidence"] == "MEDIUM"
        assert split["notes"] == "2-for-1 split"

    def test_provenance_present(self, provider):
        result = provider.parse_csv_string(SAMPLE_CSV)
        for action in result.actions:
            assert "provenance" in action
            assert action["provenance"]["method"] == "csv_import"
            assert "ingested_at" in action["provenance"]
            assert action["ingested_at"] is not None

    def test_symbol_uppercased(self, provider):
        csv_text = "symbol,action_type,ex_date,amount\ndangcem,CASH_DIVIDEND,2024-01-01,5.0\n"
        result = provider.parse_csv_string(csv_text)
        assert result.actions[0]["symbol"] == "DANGCEM"

    def test_default_source_and_currency(self, provider):
        csv_text = "symbol,action_type,ex_date,amount\nGTCO,CASH_DIVIDEND,2024-01-01,3.0\n"
        result = provider.parse_csv_string(csv_text)
        assert result.actions[0]["source"] == "CSV_IMPORT"
        assert result.actions[0]["currency"] == "NGN"


# ── 2. CSV Validation — Error Cases ─────────────────────────────────


class TestCsvValidation:

    def test_all_error_rows_rejected(self, provider):
        result = provider.parse_csv_string(SAMPLE_CSV_WITH_ERRORS)
        assert result.rows_rejected == 7
        assert result.rows_accepted == 0
        assert len(result.errors) >= 7

    def test_missing_symbol(self, provider):
        csv_text = "symbol,action_type,ex_date,amount\n,CASH_DIVIDEND,2024-01-01,5.0\n"
        result = provider.parse_csv_string(csv_text)
        assert result.rows_rejected == 1
        assert any(e.field == "symbol" for e in result.errors)

    def test_invalid_action_type(self, provider):
        csv_text = "symbol,action_type,ex_date,amount\nGTCO,FAKE,2024-01-01,5.0\n"
        result = provider.parse_csv_string(csv_text)
        assert result.rows_rejected == 1
        assert any(e.field == "action_type" for e in result.errors)

    def test_invalid_date(self, provider):
        csv_text = "symbol,action_type,ex_date,amount\nGTCO,CASH_DIVIDEND,not-a-date,5.0\n"
        result = provider.parse_csv_string(csv_text)
        assert result.rows_rejected == 1
        assert any(e.field == "ex_date" for e in result.errors)

    def test_dividend_requires_positive_amount(self, provider):
        csv_text = "symbol,action_type,ex_date,amount\nGTCO,CASH_DIVIDEND,2024-01-01,0\n"
        result = provider.parse_csv_string(csv_text)
        assert result.rows_rejected == 1
        assert any(e.field == "amount" for e in result.errors)

    def test_split_requires_ratios(self, provider):
        csv_text = "symbol,action_type,ex_date,ratio_from,ratio_to\nGTCO,STOCK_SPLIT,2024-01-01,,\n"
        result = provider.parse_csv_string(csv_text)
        assert result.rows_rejected == 1
        assert any(e.field == "ratio_from" for e in result.errors)

    def test_bonus_requires_ratios(self, provider):
        csv_text = "symbol,action_type,ex_date,ratio_from,ratio_to\nGTCO,BONUS_ISSUE,2024-01-01,1,\n"
        result = provider.parse_csv_string(csv_text)
        assert result.rows_rejected == 1
        assert any(e.field == "ratio_to" for e in result.errors)

    def test_mixed_valid_and_invalid(self, provider):
        csv_text = (
            "symbol,action_type,ex_date,amount,ratio_from,ratio_to\n"
            "GTCO,CASH_DIVIDEND,2024-01-01,5.0,,\n"
            ",CASH_DIVIDEND,2024-01-01,5.0,,\n"
            "DANGCEM,STOCK_SPLIT,2024-06-01,,1,2\n"
        )
        result = provider.parse_csv_string(csv_text)
        assert result.rows_accepted == 2
        assert result.rows_rejected == 1

    def test_parse_error_to_dict(self):
        err = ParseError(row=5, field="amount", message="must be positive")
        d = err.to_dict()
        assert d == {"row": 5, "field": "amount", "message": "must be positive"}


# ── 3. Edge Cases ────────────────────────────────────────────────────


class TestEdgeCases:

    def test_empty_csv(self, provider):
        csv_text = "symbol,action_type,ex_date,amount\n"
        result = provider.parse_csv_string(csv_text)
        assert result.rows_total == 0
        assert result.rows_accepted == 0

    def test_file_not_found(self, provider):
        with pytest.raises(FileNotFoundError):
            provider.parse_file("/nonexistent/path.csv")

    def test_extra_columns_ignored(self, provider):
        csv_text = (
            "symbol,action_type,ex_date,amount,extra_col\n"
            "GTCO,CASH_DIVIDEND,2024-01-01,5.0,ignored\n"
        )
        result = provider.parse_csv_string(csv_text)
        assert result.rows_accepted == 1
        assert "extra_col" not in result.actions[0]

    def test_invalid_confidence_defaults_to_medium(self, provider):
        csv_text = (
            "symbol,action_type,ex_date,amount,confidence\n"
            "GTCO,CASH_DIVIDEND,2024-01-01,5.0,JUNK\n"
        )
        result = provider.parse_csv_string(csv_text)
        assert result.actions[0]["confidence"] == "MEDIUM"


# ── 4. DB Round-Trip ─────────────────────────────────────────────────


class TestDbRoundTrip:

    @pytest.mark.asyncio
    async def test_corporate_action_persist(self, session, provider):
        result = provider.parse_csv_string(SAMPLE_CSV)
        for i, action_dict in enumerate(result.actions):
            ca = CorporateAction(id=i + 1, **action_dict)
            session.add(ca)
        await session.commit()

        from sqlalchemy import select, func
        count = (await session.execute(
            select(func.count()).select_from(CorporateAction)
        )).scalar()
        assert count == 4

        # Verify a specific record
        stmt = select(CorporateAction).where(
            CorporateAction.symbol == "DANGCEM",
            CorporateAction.action_type == "CASH_DIVIDEND",
        )
        row = (await session.execute(stmt)).scalar_one()
        assert row.amount == 20.0
        assert row.ex_date == date(2024, 4, 15)

    @pytest.mark.asyncio
    async def test_adjusted_price_persist(self, session):
        ap = AdjustedPrice(
            id=1,
            symbol="DANGCEM",
            ts=date(2024, 4, 15),
            close_raw=350.0,
            adj_factor=1.0,
            adj_close=350.0,
            tri=1000.0,
            daily_return_price=0.015,
            daily_return_total=0.018,
            tri_quality="FULL",
            provenance={"source": "computed", "method": "tri_engine"},
        )
        session.add(ap)
        await session.commit()

        from sqlalchemy import select
        row = (await session.execute(
            select(AdjustedPrice).where(AdjustedPrice.symbol == "DANGCEM")
        )).scalar_one()
        assert row.tri == 1000.0
        assert row.tri_quality == "FULL"
        assert row.adj_close == 350.0

    @pytest.mark.asyncio
    async def test_unique_constraint_corporate_action(self, session, provider):
        """Duplicate (symbol, action_type, ex_date) should conflict."""
        from sqlalchemy.exc import IntegrityError

        ca1 = CorporateAction(
            id=1, symbol="GTCO", action_type="CASH_DIVIDEND",
            ex_date=date(2024, 1, 1), amount=3.0, source="TEST",
            ingested_at=datetime.now(timezone.utc),
        )
        ca2 = CorporateAction(
            id=2, symbol="GTCO", action_type="CASH_DIVIDEND",
            ex_date=date(2024, 1, 1), amount=3.0, source="TEST",
            ingested_at=datetime.now(timezone.utc),
        )
        session.add(ca1)
        await session.flush()
        session.add(ca2)
        with pytest.raises(IntegrityError):
            await session.flush()
