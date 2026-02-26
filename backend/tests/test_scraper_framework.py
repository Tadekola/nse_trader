"""
Tests for the scraper framework.

Covers:
1. FundamentalsStore (SQLite cache operations)
2. ScrapedFundamentals data class
3. FundamentalsValidator
4. ValuationEngine (fair value + health score)
5. StockAnalysisScraper (unit: parse_number)
6. NgnmarketFundamentalsScraper (unit: HTML parsing)
7. ScraperRunner (integration with mocked scrapers)
"""

import json
import pytest
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.scrapers.base import ScrapedFundamentals, ScrapeBatchResult, SymbolResult
from app.scrapers.store import FundamentalsStore
from app.scrapers.stockanalysis import parse_number, _extract_year, _get_year_columns
from app.scrapers.ngnmarket_fundamentals import (
    NgnmarketFundamentalsScraper, _parse_float, _parse_market_cap,
)
from app.scrapers.valuation import ValuationEngine, FairValueResult, HealthResult
from app.scrapers.runner import FundamentalsValidator, ScraperRunner, RunResult


# ═══════════════════════════════════════════════════════════════════════
# FundamentalsStore Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFundamentalsStore:
    """Test the SQLite cache layer."""

    @pytest.fixture
    def store(self, tmp_path):
        return FundamentalsStore(db_path=tmp_path / "test_cache.db")

    def test_init_creates_db(self, store):
        assert store._db_path.exists()

    def test_put_and_get(self, store):
        store.put("src", "GTCO", date(2024, 12, 31), {"revenue": 500e9})
        cached = store.get_cached("src", "GTCO")
        assert len(cached) == 1
        assert cached[0]["revenue"] == 500e9

    def test_is_fresh_true(self, store):
        store.put("src", "GTCO", date(2024, 12, 31), {"revenue": 1})
        assert store.is_fresh("src", "GTCO", max_age_days=7) is True

    def test_is_fresh_false_no_data(self, store):
        assert store.is_fresh("src", "UNKNOWN", max_age_days=7) is False

    def test_put_replaces_on_conflict(self, store):
        store.put("src", "GTCO", date(2024, 12, 31), {"revenue": 100})
        store.put("src", "GTCO", date(2024, 12, 31), {"revenue": 200})
        cached = store.get_cached("src", "GTCO")
        assert len(cached) == 1
        assert cached[0]["revenue"] == 200

    def test_multiple_periods(self, store):
        store.put("src", "GTCO", date(2024, 12, 31), {"revenue": 100})
        store.put("src", "GTCO", date(2023, 12, 31), {"revenue": 80})
        cached = store.get_cached("src", "GTCO")
        assert len(cached) == 2
        # Ordered by period_end DESC
        assert cached[0]["revenue"] == 100  # 2024
        assert cached[1]["revenue"] == 80   # 2023

    def test_get_all_symbols(self, store):
        store.put("src", "GTCO", date(2024, 12, 31), {})
        store.put("src", "DANGCEM", date(2024, 12, 31), {})
        symbols = store.get_all_symbols("src")
        assert set(symbols) == {"GTCO", "DANGCEM"}

    def test_count(self, store):
        store.put("src", "GTCO", date(2024, 12, 31), {})
        store.put("src", "GTCO", date(2023, 12, 31), {})
        assert store.count("src") == 2
        assert store.count() == 2

    def test_record_run(self, store):
        now = datetime.now(timezone.utc)
        store.record_run(
            source="test", started_at=now, finished_at=now,
            total=10, succeeded=8, failed=2,
        )
        run = store.get_last_run("test")
        assert run is not None
        assert run["succeeded"] == 8

    def test_put_batch(self, store):
        records = [
            {"symbol": "GTCO", "period_end_date": date(2024, 12, 31), "revenue": 100},
            {"symbol": "UBA", "period_end_date": date(2024, 12, 31), "revenue": 200},
        ]
        count = store.put_batch("src", records)
        assert count == 2
        assert store.count("src") == 2

    def test_purge_old(self, store):
        # Manually insert an old record
        import sqlite3
        old_time = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        with sqlite3.connect(str(store._db_path)) as conn:
            conn.execute(
                "INSERT INTO scraped_fundamentals (source, symbol, period_end, data_json, scraped_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("src", "OLD", "2020-12-31", "{}", old_time),
            )
        assert store.count() == 1
        deleted = store.purge_old(max_age_days=90)
        assert deleted == 1
        assert store.count() == 0


