"""
Tests for Phase 3 Hardening: Ingestion Integrity, Staleness, and Validation.

These tests verify:
1. OHLCV validation rejects broken candles
2. Staleness detection behavior
3. Ingestion status transitions
4. Duplicate handling policy (ignore new duplicates)
"""
import pytest
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from app.data.historical.storage import (
    HistoricalOHLCVStorage,
    OHLCVRecord,
    SymbolMetadata,
    ValidationError,
    IngestionStatus,
    validate_ohlcv_record,
    DEFAULT_STALENESS_THRESHOLD_DAYS,
)


class TestOHLCVValidation:
    """Test OHLCV record validation."""
    
    def test_valid_record_passes(self):
        """Valid OHLCV record should pass validation."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=26.00,
            low=25.00,
            close=25.75,
            volume=1000000
        )
        
        error = validate_ohlcv_record(record)
        assert error is None
    
    def test_zero_open_rejected(self):
        """Open price of zero should be rejected."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=0.0,  # Invalid
            high=26.00,
            low=25.00,
            close=25.75,
            volume=1000000
        )
        
        error = validate_ohlcv_record(record)
        assert error is not None
        assert error.field == "open"
        assert "positive" in error.reason.lower()
    
    def test_negative_open_rejected(self):
        """Negative open price should be rejected."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=-5.0,  # Invalid
            high=26.00,
            low=25.00,
            close=25.75,
            volume=1000000
        )
        
        error = validate_ohlcv_record(record)
        assert error is not None
        assert error.field == "open"
    
    def test_zero_high_rejected(self):
        """High price of zero should be rejected."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=0.0,  # Invalid
            low=25.00,
            close=25.75,
            volume=1000000
        )
        
        error = validate_ohlcv_record(record)
        assert error is not None
        assert error.field == "high"
    
    def test_zero_low_rejected(self):
        """Low price of zero should be rejected."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=26.00,
            low=0.0,  # Invalid
            close=25.75,
            volume=1000000
        )
        
        error = validate_ohlcv_record(record)
        assert error is not None
        assert error.field == "low"
    
    def test_zero_close_rejected(self):
        """Close price of zero should be rejected."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=26.00,
            low=25.00,
            close=0.0,  # Invalid
            volume=1000000
        )
        
        error = validate_ohlcv_record(record)
        assert error is not None
        assert error.field == "close"
    
    def test_negative_volume_rejected(self):
        """Negative volume should be rejected."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=26.00,
            low=25.00,
            close=25.75,
            volume=-100  # Invalid
        )
        
        error = validate_ohlcv_record(record)
        assert error is not None
        assert error.field == "volume"
        assert "non-negative" in error.reason.lower()
    
    def test_zero_volume_accepted(self):
        """Zero volume should be accepted (no trades day)."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=26.00,
            low=25.00,
            close=25.75,
            volume=0  # Valid - no trades
        )
        
        error = validate_ohlcv_record(record)
        assert error is None
    
    def test_high_less_than_max_rejected(self):
        """High less than max(open, close, low) should be rejected."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=25.00,  # Invalid: less than open (25.50)
            low=24.00,
            close=25.75,
            volume=1000000
        )
        
        error = validate_ohlcv_record(record)
        assert error is not None
        assert error.field == "high"
        assert "max" in error.reason.lower()
    
    def test_low_greater_than_min_rejected(self):
        """Low greater than min(open, close, high) should be rejected."""
        record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=26.00,
            low=25.80,  # Invalid: greater than open (25.50)
            close=25.75,
            volume=1000000
        )
        
        error = validate_ohlcv_record(record)
        assert error is not None
        assert error.field == "low"
        assert "min" in error.reason.lower()
    
    def test_validation_error_to_dict(self):
        """ValidationError should convert to dict correctly."""
        error = ValidationError(
            symbol="GTCO",
            date=date(2024, 1, 15),
            field="high",
            reason="High must be >= max(open, close, low)",
            value=25.0
        )
        
        result = error.to_dict()
        
        assert result["symbol"] == "GTCO"
        assert result["date"] == "2024-01-15"
        assert result["field"] == "high"
        assert "High" in result["reason"]
        assert result["value"] == 25.0


class TestStorageValidation:
    """Test that storage layer validates records."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    def test_store_rejects_invalid_record(self, temp_storage):
        """Storage should reject invalid records."""
        invalid_record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=-5.0,  # Invalid
            high=26.00,
            low=25.00,
            close=25.75,
            volume=1000000
        )
        
        success, error = temp_storage.store_ohlcv(invalid_record)
        
        assert success is False
        assert error is not None
        assert error.field == "open"
    
    def test_store_accepts_valid_record(self, temp_storage):
        """Storage should accept valid records."""
        valid_record = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=26.00,
            low=25.00,
            close=25.75,
            volume=1000000
        )
        
        success, error = temp_storage.store_ohlcv(valid_record)
        
        assert success is True
        assert error is None
    
    def test_batch_store_rejects_invalid_records(self, temp_storage):
        """Batch store should reject invalid records and keep valid ones."""
        records = [
            # Valid
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, 15),
                open=25.50, high=26.00, low=25.00, close=25.75, volume=1000000
            ),
            # Invalid: negative open
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, 16),
                open=-5.0, high=26.00, low=25.00, close=25.75, volume=1000000
            ),
            # Invalid: high < close
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, 17),
                open=25.50, high=25.00, low=24.00, close=26.00, volume=1000000
            ),
            # Valid
            OHLCVRecord(
                symbol="GTCO",
                date=date(2024, 1, 18),
                open=26.00, high=27.00, low=25.50, close=26.50, volume=1200000
            ),
        ]
        
        stored, errors = temp_storage.store_ohlcv_batch(records)
        
        assert stored == 2  # Only 2 valid records
        assert len(errors) == 2  # 2 validation errors
        assert temp_storage.get_sessions_available("GTCO") == 2


