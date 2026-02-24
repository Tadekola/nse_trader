"""
Tests for NGX Official List PDF Provider (P0.5-1).

Covers:
  1. NgxOfficialListParser — header detection, row parsing, numeric handling,
     symbol normalization, quality flags
  2. ReconciliationService — insert/skip/update/conflict logic, audit events
  3. NgxOfficialListDownloader — cache hit, HTTP mock
  4. Integration — backfill_via_ngx_pdf wiring (mocked network)
  5. Real fixture test — auto-detects PDFs in tests/fixtures/ (skipped if none)
"""

import sys
import os
import glob
import pytest
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data.historical.storage import (
    HistoricalOHLCVStorage,
    OHLCVRecord,
)
from app.data.sources.ngx_official_list import (
    NgxOfficialListParser,
    ParsedRow,
    PDFProvenance,
    SOURCE_NAME,
)
from app.data.sources.reconciliation import (
    ReconciliationService,
    ReconciliationReport,
    NGX_PDF_SOURCE,
    NGNMARKET_SOURCE,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def parser():
    return NgxOfficialListParser()


@pytest.fixture
def temp_storage():
    """Create a temp SQLite storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_reconciliation.db"
        storage = HistoricalOHLCVStorage(db_path=db_path)
        yield storage
        storage.close()


@pytest.fixture
def reconciler(temp_storage):
    return ReconciliationService(storage=temp_storage, divergence_threshold_pct=2.0)


# ── Sample table data (mimics pdfplumber extract_tables output) ──────

SAMPLE_HEADER = [
    "S/N", "Security", "Prev. Close", "Open", "High", "Low",
    "Close", "Change", "Trades", "Volume", "Value"
]

SAMPLE_ROWS = [
    ["1", "DANGCEM", "290.00", "290.50", "295.00", "289.00", "293.50", "3.50", "150", "1,234,567", "362,345,678.50"],
    ["2", "GTCO", "42.50", "42.50", "43.00", "42.00", "42.80", "0.30", "89", "5,678,901", "242,567,890.00"],
    ["3", "MTNN", "195.00", "195.50", "198.00", "194.50", "197.20", "2.20", "210", "3,456,789", "681,234,567.00"],
    ["4", "ZENITHBANK", "35.00", "35.10", "35.50", "34.90", "35.30", "0.30", "120", "8,901,234", "314,123,456.00"],
    ["5", "AIRTELAFRI", "2100.00", "2105.00", "2150.00", "2090.00", "2130.00", "30.00", "50", "123,456", "262,890,000.00"],
]


# ── 1. Parser Tests ──────────────────────────────────────────────────


class TestHeaderDetection:
    """Test that _detect_header correctly identifies header rows."""

    def test_standard_header(self, parser):
        result = parser._detect_header(SAMPLE_HEADER)
        assert result is not None
        assert "security" in result.values()
        assert "close" in result.values()

    def test_alternate_header_names(self, parser):
        alt_header = ["No.", "Stock", "Ref Price", "Opening", "Highest", "Lowest", "Closing", "Chg"]
        result = parser._detect_header(alt_header)
        assert result is not None
        assert "security" in result.values()
        assert "close" in result.values()

    def test_missing_security_rejects(self, parser):
        no_security = ["S/N", "Open", "High", "Low", "Close"]
        result = parser._detect_header(no_security)
        assert result is None

    def test_missing_close_rejects(self, parser):
        no_close = ["S/N", "Security", "Open", "High", "Low"]
        result = parser._detect_header(no_close)
        assert result is None

    def test_empty_row_rejects(self, parser):
        result = parser._detect_header([None, None, None])
        assert result is None

    def test_is_header_row_detects_repeated_header(self, parser):
        assert parser._is_header_row(SAMPLE_HEADER)
        assert not parser._is_header_row(SAMPLE_ROWS[0])


class TestRowParsing:
    """Test _parse_data_row extracts correct values."""

    def _get_column_map(self, parser) -> Dict[int, str]:
        result = parser._detect_header(SAMPLE_HEADER)
        assert result is not None
        return result

    def test_parse_dangcem(self, parser):
        col_map = self._get_column_map(parser)
        row = parser._parse_data_row(SAMPLE_ROWS[0], col_map, date(2026, 2, 2))
        assert row is not None
        assert row.symbol == "DANGCEM"
        assert row.close == 293.50
        assert row.open == 290.50
        assert row.high == 295.00
        assert row.low == 289.00
        assert row.volume == 1234567
        assert row.has_all_ohlcv is True
        assert row.missing_fields == []

    def test_parse_mtnn(self, parser):
        col_map = self._get_column_map(parser)
        row = parser._parse_data_row(SAMPLE_ROWS[2], col_map, date(2026, 2, 2))
        assert row is not None
        assert row.symbol == "MTNN"
        assert row.close == 197.20

    def test_parse_with_commas_in_volume(self, parser):
        col_map = self._get_column_map(parser)
        row = parser._parse_data_row(SAMPLE_ROWS[3], col_map, date(2026, 2, 2))
        assert row is not None
        assert row.volume == 8901234

    def test_to_ohlcv_record(self, parser):
        col_map = self._get_column_map(parser)
        row = parser._parse_data_row(SAMPLE_ROWS[0], col_map, date(2026, 2, 2))
        record = row.to_ohlcv_record()
        assert record is not None
        assert record.symbol == "DANGCEM"
        assert record.source == SOURCE_NAME
        assert record.date == date(2026, 2, 2)
        assert record.close == 293.50

    def test_missing_close_returns_none_record(self, parser):
        col_map = self._get_column_map(parser)
        # Row with no close price
        bad_row = ["6", "BADSTOCK", "10.00", "10.00", "10.00", "10.00", "-", "0", "0", "0", "0"]
        row = parser._parse_data_row(bad_row, col_map, date(2026, 2, 2))
        assert row is not None
        assert row.close is None
        assert "close" in row.missing_fields
        assert row.to_ohlcv_record() is None


class TestSymbolNormalization:
    """Test _normalize_symbol handles various PDF formats."""

    def test_plain_symbol(self, parser):
        assert parser._normalize_symbol("DANGCEM") == "DANGCEM"

    def test_plc_suffix_stripped(self, parser):
        assert parser._normalize_symbol("DANGCEM PLC") == "DANGCEM"

    def test_ltd_suffix_stripped(self, parser):
        assert parser._normalize_symbol("NESTLE NIG LTD") == "NESTLE"

    def test_serial_number_rejected(self, parser):
        assert parser._normalize_symbol("123") is None

    def test_total_row_rejected(self, parser):
        assert parser._normalize_symbol("Total") is None

    def test_grand_total_rejected(self, parser):
        assert parser._normalize_symbol("Grand Total") is None

    def test_main_board_rejected(self, parser):
        assert parser._normalize_symbol("Main Board") is None

    def test_empty_rejected(self, parser):
        assert parser._normalize_symbol("") is None


class TestNumericParsing:
    """Test price/volume/change parsing edge cases."""

    def test_parse_price_with_commas(self):
        assert NgxOfficialListParser._parse_price("1,234.50") == 1234.50

    def test_parse_price_with_currency(self):
        assert NgxOfficialListParser._parse_price("₦42.50") == 42.50

    def test_parse_price_dash(self):
        assert NgxOfficialListParser._parse_price("-") is None

    def test_parse_price_na(self):
        assert NgxOfficialListParser._parse_price("N/A") is None

    def test_parse_price_none(self):
        assert NgxOfficialListParser._parse_price(None) is None

    def test_parse_change_negative_parens(self):
        assert NgxOfficialListParser._parse_change("(1.50)") == -1.50

    def test_parse_change_positive(self):
        assert NgxOfficialListParser._parse_change("3.50") == 3.50

    def test_parse_int_with_commas(self):
        assert NgxOfficialListParser._parse_int("1,234,567") == 1234567

    def test_parse_int_dash(self):
        assert NgxOfficialListParser._parse_int("-") is None


# ── 2. Reconciliation Tests ─────────────────────────────────────────


class TestReconciliation:
    """Test ReconciliationService logic."""

    def test_insert_when_no_existing(self, reconciler, temp_storage):
        """New record for empty symbol → inserted."""
        records = [
            OHLCVRecord(
                symbol="DANGCEM", date=date(2026, 2, 2),
                open=290.50, high=295.00, low=289.00, close=293.50,
                volume=1234567, source=NGX_PDF_SOURCE,
            )
        ]
        report = reconciler.reconcile_records(records)
        assert report.inserted == 1
        assert report.skipped == 0
        assert report.updated == 0

        # Verify stored
        stored = temp_storage.get_ohlcv("DANGCEM", start_date=date(2026, 2, 2), end_date=date(2026, 2, 2))
        assert len(stored) == 1
        assert stored[0].close == 293.50
        assert stored[0].source == NGX_PDF_SOURCE

    def test_skip_when_same_source(self, reconciler, temp_storage):
        """Same source for same (symbol, date) → skipped."""
        record = OHLCVRecord(
            symbol="DANGCEM", date=date(2026, 2, 2),
            open=290.50, high=295.00, low=289.00, close=293.50,
            volume=1234567, source=NGX_PDF_SOURCE,
        )
        temp_storage.store_ohlcv(record)

        # Try reconciling same source
        report = reconciler.reconcile_records([record])
        assert report.skipped == 1
        assert report.inserted == 0

    def test_skip_when_close_agrees(self, reconciler, temp_storage):
        """Different source, close within threshold → skipped."""
        # Store from ngnmarket
        existing = OHLCVRecord(
            symbol="DANGCEM", date=date(2026, 2, 2),
            open=290.50, high=295.00, low=289.00, close=293.50,
            volume=1234567, source=NGNMARKET_SOURCE,
        )
        temp_storage.store_ohlcv(existing)

        # Reconcile with PDF (close within 2%)
        pdf_record = OHLCVRecord(
            symbol="DANGCEM", date=date(2026, 2, 2),
            open=290.50, high=295.00, low=289.00, close=293.80,  # 0.1% diff
            volume=1234567, source=NGX_PDF_SOURCE,
        )
        report = reconciler.reconcile_records([pdf_record])
        assert report.skipped == 1
        assert report.updated == 0

    def test_update_when_close_diverges_preferred_source(self, reconciler, temp_storage):
        """Different source, close diverges, preferred source → updated + audit event."""
        # Store from ngnmarket
        existing = OHLCVRecord(
            symbol="DANGCEM", date=date(2026, 2, 2),
            open=290.50, high=295.00, low=289.00, close=293.50,
            volume=1234567, source=NGNMARKET_SOURCE,
        )
        temp_storage.store_ohlcv(existing)

        # Reconcile with PDF (close diverges > 2%)
        pdf_record = OHLCVRecord(
            symbol="DANGCEM", date=date(2026, 2, 2),
            open=290.50, high=295.00, low=289.00, close=310.00,  # ~5.6% diff
            volume=1234567, source=NGX_PDF_SOURCE,
        )
        report = reconciler.reconcile_records([pdf_record])
        assert report.updated == 1
        assert len(report.audit_events) == 1
        assert report.audit_events[0]["event_type"] == "RECONCILIATION_UPDATE"

        # Verify storage was updated to PDF value
        stored = temp_storage.get_ohlcv("DANGCEM", start_date=date(2026, 2, 2), end_date=date(2026, 2, 2))
        assert len(stored) == 1
        assert stored[0].close == 310.00
        assert stored[0].source == NGX_PDF_SOURCE

    def test_conflict_when_close_diverges_non_preferred(self, reconciler, temp_storage):
        """Different source, close diverges, non-preferred source → conflict logged."""
        # Store from NGX PDF (already preferred) — data must pass OHLCV validation
        existing = OHLCVRecord(
            symbol="DANGCEM", date=date(2026, 2, 2),
            open=305.00, high=312.00, low=300.00, close=310.00,
            volume=1234567, source=NGX_PDF_SOURCE,
        )
        temp_storage.store_ohlcv(existing)

        # Try reconciling with ngnmarket (NOT preferred) — diverges
        ngnmarket_record = OHLCVRecord(
            symbol="DANGCEM", date=date(2026, 2, 2),
            open=290.50, high=295.00, low=289.00, close=293.50,
            volume=1234567, source=NGNMARKET_SOURCE,
        )
        report = reconciler.reconcile_records(
            [ngnmarket_record], preferred_source=NGX_PDF_SOURCE
        )
        assert report.conflicts == 1
        assert report.updated == 0
        assert len(report.audit_events) == 1
        assert report.audit_events[0]["event_type"] == "RECONCILIATION_CONFLICT"

        # Storage unchanged (still PDF value)
        stored = temp_storage.get_ohlcv("DANGCEM", start_date=date(2026, 2, 2), end_date=date(2026, 2, 2))
        assert stored[0].close == 310.00

    def test_batch_reconciliation(self, reconciler, temp_storage):
        """Multiple records in one reconciliation run."""
        records = [
            OHLCVRecord(
                symbol=sym, date=date(2026, 2, 2),
                open=100.0, high=110.0, low=90.0, close=105.0,
                volume=10000, source=NGX_PDF_SOURCE,
            )
            for sym in ["DANGCEM", "GTCO", "MTNN"]
        ]
        report = reconciler.reconcile_records(records)
        assert report.inserted == 3
        assert report.summary() == "Reconciliation: inserted=3, updated=0, skipped=0, conflicts=0"

    def test_audit_event_payload_structure(self, reconciler, temp_storage):
        """Verify audit events carry correct payload fields."""
        existing = OHLCVRecord(
            symbol="GTCO", date=date(2026, 2, 2),
            open=42.50, high=43.00, low=42.00, close=42.80,
            volume=5000000, source=NGNMARKET_SOURCE,
        )
        temp_storage.store_ohlcv(existing)

        pdf_record = OHLCVRecord(
            symbol="GTCO", date=date(2026, 2, 2),
            open=42.50, high=43.00, low=42.00, close=50.00,  # big divergence
            volume=5000000, source=NGX_PDF_SOURCE,
        )
        report = reconciler.reconcile_records([pdf_record])
        assert len(report.audit_events) == 1

        evt = report.audit_events[0]
        assert evt["component"] == "reconciliation"
        assert "payload" in evt
        payload = evt["payload"]
        assert payload["symbol"] == "GTCO"
        assert payload["existing_source"] == NGNMARKET_SOURCE
        assert payload["new_source"] == NGX_PDF_SOURCE
        assert payload["divergence_pct"] > 2.0


# ── 3. Downloader Tests ─────────────────────────────────────────────


class TestDownloader:
    """Test NgxOfficialListDownloader with mocked httpx."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_download(self):
        """If PDF already cached locally, no HTTP request made."""
        from app.data.sources.ngx_official_list import NgxOfficialListDownloader

        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-create a cached file
            cache_path = Path(tmpdir) / "ngx_daily_list_2026-02-02.pdf"
            cache_path.write_bytes(b"%PDF-1.4 fake content")

            with patch("app.core.config.get_settings") as mock_settings:
                settings = MagicMock()
                settings.NGX_PDF_CACHE_DIR = tmpdir
                settings.NGX_PDF_URL_TEMPLATE = "https://example.com/{dd}-{mm}-{yyyy}.pdf"
                mock_settings.return_value = settings

                downloader = NgxOfficialListDownloader(cache_dir=tmpdir)
                result = await downloader.download(date(2026, 2, 2))

                assert result is not None
                path, provenance = result
                assert path == cache_path
                assert provenance.source == SOURCE_NAME
                assert provenance.trade_date == date(2026, 2, 2)
                assert provenance.sha256 != ""

    @pytest.mark.asyncio
    async def test_404_returns_none(self):
        """404 response returns None (missing PDF for that date)."""
        from app.data.sources.ngx_official_list import NgxOfficialListDownloader
        import httpx

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.core.config.get_settings") as mock_settings:
                settings = MagicMock()
                settings.NGX_PDF_CACHE_DIR = tmpdir
                settings.NGX_PDF_URL_TEMPLATE = "https://example.com/{dd}-{mm}-{yyyy}.pdf"
                mock_settings.return_value = settings

                downloader = NgxOfficialListDownloader(cache_dir=tmpdir)

                mock_response = MagicMock(spec=httpx.Response)
                mock_response.status_code = 404

                with patch("app.data.sources.ngx_official_list.http_fetch", new_callable=AsyncMock) as mock_fetch:
                    mock_fetch.return_value = mock_response

                    result = await downloader.download(date(2026, 2, 2))
                    assert result is None


# ── 4. update_ohlcv Storage Tests ───────────────────────────────────


class TestUpdateOhlcv:
    """Test the update_ohlcv method added for reconciliation."""

    def test_update_existing_record(self, temp_storage):
        """update_ohlcv overwrites OHLCV values and source."""
        original = OHLCVRecord(
            symbol="DANGCEM", date=date(2026, 2, 2),
            open=290.50, high=295.00, low=289.00, close=293.50,
            volume=1234567, source=NGNMARKET_SOURCE,
        )
        temp_storage.store_ohlcv(original)

        updated = OHLCVRecord(
            symbol="DANGCEM", date=date(2026, 2, 2),
            open=291.00, high=296.00, low=290.00, close=310.00,
            volume=1300000, source=NGX_PDF_SOURCE,
        )
        success = temp_storage.update_ohlcv(updated)
        assert success is True

        stored = temp_storage.get_ohlcv("DANGCEM", start_date=date(2026, 2, 2), end_date=date(2026, 2, 2))
        assert len(stored) == 1
        assert stored[0].close == 310.00
        assert stored[0].source == NGX_PDF_SOURCE

    def test_update_nonexistent_returns_false(self, temp_storage):
        """update_ohlcv on a non-existent row returns False."""
        record = OHLCVRecord(
            symbol="DOESNOTEXIST", date=date(2026, 2, 2),
            open=10.0, high=10.0, low=10.0, close=10.0,
            volume=100, source=NGX_PDF_SOURCE,
        )
        success = temp_storage.update_ohlcv(record)
        assert success is False


# ── 5. Real Fixture Test (auto-skip if no PDFs) ─────────────────────


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TestRealFixture:
    """Run parser against real PDFs if any are present in tests/fixtures/."""

    def _get_fixture_pdfs(self) -> List[Path]:
        return list(FIXTURE_DIR.glob("*.pdf"))

    @pytest.mark.skipif(
        not list(Path(__file__).parent.joinpath("fixtures").glob("*.pdf")),
        reason="No real PDF fixtures found in tests/fixtures/",
    )
    def test_parse_real_fixture(self, parser):
        """Parse a real NGX Daily Official List PDF fixture."""
        pdfs = self._get_fixture_pdfs()
        for pdf_path in pdfs:
            # Extract date from filename: ngx_daily_list_YYYY-MM-DD.pdf
            stem = pdf_path.stem
            try:
                date_str = stem.split("_")[-1]
                trade_date = date.fromisoformat(date_str)
            except (ValueError, IndexError):
                trade_date = date(2026, 1, 1)

            rows = parser.parse(pdf_path, trade_date)

            # Must parse at least some rows
            assert len(rows) >= 10, f"Expected >=10 rows from {pdf_path.name}, got {len(rows)}"

            # Check for known symbols
            symbols = {r.symbol for r in rows}
            known = {"DANGCEM", "GTCO", "MTNN", "ZENITHBANK"}
            found = symbols & known
            assert len(found) >= 2, f"Expected >=2 known symbols, found: {found}"

            # All parsed rows should have a close price
            rows_with_close = [r for r in rows if r.close is not None and r.close > 0]
            assert len(rows_with_close) >= len(rows) * 0.8, ">=80% of rows should have a valid close"


# ── 6. ParsedRow quality flags ───────────────────────────────────────


class TestParsedRowQuality:
    """Test ParsedRow quality tracking."""

    def test_all_fields_present(self):
        row = ParsedRow(
            symbol="DANGCEM", trade_date=date(2026, 2, 2),
            open=290.50, high=295.00, low=289.00, close=293.50,
            volume=1234567, has_all_ohlcv=True, missing_fields=[],
        )
        record = row.to_ohlcv_record()
        assert record is not None
        assert record.open == 290.50
        assert record.volume == 1234567

    def test_missing_open_uses_close(self):
        row = ParsedRow(
            symbol="TEST", trade_date=date(2026, 2, 2),
            open=None, high=None, low=None, close=100.00,
            volume=None, has_all_ohlcv=False,
            missing_fields=["open", "high", "low", "volume"],
        )
        record = row.to_ohlcv_record()
        assert record is not None
        assert record.open == 100.00  # fallback to close
        assert record.high == 100.00
        assert record.low == 100.00
        assert record.volume == 0

    def test_no_close_returns_none(self):
        row = ParsedRow(
            symbol="TEST", trade_date=date(2026, 2, 2),
            open=100.00, high=110.00, low=90.00, close=None,
            volume=1000, has_all_ohlcv=False, missing_fields=["close"],
        )
        assert row.to_ohlcv_record() is None

    def test_zero_close_returns_none(self):
        row = ParsedRow(
            symbol="TEST", trade_date=date(2026, 2, 2),
            open=100.00, high=110.00, low=90.00, close=0.0,
            volume=1000, has_all_ohlcv=False, missing_fields=[],
        )
        assert row.to_ohlcv_record() is None