# ═══════════════════════════════════════════════════════════════════════
# ScrapedFundamentals Tests
# ═══════════════════════════════════════════════════════════════════════

class TestScrapedFundamentals:
    def test_field_count(self):
        f = ScrapedFundamentals(
            symbol="GTCO", period_end_date=date(2024, 12, 31),
            period_type="ANNUAL", revenue=500e9, net_income=100e9,
        )
        assert f.field_count() == 2

    def test_to_dict(self):
        f = ScrapedFundamentals(
            symbol="GTCO", period_end_date=date(2024, 12, 31),
            period_type="ANNUAL", revenue=500e9,
        )
        d = f.to_dict()
        assert d["symbol"] == "GTCO"
        assert d["revenue"] == 500e9
        assert d["period_type"] == "ANNUAL"

    def test_field_count_all_populated(self):
        f = ScrapedFundamentals(
            symbol="X", period_end_date=date(2024, 12, 31), period_type="ANNUAL",
            revenue=1, operating_profit=2, net_income=3, total_assets=4,
            total_equity=5, total_debt=6, cash=7, operating_cash_flow=8,
            capex=9, dividends_paid=10,
        )
        assert f.field_count() == 10


# ═══════════════════════════════════════════════════════════════════════
# StockAnalysis parse_number Tests
# ═══════════════════════════════════════════════════════════════════════

class TestParseNumber:
    def test_normal_thousands(self):
        # stockanalysis shows in thousands
        assert parse_number("3,580,550") == 3_580_550_000

    def test_negative_parens(self):
        assert parse_number("(97,000)") == -97_000_000

    def test_negative_dash(self):
        assert parse_number("-97,000") == -97_000_000

    def test_percentage_returns_none(self):
        assert parse_number("28.29%") is None

    def test_na_returns_none(self):
        assert parse_number("N/A") is None

    def test_empty_returns_none(self):
        assert parse_number("") is None
        assert parse_number("-") is None

    def test_upgrade_returns_none(self):
        assert parse_number("Upgrade") is None

    def test_suffix_B(self):
        assert parse_number("1.5B") == 1_500_000_000

    def test_suffix_M(self):
        assert parse_number("250M") == 250_000_000

    def test_extract_year(self):
        assert _extract_year("FY 2024") == "2024"
        assert _extract_year("2023") == "2023"
        assert _extract_year("TTM") is None

    def test_get_year_columns(self):
        rows = [{"metric": "Revenue", "FY 2024": "100", "FY 2023": "80", "TTM": "110"}]
        cols = _get_year_columns(rows)
        assert len(cols) == 2
        assert ("FY 2024", "2024") in cols
        assert ("FY 2023", "2023") in cols


# ═══════════════════════════════════════════════════════════════════════
# Ngnmarket parse Tests
# ═══════════════════════════════════════════════════════════════════════

class TestNgnmarketParsing:
    def test_parse_float_basic(self):
        assert _parse_float("12.34") == 12.34

    def test_parse_float_currency(self):
        assert _parse_float("₦12.34") == 12.34

    def test_parse_float_commas(self):
        assert _parse_float("1,234.56") == 1234.56

    def test_parse_float_none(self):
        assert _parse_float("") is None
        assert _parse_float("N/A") is None

    def test_parse_market_cap_trillion(self):
        assert _parse_market_cap("₦1.23T") == 1.23e12

    def test_parse_market_cap_billion(self):
        assert _parse_market_cap("₦456.7B") == 456.7e9

    def test_ngnmarket_parse_html(self):
        scraper = NgnmarketFundamentalsScraper()
        html = """
        <table>
          <tr><td>P/E Ratio</td><td>5.23</td></tr>
          <tr><td>EPS</td><td>₦12.34</td></tr>
          <tr><td>Dividend Yield</td><td>3.5%</td></tr>
          <tr><td>Market Capitalization</td><td>₦1.2T</td></tr>
        </table>
        """
        result = scraper._parse_html("GTCO", html)
        assert result is not None
        assert result.pe_ratio == 5.23
        assert result.eps == 12.34
        assert result.dividend_yield == 3.5


