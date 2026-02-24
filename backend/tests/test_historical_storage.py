"""
Tests for Historical OHLCV Storage and Ingestion (Phase 3).

These tests verify:
1. Storage layer correctly persists and retrieves OHLCV data
2. Coverage service reflects actual stored sessions
3. Indicators are un-gated when sufficient history exists
4. No data fabrication - only stored data is used
"""
import pytest
import tempfile
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from app.data.historical.storage import (
    HistoricalOHLCVStorage,
    OHLCVRecord,
    SymbolMetadata,
)


class TestOHLCVRecord:
    """Test the OHLCVRecord dataclass."""
    
    def test_create_record(self):
        """Should create a valid OHLCV record."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=26.00,
            low=25.00,
            close=25.75,
            volume=1000000,
            source="NGNMARKET_HISTORICAL"
        )
        
        assert record.symbol == "GTCO"
        assert record.date == date(2024, 1, 15)
        assert record.open == 25.50
        assert record.high == 26.00
        assert record.low == 25.00
        assert record.close == 25.75
        assert record.volume == 1000000
    
    def test_record_to_dict(self):
        """Should convert to dictionary correctly."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=26.00,
            low=25.00,
            close=25.75,
            volume=1000000
        )
        
        result = record.to_dict()
        
        assert result["symbol"] == "GTCO"
        assert result["date"] == "2024-01-15"
        assert result["open"] == 25.50
        assert result["close"] == 25.75