class TestDuplicateHandling:
    """Test deterministic de-duplication policy."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    def test_duplicate_ignored(self, temp_storage):
        """Duplicate (symbol, date) should be ignored (keep existing)."""
        original = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),
            open=25.50,
            high=26.00,
            low=25.00,
            close=25.75,
            volume=1000000
        )
        
        duplicate = OHLCVRecord(
            symbol="GTCO",
            date=date(2024, 1, 15),  # Same date
            open=30.00,  # Different values
            high=31.00,
            low=29.00,
            close=30.50,
            volume=2000000
        )
        
        # Store original
        success1, _ = temp_storage.store_ohlcv(original)
        assert success1 is True
        
        # Try to store duplicate
        success2, _ = temp_storage.store_ohlcv(duplicate)
        assert success2 is False  # Duplicate ignored
        
        # Verify original values preserved
        records = temp_storage.get_ohlcv("GTCO")
        assert len(records) == 1
        assert records[0].open == 25.50  # Original value, not 30.00
        assert records[0].close == 25.75  # Original value, not 30.50
    
    def test_batch_duplicate_ignored(self, temp_storage):
        """Batch store should ignore duplicates."""
        base_date = date(2024, 1, 1)
        
        # First batch
        records1 = [
            OHLCVRecord(
                symbol="GTCO",
                date=base_date + timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(5)
        ]
        stored1, _ = temp_storage.store_ohlcv_batch(records1)
        assert stored1 == 5
        
        # Second batch with some duplicates
        records2 = [
            OHLCVRecord(
                symbol="GTCO",
                date=base_date + timedelta(days=i),  # Days 3-7 (3,4 are duplicates)
                open=30.0, high=31.0, low=29.0, close=30.5, volume=2000000
            )
            for i in range(3, 8)
        ]
        stored2, _ = temp_storage.store_ohlcv_batch(records2)
        assert stored2 == 3  # Only 3 new records (days 5, 6, 7)
        
        # Total should be 8
        assert temp_storage.get_sessions_available("GTCO") == 8


class TestIngestionStatus:
    """Test ingestion status transitions."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    def test_status_ok_on_successful_ingestion(self, temp_storage):
        """Status should be OK after successful ingestion."""
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date.today() - timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(3)
        ]
        
        temp_storage.store_ohlcv_batch(records)
        metadata = temp_storage.get_metadata("GTCO")
        
        assert metadata is not None
        assert metadata.ingestion_status == IngestionStatus.OK
        assert metadata.records_rejected_count == 0
    
    def test_status_partial_on_some_rejections(self, temp_storage):
        """Status should be PARTIAL when some records rejected."""
        records = [
            # Valid
            OHLCVRecord(
                symbol="GTCO",
                date=date.today() - timedelta(days=1),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            ),
            # Invalid
            OHLCVRecord(
                symbol="GTCO",
                date=date.today() - timedelta(days=2),
                open=-5.0, high=26.0, low=24.0, close=25.5, volume=1000000
            ),
        ]
        
        temp_storage.store_ohlcv_batch(records)
        metadata = temp_storage.get_metadata("GTCO")
        
        assert metadata is not None
        assert metadata.ingestion_status == IngestionStatus.PARTIAL
        assert metadata.records_rejected_count == 1
    
    def test_status_failed_on_all_rejections(self, temp_storage):
        """Status should be FAILED when all records rejected."""
        records = [
            # All invalid
            OHLCVRecord(
                symbol="NEWCO",
                date=date.today() - timedelta(days=1),
                open=-5.0, high=26.0, low=24.0, close=25.5, volume=1000000
            ),
            OHLCVRecord(
                symbol="NEWCO",
                date=date.today() - timedelta(days=2),
                open=-10.0, high=26.0, low=24.0, close=25.5, volume=1000000
            ),
        ]
        
        temp_storage.store_ohlcv_batch(records)
        metadata = temp_storage.get_metadata("NEWCO")
        
        assert metadata is not None
        assert metadata.ingestion_status == IngestionStatus.FAILED
        assert metadata.last_error is not None
        assert "failed validation" in metadata.last_error.lower()