# ═══════════════════════════════════════════════════════════════════════
# FundamentalsValidator Tests
# ═══════════════════════════════════════════════════════════════════════

class TestValidator:
    @pytest.fixture
    def validator(self):
        return FundamentalsValidator()

    def test_valid_period(self, validator):
        p = ScrapedFundamentals(
            symbol="GTCO", period_end_date=date(2024, 12, 31),
            period_type="ANNUAL", revenue=500e9, net_income=100e9,
            total_assets=3000e9, total_equity=400e9,
        )
        warnings = validator.validate(p)
        assert len(warnings) == 0

    def test_too_few_fields(self, validator):
        p = ScrapedFundamentals(
            symbol="GTCO", period_end_date=date(2024, 12, 31),
            period_type="ANNUAL", revenue=500e9,
        )
        warnings = validator.validate(p)
        assert any("fields populated" in w for w in warnings)

    def test_negative_revenue(self, validator):
        p = ScrapedFundamentals(
            symbol="X", period_end_date=date(2024, 12, 31),
            period_type="ANNUAL", revenue=-100, net_income=1,
            total_assets=1, total_equity=1,
        )
        warnings = validator.validate(p)
        assert any("Negative revenue" in w for w in warnings)

    def test_equity_exceeds_assets(self, validator):
        p = ScrapedFundamentals(
            symbol="X", period_end_date=date(2024, 12, 31),
            period_type="ANNUAL", revenue=1, net_income=1,
            total_assets=100, total_equity=200,
        )
        warnings = validator.validate(p)
        assert any("Equity" in w and "exceeds" in w for w in warnings)

    def test_date_out_of_range(self, validator):
        p = ScrapedFundamentals(
            symbol="X", period_end_date=date(2010, 12, 31),
            period_type="ANNUAL", revenue=1, net_income=1,
            total_assets=1, total_equity=1,
        )
        warnings = validator.validate(p)
        assert any("out of range" in w for w in warnings)


# ═══════════════════════════════════════════════════════════════════════
# ValuationEngine Tests
# ═══════════════════════════════════════════════════════════════════════

class TestValuationEngine:
    @pytest.fixture
    def engine(self):
        return ValuationEngine()

    def test_fair_value_profitable_company(self, engine):
        result = engine.compute_fair_value(
            symbol="GTCO",
            current_price=50.0,
            latest_period={
                "net_income": 300e9,
                "total_equity": 1000e9,
                "shares_outstanding": 29e9,
            },
            sector="Financial Services",
        )
        assert result.eps is not None
        assert result.eps > 0
        assert result.earnings_value is not None
        assert result.blended_value is not None
        assert result.verdict in ("UNDERVALUED", "FAIR", "OVERVALUED")
        assert result.confidence in ("MEDIUM", "HIGH")

    def test_fair_value_no_data(self, engine):
        result = engine.compute_fair_value(
            symbol="X", current_price=100.0, latest_period={},
        )
        assert result.verdict == "UNKNOWN"
        assert result.confidence == "LOW"

    def test_fair_value_negative_earnings(self, engine):
        result = engine.compute_fair_value(
            symbol="X",
            current_price=50.0,
            latest_period={
                "net_income": -100e9,
                "total_equity": 500e9,
                "shares_outstanding": 10e9,
            },
        )
        # Negative EPS → no earnings-based value
        assert result.earnings_value is None
        # But asset value should exist
        assert result.asset_value is not None

    def test_health_score_strong_company(self, engine):
        periods = [
            {
                "net_income": 300e9, "revenue": 800e9,
                "operating_profit": 400e9,
                "total_equity": 1000e9, "total_debt": 200e9,
                "cash": 500e9, "total_assets": 3000e9,
                "operating_cash_flow": 350e9, "capex": 50e9,
            },
            {
                "net_income": 250e9, "revenue": 700e9,
                "operating_profit": 350e9,
                "total_equity": 900e9, "total_debt": 250e9,
                "cash": 400e9, "total_assets": 2800e9,
                "operating_cash_flow": 280e9, "capex": 40e9,
            },
        ]
        result = engine.compute_health("GTCO", periods)
        assert result.overall_score >= 50
        assert result.grade in ("A", "B", "C")
        assert len(result.factors) == 6

    def test_health_score_no_data(self, engine):
        result = engine.compute_health("X", [])
        assert result.grade == "F"
        assert "No financial data" in result.weaknesses[0]

    def test_health_score_single_period(self, engine):
        result = engine.compute_health("X", [{"net_income": 100, "revenue": 500}])
        assert result.overall_score > 0
        # Growth and stability should default to 50 (insufficient history)
        growth_factor = next(f for f in result.factors if f.name == "growth")
        assert growth_factor.score == 50.0

    def test_health_grade_mapping(self, engine):
        assert engine._score_to_grade(85) == "A"
        assert engine._score_to_grade(70) == "B"
        assert engine._score_to_grade(55) == "C"
        assert engine._score_to_grade(40) == "D"
        assert engine._score_to_grade(20) == "F"