class TestHistoricalOHLCVStorage:
    """Test the SQLite storage layer."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    def test_storage_initialization(self, temp_storage):
        """Storage should initialize database correctly."""
        assert temp_storage.db_path.exists()
        
        stats = temp_storage.get_stats()
        assert stats["total_symbols"] == 0
        assert stats["total_records"] == 0
    
    def test_store_single_record(self, temp_storage):
        """Should store a single OHLCV record."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=26.00,
            low=25.00,
            close=25.75,
            volume=1000000
        )
        
        success, error = temp_storage.store_ohlcv(record)
        
        assert success is True
        assert error is None
        assert temp_storage.get_sessions_available("GTCO") == 1
    
    def test_store_duplicate_record(self, temp_storage):
        """Should not store duplicate records (same symbol + date)."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=26.00,
            low=25.00,
            close=25.75,
            volume=1000000
        )
        
        # Store first time
        success1, _ = temp_storage.store_ohlcv(record)
        assert success1 is True
        
        # Store again - should be ignored
        success2, _ = temp_storage.store_ohlcv(record)
        assert success2 is False
        
        # Should still have only 1 session
        assert temp_storage.get_sessions_available("GTCO") == 1
    
    def test_store_batch_records(self, temp_storage):
        """Should store multiple records in batch."""
        base_date = date(2024, 1, 1)
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=base_date + timedelta(days=i),
                open=25.0 + i * 0.1,
                high=26.0 + i * 0.1,
                low=24.0 + i * 0.1,
                close=25.5 + i * 0.1,
                volume=1000000 + i * 10000
            )
            for i in range(60)  # 60 days
        ]
        
        stored, errors = temp_storage.store_ohlcv_batch(records)
        
        assert stored == 60
        assert len(errors) == 0
        assert temp_storage.get_sessions_available("GTCO") == 60
    
    def test_get_ohlcv(self, temp_storage):
        """Should retrieve OHLCV records."""
        # Store some records
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, i),
                open=25.0,
                high=26.0,
                low=24.0,
                close=25.5,
                volume=1000000
            )
            for i in range(1, 11)  # 10 days
        ]
        temp_storage.store_ohlcv_batch(records)
        
        # Retrieve all
        retrieved = temp_storage.get_ohlcv("GTCO")
        assert len(retrieved) == 10
        
        # Should be ordered by date ascending
        assert retrieved[0].date < retrieved[-1].date
    
    def test_get_ohlcv_with_date_filter(self, temp_storage):
        """Should filter OHLCV by date range."""
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, i),
                open=25.0,
                high=26.0,
                low=24.0,
                close=25.5,
                volume=1000000
            )
            for i in range(1, 31)  # 30 days
        ]
        temp_storage.store_ohlcv_batch(records)
        
        # Filter by date range
        retrieved = temp_storage.get_ohlcv(
            "GTCO",
            start_date=date(2024, 1, 10),
            end_date=date(2024, 1, 20)
        )
        
        assert len(retrieved) == 11  # Jan 10-20 inclusive
        assert retrieved[0].date == date(2024, 1, 10)
        assert retrieved[-1].date == date(2024, 1, 20)
    
    def test_get_latest_ohlcv(self, temp_storage):
        """Should retrieve most recent records."""
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, i),
                open=25.0,
                high=26.0,
                low=24.0,
                close=25.5,
                volume=1000000
            )
            for i in range(1, 31)
        ]
        temp_storage.store_ohlcv_batch(records)
        
        latest = temp_storage.get_latest_ohlcv("GTCO", sessions=5)
        
        assert len(latest) == 5
        # Should be ordered by date descending (most recent first)
        assert latest[0].date == date(2024, 1, 30)
    
    def test_get_metadata(self, temp_storage):
        """Should retrieve symbol metadata."""
        base_date = date(2024, 1, 1)
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=base_date + timedelta(days=i),
                open=25.0,
                high=26.0,
                low=24.0,
                close=25.5,
                volume=1000000
            )
            for i in range(50)  # 50 days
        ]
        temp_storage.store_ohlcv_batch(records)
        
        metadata = temp_storage.get_metadata("GTCO")
        
        assert metadata is not None
        assert metadata.symbol == "GTCO"
        assert metadata.total_sessions == 50
        assert metadata.first_date == date(2024, 1, 1)
        assert metadata.last_date == date(2024, 2, 19)  # Jan 1 + 49 days
    
    def test_get_symbols_with_sufficient_history(self, temp_storage):
        """Should return symbols with at least N sessions."""
        # GTCO: 60 sessions
        gtco_records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, 1) + timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(60)
        ]
        
        # ZENITH: 30 sessions
        zenith_records = [
            OHLCVRecord(
                symbol="ZENITHBANK",
                date=date(2024, 1, 1) + timedelta(days=i),
                open=30.0, high=31.0, low=29.0, close=30.5, volume=2000000
            )
            for i in range(30)
        ]
        
        temp_storage.store_ohlcv_batch(gtco_records)
        temp_storage.store_ohlcv_batch(zenith_records)
        
        # Only GTCO has >= 50 sessions
        sufficient = temp_storage.get_symbols_with_sufficient_history(50)
        assert "GTCO" in sufficient
        assert "ZENITHBANK" not in sufficient
    
    def test_symbol_case_insensitive(self, temp_storage):
        """Symbol lookups should be case-insensitive."""
        record = OHLCVRecord(
            symbol="gtco",  # lowercase
            date=date(2024, 1, 15),
            open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
        )
        temp_storage.store_ohlcv(record)
        
        # Should work with uppercase
        assert temp_storage.get_sessions_available("GTCO") == 1
        assert temp_storage.get_sessions_available("gtco") == 1
        assert temp_storage.get_sessions_available("GtCo") == 1
    
    def test_delete_symbol(self, temp_storage):
        """Should delete all data for a symbol."""
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(1, 11)
        ]
        temp_storage.store_ohlcv_batch(records)
        
        assert temp_storage.get_sessions_available("GTCO") == 10
        
        temp_storage.delete_symbol("GTCO")
        
        assert temp_storage.get_sessions_available("GTCO") == 0


class TestCoverageIntegration:
    """Test integration between storage and coverage service."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    def test_coverage_reflects_stored_sessions(self, temp_storage):
        """Coverage should reflect actual stored sessions."""
        from app.services.historical_coverage import HistoricalCoverageService
        
        # Store 60 sessions for GTCO
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, 1) + timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(60)
        ]
        temp_storage.store_ohlcv_batch(records)
        
        # Create coverage service with mocked storage
        service = HistoricalCoverageService()
        service._storage = temp_storage
        
        coverage = service.get_coverage("GTCO")
        
        assert coverage.sessions_available == 60
        assert coverage.is_sufficient is True
        assert coverage.source == "NGNMARKET_HISTORICAL"
    
    def test_coverage_zero_when_no_data(self, temp_storage):
        """Coverage should be zero when no data stored."""
        from app.services.historical_coverage import HistoricalCoverageService
        
        service = HistoricalCoverageService()
        service._storage = temp_storage
        
        coverage = service.get_coverage("UNKNOWN")
        
        assert coverage.sessions_available == 0
        assert coverage.is_sufficient is False
        assert coverage.source == "NO_HISTORICAL_DATA"
    
    def test_indicators_ungated_with_sufficient_history(self, temp_storage):
        """Indicators should be computable with sufficient history."""
        from app.services.historical_coverage import IndicatorType
        
        # Store 60 sessions
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, 1) + timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(60)
        ]
        temp_storage.store_ohlcv_batch(records)
        
        from app.services.historical_coverage import HistoricalCoverageService
        service = HistoricalCoverageService()
        service._storage = temp_storage
        
        coverage = service.get_coverage("GTCO")
        
        # With 60 sessions, these should be computable
        assert coverage.can_compute(IndicatorType.RSI_14) is True  # needs 15
        assert coverage.can_compute(IndicatorType.SMA_50) is True  # needs 50
        assert coverage.can_compute(IndicatorType.BOLLINGER_20) is True  # needs 20
        
        # SMA_200 still needs more history
        assert coverage.can_compute(IndicatorType.SMA_200) is False  # needs 200
    
    def test_recommendation_enabled_with_sufficient_history(self, temp_storage):
        """Recommendation should be enabled with sufficient history."""
        # Store 60 sessions
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, 1) + timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(60)
        ]
        temp_storage.store_ohlcv_batch(records)
        
        from app.services.historical_coverage import HistoricalCoverageService
        service = HistoricalCoverageService()
        service._storage = temp_storage
        
        can_generate, reason = service.can_generate_recommendation("GTCO")
        
        assert can_generate is True
        assert "Sufficient" in reason


