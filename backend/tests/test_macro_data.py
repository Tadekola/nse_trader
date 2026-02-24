"""
Tests for FX + CPI Data Layer (Milestone B — PR1).

Covers:
  1. FX CSV parsing — happy path, validation errors, edge cases
  2. FxRateService — exact lookup, forward-fill, gaps, convert_series
  3. CPI CSV parsing — happy path, validation errors
  4. CpiService — forward-fill monthly→daily, deflator, deflate_series
  5. DB round-trip — FxRate + MacroSeries persist and query
  6. Quality flags — FX_FULL/FX_MISSING, CPI_FULL/CPI_MISSING
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

from app.db.models import Base, FxRate, MacroSeries
from app.data.macro.fx_provider import CsvFxRateProvider, FxRateService
from app.data.macro.cpi_provider import CsvCpiProvider, CpiService


# ── Fixtures ─────────────────────────────────────────────────────────

SAMPLE_FX_CSV = """\
date,pair,rate,source,confidence
2024-01-02,USDNGN,907.50,CBN,HIGH
2024-01-03,USDNGN,910.00,CBN,HIGH
2024-01-04,USDNGN,915.25,CBN,HIGH
2024-01-05,USDNGN,920.00,CBN,HIGH
2024-01-08,USDNGN,935.00,CBN,HIGH
2024-01-09,USDNGN,940.00,CBN,HIGH
2024-01-02,GBPNGN,1150.00,CBN,MEDIUM
2024-01-03,GBPNGN,1155.00,CBN,MEDIUM
"""

SAMPLE_FX_CSV_ERRORS = """\
date,pair,rate,source,confidence
,USDNGN,900,CBN,HIGH
2024-01-01,US,900,CBN,HIGH
2024-01-01,USDNGN,,CBN,HIGH
2024-01-01,USDNGN,-50,CBN,HIGH
2024-01-01,USDNGN,abc,CBN,HIGH
"""

SAMPLE_CPI_CSV = """\
date,series_name,value,frequency,source,confidence
2023-01-01,CPI_NGN,100.0,MONTHLY,NBS,HIGH
2023-02-01,CPI_NGN,101.5,MONTHLY,NBS,HIGH
2023-03-01,CPI_NGN,103.2,MONTHLY,NBS,HIGH
2023-04-01,CPI_NGN,105.0,MONTHLY,NBS,HIGH
2023-05-01,CPI_NGN,107.8,MONTHLY,NBS,HIGH
2023-06-01,CPI_NGN,110.0,MONTHLY,NBS,HIGH
2024-01-01,CPI_NGN,130.0,MONTHLY,NBS,HIGH
2024-02-01,CPI_NGN,133.5,MONTHLY,NBS,HIGH
2024-03-01,CPI_NGN,136.0,MONTHLY,NBS,HIGH
"""

SAMPLE_CPI_CSV_ERRORS = """\
date,series_name,value,frequency,source,confidence
,CPI_NGN,100,MONTHLY,NBS,HIGH
2024-01-01,,100,MONTHLY,NBS,HIGH
2024-01-01,CPI_NGN,,MONTHLY,NBS,HIGH
2024-01-01,CPI_NGN,-5,MONTHLY,NBS,HIGH
"""


@pytest.fixture
def fx_provider():
    return CsvFxRateProvider()


@pytest.fixture
def cpi_provider():
    return CsvCpiProvider()


@pytest.fixture
def fx_service():
    """FxRateService with sample USDNGN data including weekend gap (Jan 6-7)."""
    rates = [
        {"pair": "USDNGN", "ts": date(2024, 1, 2), "rate": 907.50},
        {"pair": "USDNGN", "ts": date(2024, 1, 3), "rate": 910.00},
        {"pair": "USDNGN", "ts": date(2024, 1, 4), "rate": 915.25},
        {"pair": "USDNGN", "ts": date(2024, 1, 5), "rate": 920.00},
        # Jan 6 (Sat), Jan 7 (Sun) — no data
        {"pair": "USDNGN", "ts": date(2024, 1, 8), "rate": 935.00},
        {"pair": "USDNGN", "ts": date(2024, 1, 9), "rate": 940.00},
        {"pair": "GBPNGN", "ts": date(2024, 1, 2), "rate": 1150.00},
    ]
    return FxRateService(rates)


@pytest.fixture
def cpi_service():
    """CpiService with monthly CPI_NGN data."""
    entries = [
        {"series_name": "CPI_NGN", "ts": date(2023, 1, 1), "value": 100.0},
        {"series_name": "CPI_NGN", "ts": date(2023, 2, 1), "value": 101.5},
        {"series_name": "CPI_NGN", "ts": date(2023, 3, 1), "value": 103.2},
        {"series_name": "CPI_NGN", "ts": date(2023, 6, 1), "value": 110.0},
        {"series_name": "CPI_NGN", "ts": date(2024, 1, 1), "value": 130.0},
        {"series_name": "CPI_NGN", "ts": date(2024, 2, 1), "value": 133.5},
    ]
    return CpiService(entries)


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


# ── 1. FX CSV Parsing ────────────────────────────────────────────────


class TestFxCsvParsing:

    def test_happy_path(self, fx_provider):
        result = fx_provider.parse_csv_string(SAMPLE_FX_CSV)
        assert result.rows_total == 8
        assert result.rows_accepted == 8
        assert result.rows_rejected == 0

    def test_rate_values(self, fx_provider):
        result = fx_provider.parse_csv_string(SAMPLE_FX_CSV)
        usd_rates = [r for r in result.rates if r["pair"] == "USDNGN"]
        assert len(usd_rates) == 6
        assert usd_rates[0]["rate"] == 907.50
        assert usd_rates[0]["ts"] == date(2024, 1, 2)

    def test_multiple_pairs(self, fx_provider):
        result = fx_provider.parse_csv_string(SAMPLE_FX_CSV)
        pairs = {r["pair"] for r in result.rates}
        assert pairs == {"USDNGN", "GBPNGN"}

    def test_provenance_present(self, fx_provider):
        result = fx_provider.parse_csv_string(SAMPLE_FX_CSV)
        for r in result.rates:
            assert r["provenance"]["method"] == "csv_import"

    def test_error_rows_rejected(self, fx_provider):
        result = fx_provider.parse_csv_string(SAMPLE_FX_CSV_ERRORS)
        assert result.rows_rejected == 5
        assert result.rows_accepted == 0

    def test_missing_date(self, fx_provider):
        csv_text = "date,pair,rate,source\n,USDNGN,900,CBN\n"
        result = fx_provider.parse_csv_string(csv_text)
        assert any(e.field == "date" for e in result.errors)

    def test_negative_rate(self, fx_provider):
        csv_text = "date,pair,rate,source\n2024-01-01,USDNGN,-50,CBN\n"
        result = fx_provider.parse_csv_string(csv_text)
        assert any(e.field == "rate" for e in result.errors)

    def test_file_not_found(self, fx_provider):
        with pytest.raises(FileNotFoundError):
            fx_provider.parse_file("/nonexistent.csv")

    def test_empty_csv(self, fx_provider):
        result = fx_provider.parse_csv_string("date,pair,rate,source\n")
        assert result.rows_total == 0


# ── 2. FxRateService ─────────────────────────────────────────────────


class TestFxRateService:

    def test_exact_lookup(self, fx_service):
        rate = fx_service.get_rate("USDNGN", date(2024, 1, 3))
        assert rate == 910.00

    def test_forward_fill_weekend(self, fx_service):
        """Saturday Jan 6 should forward-fill from Friday Jan 5."""
        rate = fx_service.get_rate("USDNGN", date(2024, 1, 6))
        assert rate == 920.00  # Jan 5's rate

    def test_forward_fill_sunday(self, fx_service):
        rate = fx_service.get_rate("USDNGN", date(2024, 1, 7))
        assert rate == 920.00

    def test_no_rate_before_start(self, fx_service):
        rate = fx_service.get_rate("USDNGN", date(2024, 1, 1))
        assert rate is None

    def test_unknown_pair(self, fx_service):
        rate = fx_service.get_rate("EURNGN", date(2024, 1, 3))
        assert rate is None

    def test_gbp_rate(self, fx_service):
        rate = fx_service.get_rate("GBPNGN", date(2024, 1, 2))
        assert rate == 1150.00

    def test_convert_series_full(self, fx_service):
        dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
        ngn = [907500.0, 910000.0, 915250.0]  # exactly 1000 USD each day
        usd, mode = fx_service.convert_series("USDNGN", dates, ngn)
        assert mode == "FX_FULL"
        assert len(usd) == 3
        assert abs(usd[0] - 1000.0) < 0.01
        assert abs(usd[1] - 1000.0) < 0.01

    def test_convert_series_missing(self, fx_service):
        """Date before data range → None, mode = FX_MISSING."""
        dates = [date(2024, 1, 1), date(2024, 1, 2)]
        ngn = [100000.0, 100000.0]
        usd, mode = fx_service.convert_series("USDNGN", dates, ngn)
        assert mode == "FX_MISSING"
        assert usd[0] is None
        assert usd[1] is not None

    def test_available_range(self, fx_service):
        r = fx_service.get_available_range("USDNGN")
        assert r == (date(2024, 1, 2), date(2024, 1, 9))

    def test_pairs_list(self, fx_service):
        assert set(fx_service.pairs) == {"USDNGN", "GBPNGN"}

    def test_convert_series_unknown_pair(self, fx_service):
        dates = [date(2024, 1, 2)]
        ngn = [100000.0]
        usd, mode = fx_service.convert_series("EURNGN", dates, ngn)
        assert mode == "FX_MISSING"
        assert usd[0] is None


# ── 3. CPI CSV Parsing ───────────────────────────────────────────────


class TestCpiCsvParsing:

    def test_happy_path(self, cpi_provider):
        result = cpi_provider.parse_csv_string(SAMPLE_CPI_CSV)
        assert result.rows_total == 9
        assert result.rows_accepted == 9
        assert result.rows_rejected == 0

    def test_values_correct(self, cpi_provider):
        result = cpi_provider.parse_csv_string(SAMPLE_CPI_CSV)
        jan = [e for e in result.entries if e["ts"] == date(2023, 1, 1)]
        assert len(jan) == 1
        assert jan[0]["value"] == 100.0
        assert jan[0]["series_name"] == "CPI_NGN"
        assert jan[0]["frequency"] == "MONTHLY"

    def test_error_rows_rejected(self, cpi_provider):
        result = cpi_provider.parse_csv_string(SAMPLE_CPI_CSV_ERRORS)
        assert result.rows_rejected == 4
        assert result.rows_accepted == 0

    def test_file_not_found(self, cpi_provider):
        with pytest.raises(FileNotFoundError):
            cpi_provider.parse_file("/nonexistent.csv")

    def test_provenance_present(self, cpi_provider):
        result = cpi_provider.parse_csv_string(SAMPLE_CPI_CSV)
        for e in result.entries:
            assert e["provenance"]["method"] == "csv_import"


# ── 4. CpiService ────────────────────────────────────────────────────


class TestCpiService:

    def test_exact_monthly_lookup(self, cpi_service):
        val = cpi_service.get_value(date(2023, 1, 1))
        assert val == 100.0

    def test_forward_fill_within_month(self, cpi_service):
        """Jan 15 should use Jan 1 value (forward-fill)."""
        val = cpi_service.get_value(date(2023, 1, 15))
        assert val == 100.0

    def test_forward_fill_end_of_month(self, cpi_service):
        """Jan 31 should still use Jan 1 value."""
        val = cpi_service.get_value(date(2023, 1, 31))
        assert val == 100.0

    def test_february_uses_feb_value(self, cpi_service):
        val = cpi_service.get_value(date(2023, 2, 15))
        assert val == 101.5

    def test_gap_forward_fill(self, cpi_service):
        """Apr-May have no data; Apr 15 should use Mar value (103.2)."""
        val = cpi_service.get_value(date(2023, 4, 15))
        assert val == 103.2

    def test_no_data_before_start(self, cpi_service):
        val = cpi_service.get_value(date(2022, 12, 31))
        assert val is None

    def test_deflator_relative_to_base(self, cpi_service):
        """Deflator = cpi[ts] / cpi[base_date]."""
        # CPI Jan 2023 = 100, CPI Jan 2024 = 130
        # Deflator for Jan 2024 relative to Jan 2023 = 130/100 = 1.3
        d = cpi_service.get_deflator(date(2024, 1, 15), base_date=date(2023, 1, 1))
        assert abs(d - 1.3) < 0.001

    def test_deflator_default_base(self, cpi_service):
        """Without base_date, uses earliest CPI as base."""
        d = cpi_service.get_deflator(date(2024, 1, 15))
        assert abs(d - 1.3) < 0.001  # 130 / 100

    def test_deflate_series_full(self, cpi_service):
        dates = [date(2023, 1, 15), date(2023, 2, 15), date(2024, 1, 15)]
        nominal = [100000.0, 100000.0, 100000.0]
        real, mode = cpi_service.deflate_series(dates, nominal, base_date=date(2023, 1, 1))
        assert mode == "CPI_FULL"
        # Jan 2023: 100/100=1.0 → 100000
        assert abs(real[0] - 100000.0) < 0.01
        # Feb 2023: 101.5/100=1.015 → 100000/1.015 ≈ 98522
        assert abs(real[1] - (100000.0 / 1.015)) < 1.0
        # Jan 2024: 130/100=1.3 → 100000/1.3 ≈ 76923
        assert abs(real[2] - (100000.0 / 1.3)) < 1.0

    def test_deflate_series_missing(self, cpi_service):
        dates = [date(2022, 6, 15), date(2023, 1, 15)]
        nominal = [100000.0, 100000.0]
        real, mode = cpi_service.deflate_series(dates, nominal, base_date=date(2023, 1, 1))
        assert mode == "CPI_MISSING"
        assert real[0] is None
        assert real[1] is not None

    def test_available_range(self, cpi_service):
        r = cpi_service.get_available_range()
        assert r == (date(2023, 1, 1), date(2024, 2, 1))

    def test_series_names(self, cpi_service):
        assert "CPI_NGN" in cpi_service.series_names


# ── 5. DB Round-Trip ─────────────────────────────────────────────────


class TestDbRoundTrip:

    @pytest.mark.asyncio
    async def test_fx_rate_persist(self, session, fx_provider):
        result = fx_provider.parse_csv_string(SAMPLE_FX_CSV)
        for i, r in enumerate(result.rates):
            session.add(FxRate(id=i + 1, **r))
        await session.commit()

        count = (await session.execute(
            select(func.count()).select_from(FxRate)
        )).scalar()
        assert count == 8

        stmt = select(FxRate).where(
            FxRate.pair == "USDNGN", FxRate.ts == date(2024, 1, 2)
        )
        row = (await session.execute(stmt)).scalar_one()
        assert row.rate == 907.50

    @pytest.mark.asyncio
    async def test_macro_series_persist(self, session, cpi_provider):
        result = cpi_provider.parse_csv_string(SAMPLE_CPI_CSV)
        for i, e in enumerate(result.entries):
            session.add(MacroSeries(id=i + 1, **e))
        await session.commit()

        count = (await session.execute(
            select(func.count()).select_from(MacroSeries)
        )).scalar()
        assert count == 9

    @pytest.mark.asyncio
    async def test_fx_rate_unique_constraint(self, session):
        from sqlalchemy.exc import IntegrityError

        r1 = FxRate(id=1, pair="USDNGN", ts=date(2024, 1, 1), rate=900.0,
                     source="TEST", ingested_at=datetime.utcnow())
        r2 = FxRate(id=2, pair="USDNGN", ts=date(2024, 1, 1), rate=905.0,
                     source="TEST2", ingested_at=datetime.utcnow())
        session.add(r1)
        await session.flush()
        session.add(r2)
        with pytest.raises(IntegrityError):
            await session.flush()


# ── 6. FX Devaluation Impact ─────────────────────────────────────────


class TestFxDevaluationImpact:
    """
    Verify that Naira devaluation correctly reduces USD-reported values.
    This is the core business reason for FX reporting.
    """

    def test_devaluation_reduces_usd_value(self):
        """
        Portfolio worth 1M NGN on both dates.
        If USDNGN goes from 900 to 1500, the USD value drops.
        """
        rates = [
            {"pair": "USDNGN", "ts": date(2023, 1, 1), "rate": 900.0},
            {"pair": "USDNGN", "ts": date(2024, 1, 1), "rate": 1500.0},
        ]
        svc = FxRateService(rates)
        dates = [date(2023, 1, 1), date(2024, 1, 1)]
        ngn = [1_000_000.0, 1_000_000.0]
        usd, mode = svc.convert_series("USDNGN", dates, ngn)
        assert mode == "FX_FULL"
        # 2023: 1M / 900 = $1,111.11
        assert abs(usd[0] - 1111.11) < 1.0
        # 2024: 1M / 1500 = $666.67 — 40% drop in USD!
        assert abs(usd[1] - 666.67) < 1.0
        assert usd[1] < usd[0]  # USD value dropped

    def test_inflation_erodes_real_value(self):
        """
        100K NGN in Jan 2023 vs Jan 2024 with 30% CPI increase.
        Real value of 100K in Jan 2024 < 100K in Jan 2023 terms.
        """
        entries = [
            {"series_name": "CPI_NGN", "ts": date(2023, 1, 1), "value": 100.0},
            {"series_name": "CPI_NGN", "ts": date(2024, 1, 1), "value": 130.0},
        ]
        svc = CpiService(entries)
        dates = [date(2023, 1, 1), date(2024, 1, 1)]
        nominal = [100_000.0, 100_000.0]
        real, mode = svc.deflate_series(dates, nominal, base_date=date(2023, 1, 1))
        assert mode == "CPI_FULL"
        # 2023: 100K / 1.0 = 100K (base year)
        assert abs(real[0] - 100_000.0) < 0.01
        # 2024: 100K / 1.3 ≈ 76,923 — purchasing power dropped
        assert abs(real[1] - 76_923.08) < 1.0
        assert real[1] < real[0]