# ═══════════════════════════════════════════════════════════════════════
# ScraperRunner Tests (with mocked scrapers)
# ═══════════════════════════════════════════════════════════════════════

class TestScraperRunner:
    @pytest.fixture
    def runner(self, tmp_path):
        store = FundamentalsStore(db_path=tmp_path / "test_runner.db")
        runner = ScraperRunner(store=store)
        return runner

    @pytest.mark.asyncio
    async def test_run_with_mocked_scrapers(self, runner):
        """Test the full pipeline with mocked scraper results."""
        # Mock primary scraper
        mock_primary_result = ScrapeBatchResult(
            source="stockanalysis", total_symbols=2,
            succeeded=2, failed=0, total_periods=4,
            results=[
                SymbolResult(symbol="GTCO", success=True, periods=[
                    ScrapedFundamentals(
                        symbol="GTCO", period_end_date=date(2024, 12, 31),
                        period_type="ANNUAL", revenue=500e9, net_income=100e9,
                        total_assets=3000e9, total_equity=400e9,
                        source="stockanalysis",
                    ),
                    ScrapedFundamentals(
                        symbol="GTCO", period_end_date=date(2023, 12, 31),
                        period_type="ANNUAL", revenue=450e9, net_income=90e9,
                        total_assets=2800e9, total_equity=380e9,
                        source="stockanalysis",
                    ),
                ]),
                SymbolResult(symbol="DANGCEM", success=True, periods=[
                    ScrapedFundamentals(
                        symbol="DANGCEM", period_end_date=date(2024, 12, 31),
                        period_type="ANNUAL", revenue=800e9, net_income=200e9,
                        total_assets=2000e9, total_equity=600e9,
                        source="stockanalysis",
                    ),
                    ScrapedFundamentals(
                        symbol="DANGCEM", period_end_date=date(2023, 12, 31),
                        period_type="ANNUAL", revenue=750e9, net_income=180e9,
                        total_assets=1900e9, total_equity=550e9,
                        source="stockanalysis",
                    ),
                ]),
            ],
        )

        # Mock validation scraper
        mock_val_result = ScrapeBatchResult(
            source="ngnmarket_fundamentals", total_symbols=2,
            succeeded=2, failed=0, total_periods=2,
        )

        runner.primary.scrape_batch = AsyncMock(return_value=mock_primary_result)
        runner.validation.scrape_batch = AsyncMock(return_value=mock_val_result)

        result = await runner.run(symbols=["GTCO", "DANGCEM"])

        assert result.periods_persisted == 4
        assert result.periods_rejected == 0
        assert result.primary_result.succeeded == 2

    @pytest.mark.asyncio
    async def test_run_rejects_low_quality(self, runner):
        """Test that periods with too few fields are rejected."""
        mock_result = ScrapeBatchResult(
            source="stockanalysis", total_symbols=1,
            succeeded=1, failed=0, total_periods=1,
            results=[
                SymbolResult(symbol="X", success=True, periods=[
                    ScrapedFundamentals(
                        symbol="X", period_end_date=date(2024, 12, 31),
                        period_type="ANNUAL", revenue=100,
                        source="stockanalysis",
                    ),
                ]),
            ],
        )
        mock_val = ScrapeBatchResult(source="ngnmarket_fundamentals")

        runner.primary.scrape_batch = AsyncMock(return_value=mock_result)
        runner.validation.scrape_batch = AsyncMock(return_value=mock_val)

        result = await runner.run(symbols=["X"])
        assert result.periods_rejected == 1
        assert result.periods_persisted == 0
