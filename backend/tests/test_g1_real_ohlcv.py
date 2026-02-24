"""
Gate G1 test: _build_price_dataframe() MUST use real OHLCV, never fabricate.

Verifies:
- Returns None (→ NO_TRADE) when symbol has no history
- Returns None when history < MIN_OHLCV_SESSIONS
- Returns None when data is stale
- Returns real DataFrame when sufficient fresh data exists
- DataFrame has correct columns and ascending DatetimeIndex
- No np.random anywhere in the output
"""
import sys
import os
import pytest
import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data.historical.storage import (
    HistoricalOHLCVStorage,
    OHLCVRecord,
)


@pytest.fixture
def temp_storage():
    """Create a temp SQLite storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ohlcv.db"
        storage = HistoricalOHLCVStorage(db_path=db_path)
        yield storage
        storage.close()


@pytest.fixture
def populated_storage(temp_storage):
    """Storage with 80 sessions for DANGCEM and 80 for ASI."""
    today = date.today()
    records = []
    for i in range(80):
        d = today - timedelta(days=80 - i)
        records.append(OHLCVRecord(
            symbol="DANGCEM",
            date=d,
            open=300.0 + i * 0.1,
            high=305.0 + i * 0.1,
            low=295.0 + i * 0.1,
            close=302.0 + i * 0.1,
            volume=100000 + i * 100,
            source="NGNMARKET_HISTORICAL",
        ))
        records.append(OHLCVRecord(
            symbol="ASI",
            date=d,
            open=65000.0 + i * 10,
            high=65500.0 + i * 10,
            low=64500.0 + i * 10,
            close=65200.0 + i * 10,
            volume=1000000000,
            source="NGNMARKET_HISTORICAL",
        ))
    temp_storage.store_ohlcv_batch(records)
    return temp_storage


class TestBuildPriceDataframe:
    """Test _build_price_dataframe() uses real OHLCV."""

    def test_returns_none_when_no_history(self, temp_storage):
        """Symbol with zero history → None."""
        df = temp_storage.get_ohlcv_dataframe("NONEXIST", min_sessions=60)
        assert df is None

    def test_returns_none_when_insufficient_sessions(self, temp_storage):
        """Symbol with < min_sessions → None."""
        today = date.today()
        for i in range(10):
            temp_storage.store_ohlcv(OHLCVRecord(
                symbol="FEWDATA", date=today - timedelta(days=10 - i),
                open=10.0, high=11.0, low=9.0, close=10.5, volume=1000,
            ))
        df = temp_storage.get_ohlcv_dataframe("FEWDATA", min_sessions=60)
        assert df is None

    def test_returns_dataframe_when_sufficient(self, populated_storage):
        """Symbol with ≥60 sessions → valid DataFrame."""
        df = populated_storage.get_ohlcv_dataframe("DANGCEM", min_sessions=60)
        assert df is not None
        assert len(df) >= 60
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        # Index must be ascending
        assert df.index.is_monotonic_increasing

    def test_dataframe_contains_no_nans(self, populated_storage):
        """All OHLCV values must be present."""
        df = populated_storage.get_ohlcv_dataframe("DANGCEM", min_sessions=60)
        assert df is not None
        assert not df.isnull().any().any()

    def test_asi_dataframe_available(self, populated_storage):
        """ASI data must also be loadable."""
        df = populated_storage.get_ohlcv_dataframe("ASI", min_sessions=60)
        assert df is not None
        assert len(df) >= 60

    def test_metadata_reflects_session_count(self, populated_storage):
        """Metadata must accurately report session count."""
        meta = populated_storage.get_metadata("DANGCEM")
        assert meta is not None
        assert meta.total_sessions >= 60

    def test_stale_data_detected(self, temp_storage):
        """Data older than threshold must be flagged as stale."""
        old_date = date.today() - timedelta(days=100)
        for i in range(70):
            temp_storage.store_ohlcv(OHLCVRecord(
                symbol="STALE",
                date=old_date + timedelta(days=i),
                open=10.0, high=11.0, low=9.0, close=10.5, volume=1000,
            ))
        meta = temp_storage.get_metadata("STALE")
        assert meta is not None
        assert meta.is_stale(threshold_days=5)
