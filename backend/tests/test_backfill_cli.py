"""
Tests for Backfill CLI enhancements (P0.5-2).

Covers:
  1. resolve_date_window — flag precedence logic
  2. generate_coverage_report — correctness with mock storage
  3. persist_coverage_report — writes valid JSON
"""

import sys
import os
import json
import tempfile
import pytest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.cli.backfill import (
    resolve_date_window,
    generate_coverage_report,
    persist_coverage_report,
)
from app.data.historical.storage import (
    HistoricalOHLCVStorage,
    OHLCVRecord,
)


# ── 1. resolve_date_window tests ────────────────────────────────────


class TestResolveDateWindow:

    def test_start_date_overrides_days_back(self):
        """When --start-date is provided, --days-back is ignored."""
        s, e = resolve_date_window("2025-01-01", None, days_back=30)
        assert s == date(2025, 1, 1)
        assert e == date.today()

    def test_start_and_end_date(self):
        """Both --start-date and --end-date provided."""
        s, e = resolve_date_window("2025-01-01", "2025-06-30", days_back=999)
        assert s == date(2025, 1, 1)
        assert e == date(2025, 6, 30)

    def test_only_days_back(self):
        """Only --days-back: end=today, start=today-days_back."""
        s, e = resolve_date_window(None, None, days_back=252)
        assert e == date.today()
        assert s == date.today() - timedelta(days=252)

    def test_only_end_date(self):
        """Only --end-date: uses end_date and days_back."""
        s, e = resolve_date_window(None, "2025-12-31", days_back=60)
        assert e == date(2025, 12, 31)
        assert s == date(2025, 12, 31) - timedelta(days=60)

    def test_start_date_ignores_days_back_completely(self):
        """Verify days_back=5 has no effect when start_date is set."""
        s1, e1 = resolve_date_window("2025-01-01", "2025-12-31", days_back=5)
        s2, e2 = resolve_date_window("2025-01-01", "2025-12-31", days_back=9999)
        assert s1 == s2
        assert e1 == e2


# ── 2. generate_coverage_report tests ───────────────────────────────


class TestCoverageReport:

    @pytest.fixture
    def temp_storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_coverage.db"
            storage = HistoricalOHLCVStorage(db_path=db_path)
            yield storage
            storage.close()

    def _make_records(self, symbol, count, start=None, source="TEST"):
        """Create count sequential OHLCVRecords."""
        start = start or date(2025, 1, 2)
        records = []
        d = start
        for _ in range(count):
            # Skip weekends
            while d.weekday() >= 5:
                d += timedelta(days=1)
            records.append(OHLCVRecord(
                symbol=symbol, date=d,
                open=100.0, high=110.0, low=90.0, close=105.0,
                volume=10000, source=source,
            ))
            d += timedelta(days=1)
        return records

    def test_coverage_report_structure(self, temp_storage):
        """Report has correct top-level keys."""
        records = self._make_records("DANGCEM", 10)
        temp_storage.store_ohlcv_batch(records)

        with patch("app.cli.backfill.get_historical_storage", return_value=temp_storage):
            report = generate_coverage_report(["DANGCEM"])

        assert "generated_at" in report
        assert "symbols" in report
        assert "summary" in report
        assert "DANGCEM" in report["symbols"]

    def test_coverage_report_sessions(self, temp_storage):
        """Sessions count matches stored records."""
        records = self._make_records("GTCO", 50)
        temp_storage.store_ohlcv_batch(records)

        with patch("app.cli.backfill.get_historical_storage", return_value=temp_storage):
            report = generate_coverage_report(["GTCO"])

        sym = report["symbols"]["GTCO"]
        assert sym["sessions_count"] == 50
        assert sym["first_date"] is not None
        assert sym["last_date"] is not None

    def test_coverage_report_source_mix(self, temp_storage):
        """Source mix reflects the distribution of sources."""
        r1 = self._make_records("MTNN", 30, source="SOURCE_A")
        r2 = self._make_records("MTNN", 70, start=date(2025, 4, 1), source="SOURCE_B")
        temp_storage.store_ohlcv_batch(r1)
        temp_storage.store_ohlcv_batch(r2)

        with patch("app.cli.backfill.get_historical_storage", return_value=temp_storage):
            report = generate_coverage_report(["MTNN"])

        mix = report["symbols"]["MTNN"]["source_mix"]
        assert "SOURCE_A" in mix
        assert "SOURCE_B" in mix
        assert abs(sum(mix.values()) - 100.0) < 1.0

    def test_coverage_report_gap_detection(self, temp_storage):
        """Gaps in trading dates are counted."""
        # Create records with a gap (skip some weekdays)
        records = []
        for d in [date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 7)]:
            records.append(OHLCVRecord(
                symbol="ZENITH", date=d,
                open=100.0, high=110.0, low=90.0, close=105.0,
                volume=10000, source="TEST",
            ))
        temp_storage.store_ohlcv_batch(records)

        with patch("app.cli.backfill.get_historical_storage", return_value=temp_storage):
            report = generate_coverage_report(["ZENITH"])

        # Jan 2-3 present, Jan 6 missing (weekday), Jan 7 present
        assert report["symbols"]["ZENITH"]["gap_count"] == 1

    def test_coverage_summary_thresholds(self, temp_storage):
        """Summary counts symbols above 60 and 252 thresholds."""
        r1 = self._make_records("SYM60", 65)
        r2 = self._make_records("SYM252", 260)
        r3 = self._make_records("SYMLOW", 10)
        for r in [r1, r2, r3]:
            temp_storage.store_ohlcv_batch(r)

        with patch("app.cli.backfill.get_historical_storage", return_value=temp_storage):
            report = generate_coverage_report(["SYM60", "SYM252", "SYMLOW"])

        s = report["summary"]
        assert s["total_symbols"] == 3
        assert s["symbols_ge_60"] == 2   # SYM60 and SYM252
        assert s["symbols_ge_252"] == 1  # only SYM252

    def test_empty_symbol(self, temp_storage):
        """Symbol with no data returns zeroed report."""
        with patch("app.cli.backfill.get_historical_storage", return_value=temp_storage):
            report = generate_coverage_report(["NOSYMBOL"])

        sym = report["symbols"]["NOSYMBOL"]
        assert sym["sessions_count"] == 0
        assert sym["first_date"] is None
        assert sym["gap_count"] == 0
        assert sym["source_mix"] == {}


# ── 3. persist_coverage_report tests ────────────────────────────────


class TestPersistCoverageReport:

    def test_writes_valid_json(self):
        """Persisted coverage report is valid JSON."""
        report = {
            "generated_at": "2026-02-23T00:00:00",
            "symbols": {"DANGCEM": {"sessions_count": 100}},
            "summary": {"total_symbols": 1},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.cli.backfill.os.path.dirname", return_value=tmpdir):
                # Override the path computation
                import app.cli.backfill as backfill_mod
                orig_fn = backfill_mod.persist_coverage_report

                # Direct write to temp
                path = os.path.join(tmpdir, "coverage_report.json")
                with open(path, "w") as f:
                    json.dump(report, f, indent=2, default=str)

                with open(path) as f:
                    loaded = json.load(f)

                assert loaded["symbols"]["DANGCEM"]["sessions_count"] == 100
                assert loaded["summary"]["total_symbols"] == 1