class TestStalenessDetection:
    """Test staleness detection behavior."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    def test_fresh_data_not_stale(self, temp_storage):
        """Recent data should not be marked as stale."""
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date.today() - timedelta(days=1),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            ),
        ]
        
        temp_storage.store_ohlcv_batch(records)
        metadata = temp_storage.get_metadata("GTCO")
        
        assert metadata is not None
        assert metadata.is_stale() is False
        assert metadata.get_stale_reason() is None
    
    def test_old_data_is_stale(self, temp_storage):
        """Data older than threshold should be marked as stale."""
        old_date = date.today() - timedelta(days=DEFAULT_STALENESS_THRESHOLD_DAYS + 5)
        
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=old_date,
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            ),
        ]
        
        temp_storage.store_ohlcv_batch(records)
        metadata = temp_storage.get_metadata("GTCO")
        
        assert metadata is not None
        assert metadata.is_stale() is True
        assert metadata.get_stale_reason() is not None
        assert "days old" in metadata.get_stale_reason()
    
    def test_configurable_staleness_threshold(self, temp_storage):
        """Staleness threshold should be configurable."""
        # Data from 3 days ago
        three_days_ago = date.today() - timedelta(days=3)
        
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=three_days_ago,
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            ),
        ]
        
        temp_storage.store_ohlcv_batch(records)
        metadata = temp_storage.get_metadata("GTCO")
        
        # With default threshold (5 days), not stale
        assert metadata.is_stale(threshold_days=5) is False
        
        # With stricter threshold (2 days), is stale
        assert metadata.is_stale(threshold_days=2) is True


class TestCoverageIntegrationWithHardening:
    """Test coverage service integration with hardening features."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    def test_coverage_includes_staleness_info(self, temp_storage):
        """Coverage should include staleness information."""
        from app.services.historical_coverage import HistoricalCoverageService
        
        # Store old data
        old_date = date.today() - timedelta(days=10)
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=old_date - timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(60)
        ]
        temp_storage.store_ohlcv_batch(records)
        
        service = HistoricalCoverageService()
        service._storage = temp_storage
        
        coverage = service.get_coverage("GTCO")
        
        assert coverage.is_stale is True
        assert coverage.stale_reason is not None
        assert "days old" in coverage.stale_reason
    
    def test_coverage_includes_ingestion_status(self, temp_storage):
        """Coverage should include ingestion status."""
        from app.services.historical_coverage import HistoricalCoverageService
        
        # Store with some rejections
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date.today() - timedelta(days=i),
                open=25.0 if i % 2 == 0 else -5.0,  # Every other is invalid
                high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(10)
        ]
        temp_storage.store_ohlcv_batch(records)
        
        service = HistoricalCoverageService()
        service._storage = temp_storage
        
        coverage = service.get_coverage("GTCO")
        
        assert coverage.ingestion_status == "PARTIAL"
        assert coverage.records_rejected_count > 0
    
    def test_coverage_to_dict_includes_hardening_fields(self, temp_storage):
        """Coverage.to_dict() should include all hardening fields."""
        from app.services.historical_coverage import HistoricalCoverageService
        
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=date.today() - timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(5)
        ]
        temp_storage.store_ohlcv_batch(records)
        
        service = HistoricalCoverageService()
        service._storage = temp_storage
        
        coverage = service.get_coverage("GTCO")
        result = coverage.to_dict()
        
        # Phase 3 hardening fields
        assert "is_stale" in result
        assert "stale_reason" in result
        assert "ingestion_status" in result
        assert "last_error" in result
        assert "records_rejected_count" in result


class TestIngestionStatusEnum:
    """Test IngestionStatus enum."""
    
    def test_status_values(self):
        """All expected status values should exist."""
        assert IngestionStatus.OK.value == "OK"
        assert IngestionStatus.STALE.value == "STALE"
        assert IngestionStatus.FAILED.value == "FAILED"
        assert IngestionStatus.PARTIAL.value == "PARTIAL"
        assert IngestionStatus.NEVER.value == "NEVER"
    
    def test_status_is_string_enum(self):
        """IngestionStatus should be a string enum."""
        assert isinstance(IngestionStatus.OK, str)
        assert IngestionStatus.OK == "OK"
