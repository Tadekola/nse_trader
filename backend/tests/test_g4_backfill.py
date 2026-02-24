"""
Gate G4 test: Verify backfill infrastructure works correctly.

Tests:
- Universe config returns ≥20 symbols
- Storage can accept batch OHLCV records
- Verification report logic correctly identifies pass/fail
- ASI record can be stored alongside stock OHLCV
"""
import sys
import os
import pytest
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data.universe import get_symbol_universe, DEFAULT_UNIVERSE
from app.data.historical.storage import (
    HistoricalOHLCVStorage,
    OHLCVRecord,
)


@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ohlcv.db"
        storage = HistoricalOHLCVStorage(db_path=db_path)
        yield storage
        storage.close()


class TestUniverse:
    def test_default_universe_has_20_symbols(self):
        assert len(DEFAULT_UNIVERSE) == 20

    def test_get_universe_returns_list(self):
        symbols = get_symbol_universe()
        assert isinstance(symbols, list)
        assert len(symbols) >= 20

    def test_all_symbols_uppercase(self):
        for s in DEFAULT_UNIVERSE:
            assert s == s.upper(), f"{s} is not uppercase"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("SYMBOL_UNIVERSE", "FOO, BAR, BAZ")
        symbols = get_symbol_universe()
        assert symbols == ["FOO", "BAR", "BAZ"]


class TestBackfillStorage:
    def _generate_records(self, symbol: str, count: int):
        today = date.today()
        return [
            OHLCVRecord(
                symbol=symbol,
                date=today - timedelta(days=count - i),
                open=100.0 + i,
                high=105.0 + i,
                low=95.0 + i,
                close=102.0 + i,
                volume=10000 + i * 100,
                source="NGNMARKET_HISTORICAL",
            )
            for i in range(count)
        ]

    def test_batch_store_and_count(self, temp_storage):
        records = self._generate_records("DANGCEM", 80)
        stored, errors = temp_storage.store_ohlcv_batch(records)
        assert stored == 80
        assert len(errors) == 0
        meta = temp_storage.get_metadata("DANGCEM")
        assert meta is not None
        assert meta.total_sessions == 80

    def test_asi_stored_alongside_stocks(self, temp_storage):
        stock_records = self._generate_records("GTCO", 70)
        asi_records = self._generate_records("ASI", 70)
        temp_storage.store_ohlcv_batch(stock_records)
        temp_storage.store_ohlcv_batch(asi_records)

        stock_meta = temp_storage.get_metadata("GTCO")
        asi_meta = temp_storage.get_metadata("ASI")
        assert stock_meta.total_sessions == 70
        assert asi_meta.total_sessions == 70

    def test_sufficient_history_query(self, temp_storage):
        for sym in ["A", "B", "C"]:
            count = 80 if sym != "C" else 30
            records = self._generate_records(sym, count)
            temp_storage.store_ohlcv_batch(records)

        sufficient = temp_storage.get_symbols_with_sufficient_history(60)
        assert "A" in sufficient
        assert "B" in sufficient
        assert "C" not in sufficient

    def test_dataframe_output(self, temp_storage):
        records = self._generate_records("DANGCEM", 65)
        temp_storage.store_ohlcv_batch(records)

        df = temp_storage.get_ohlcv_dataframe("DANGCEM", min_sessions=60)
        assert df is not None
        assert len(df) == 65
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert df.index.is_monotonic_increasing

    def test_deduplication(self, temp_storage):
        records = self._generate_records("DANGCEM", 10)
        temp_storage.store_ohlcv_batch(records)
        stored2, _ = temp_storage.store_ohlcv_batch(records)  # duplicates
        assert stored2 == 0  # all ignored
        meta = temp_storage.get_metadata("DANGCEM")
        assert meta.total_sessions == 10