class TestNoDataFabrication:
    """Test that no data is fabricated."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    def test_missing_dates_not_filled(self, temp_storage):
        """Missing dates should not be filled with synthetic data."""
        # Store records for Jan 1, 3, 5 (skipping 2 and 4)
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, 1),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            ),
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, 3),
                open=25.5, high=26.5, low=24.5, close=26.0, volume=1100000
            ),
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, 5),
                open=26.0, high=27.0, low=25.0, close=26.5, volume=1200000
            ),
        ]
        temp_storage.store_ohlcv_batch(records)
        
        # Should only have 3 sessions, not 5
        assert temp_storage.get_sessions_available("GTCO") == 3
        
        # Retrieved records should only be the stored ones
        retrieved = temp_storage.get_ohlcv("GTCO")
        assert len(retrieved) == 3
        
        dates = [r.date for r in retrieved]
        assert date(2024, 1, 2) not in dates
        assert date(2024, 1, 4) not in dates
    
    def test_symbol_without_data_returns_zero(self, temp_storage):
        """Symbol without any data should return zero sessions."""
        assert temp_storage.get_sessions_available("NONEXISTENT") == 0
        assert temp_storage.get_ohlcv("NONEXISTENT") == []
        assert temp_storage.get_metadata("NONEXISTENT") is None


class TestSymbolMetadata:
    """Test SymbolMetadata dataclass."""
    
    def test_metadata_to_dict(self):
        """Should convert metadata to dictionary."""
        metadata = SymbolMetadata(
            symbol="GTCO",
            first_date=date(2024, 1, 1),
            last_date=date(2024, 3, 31),
            total_sessions=60,
            last_ingested_at=datetime(2024, 4, 1, 12, 0, 0),
            source="NGNMARKET_HISTORICAL"
        )
        
        result = metadata.to_dict()
        
        assert result["symbol"] == "GTCO"
        assert result["first_date"] == "2024-01-01"
        assert result["last_date"] == "2024-03-31"
        assert result["total_sessions"] == 60
        assert result["source"] == "NGNMARKET_HISTORICAL"
