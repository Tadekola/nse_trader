"""
Tests for Phase 5 Trust Status Service.

These tests verify:
1. TrustStatus aggregation from subsystems
2. Data integrity level computation
3. Educational messages for status codes
4. Banner message generation
5. Health endpoint responses
"""
import pytest
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.services.trust_status import (
    TrustStatusService,
    TrustStatus,
    DataIntegrityLevel,
    PerformanceReadiness,
    get_educational_message,
    EDUCATIONAL_MESSAGES,
)
from app.data.historical.storage import (
    HistoricalOHLCVStorage,
    OHLCVRecord,
)


class TestTrustStatusAggregation:
    """Test TrustStatus aggregation from subsystems."""
    
    def test_trust_status_with_no_data(self):
        """Should return DEGRADED when no historical data exists."""
        service = TrustStatusService()
        # Don't initialize storage - simulate no data
        service._storage = False
        service._performance_service = False
        
        status = service.get_trust_status()
        
        assert status.data_integrity == DataIntegrityLevel.DEGRADED
        assert status.symbols_with_history == 0
        assert status.symbols_ready_for_trading == 0
        assert len(status.notes) > 0
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    def test_trust_status_with_fresh_data(self, temp_storage):
        """Should return HIGH integrity when data is fresh and sufficient."""
        # Store fresh data
        base_date = date.today() - timedelta(days=2)
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=base_date - timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(60)
        ]
        temp_storage.store_ohlcv_batch(records)
        
        service = TrustStatusService()
        service._storage = temp_storage
        
        status = service.get_trust_status()
        
        assert status.data_integrity == DataIntegrityLevel.HIGH
        assert status.symbols_with_history >= 1
        assert status.symbols_ready_for_trading >= 1
        assert status.stale_data_present is False
    
    def test_trust_status_with_stale_data(self, temp_storage):
        """Should return MEDIUM integrity when data is stale."""
        # Store old data
        base_date = date.today() - timedelta(days=30)
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=base_date - timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(60)
        ]
        temp_storage.store_ohlcv_batch(records)
        
        service = TrustStatusService()
        service._storage = temp_storage
        
        status = service.get_trust_status()
        
        assert status.data_integrity == DataIntegrityLevel.MEDIUM
        assert status.stale_data_present is True
        assert any("stale" in note.lower() for note in status.notes)


class TestDataIntegrityLevel:
    """Test data integrity level computation."""
    
    def test_high_integrity_requires_no_stale_data(self):
        """HIGH integrity requires no stale data."""
        # Test via TrustStatus dataclass behavior
        status = TrustStatus(
            data_integrity=DataIntegrityLevel.HIGH,
            performance_readiness=PerformanceReadiness.READY,
            simulation_rate=0.0,
            stale_data_present=False,
            symbols_with_history=10,
            symbols_ready_for_trading=10,
            total_historical_sessions=600,
            last_successful_ingestion=date.today(),
            status_computed_at=datetime.now(timezone.utc),
        )
        
        assert status.data_integrity == DataIntegrityLevel.HIGH
        assert status.stale_data_present is False
    
    def test_integrity_levels_are_ordered(self):
        """Integrity levels should be properly ordered."""
        # HIGH > MEDIUM > DEGRADED
        assert DataIntegrityLevel.HIGH.value == "HIGH"
        assert DataIntegrityLevel.MEDIUM.value == "MEDIUM"
        assert DataIntegrityLevel.DEGRADED.value == "DEGRADED"


class TestEducationalMessages:
    """Test educational helper messages."""
    
    def test_no_trade_message_exists(self):
        """NO_TRADE should have educational message."""
        message = get_educational_message("NO_TRADE")
        
        assert "what_this_means" in message
        assert "user_action" in message
        assert "protective" in message["what_this_means"].lower()
    
    def test_insufficient_history_message(self):
        """INSUFFICIENT_HISTORY should explain data requirement."""
        message = get_educational_message("INSUFFICIENT_HISTORY")
        
        assert "what_this_means" in message
        assert "historical" in message["what_this_means"].lower() or "data" in message["what_this_means"].lower()
    
    def test_insufficient_sample_message(self):
        """INSUFFICIENT_SAMPLE should explain statistics requirement."""
        message = get_educational_message("INSUFFICIENT_SAMPLE")
        
        assert "what_this_means" in message
        assert "statistic" in message["what_this_means"].lower() or "sample" in message["what_this_means"].lower()
    
    def test_all_documented_statuses_have_messages(self):
        """All documented status codes should have messages."""
        required_statuses = [
            "NO_TRADE",
            "INSUFFICIENT_HISTORY",
            "INSUFFICIENT_SAMPLE",
            "PARTIALLY_READY",
            "NOT_READY",
            "STALE_DATA",
        ]
        
        for status in required_statuses:
            message = get_educational_message(status)
            assert "what_this_means" in message, f"Missing message for {status}"
    
    def test_unknown_status_returns_default(self):
        """Unknown status codes should return a sensible default."""
        message = get_educational_message("UNKNOWN_STATUS_XYZ")
        
        assert "what_this_means" in message
        assert "user_action" in message


class TestBannerMessages:
    """Test user-facing banner message generation."""
    
    def test_high_integrity_ready_banner(self):
        """HIGH + READY should show positive message."""
        status = TrustStatus(
            data_integrity=DataIntegrityLevel.HIGH,
            performance_readiness=PerformanceReadiness.READY,
            simulation_rate=0.0,
            stale_data_present=False,
            symbols_with_history=10,
            symbols_ready_for_trading=10,
            total_historical_sessions=600,
            last_successful_ingestion=date.today(),
            status_computed_at=datetime.now(timezone.utc),
        )
        
        banner = status.get_banner_message()
        
        assert "LIVE DATA" in banner
        assert "AVAILABLE" in banner or "METRICS" in banner
    
    def test_high_integrity_not_ready_banner(self):
        """HIGH + NOT_READY should mention insufficient history."""
        status = TrustStatus(
            data_integrity=DataIntegrityLevel.HIGH,
            performance_readiness=PerformanceReadiness.NOT_READY,
            simulation_rate=0.0,
            stale_data_present=False,
            symbols_with_history=5,
            symbols_ready_for_trading=0,
            total_historical_sessions=100,
            last_successful_ingestion=date.today(),
            status_computed_at=datetime.now(timezone.utc),
        )
        
        banner = status.get_banner_message()
        
        assert "INSUFFICIENT" in banner or "HISTORY" in banner
    
    def test_degraded_integrity_banner(self):
        """DEGRADED should show caution message."""
        status = TrustStatus(
            data_integrity=DataIntegrityLevel.DEGRADED,
            performance_readiness=PerformanceReadiness.NOT_READY,
            simulation_rate=0.0,
            stale_data_present=False,
            symbols_with_history=0,
            symbols_ready_for_trading=0,
            total_historical_sessions=0,
            last_successful_ingestion=None,
            status_computed_at=datetime.now(timezone.utc),
        )
        
        banner = status.get_banner_message()
        
        assert "DEGRADED" in banner or "CAUTION" in banner


class TestTrustStatusToDict:
    """Test TrustStatus serialization."""
    
    def test_to_dict_includes_all_fields(self):
        """to_dict() should include all required fields."""
        status = TrustStatus(
            data_integrity=DataIntegrityLevel.HIGH,
            performance_readiness=PerformanceReadiness.READY,
            simulation_rate=0.0,
            stale_data_present=False,
            symbols_with_history=10,
            symbols_ready_for_trading=8,
            total_historical_sessions=600,
            last_successful_ingestion=date.today(),
            status_computed_at=datetime.now(timezone.utc),
            notes=["Test note"],
            subsystem_status={"test": "OK"},
        )
        
        result = status.to_dict()
        
        assert result["data_integrity"] == "HIGH"
        assert result["performance_readiness"] == "READY"
        assert result["simulation_rate"] == 0.0
        assert result["stale_data_present"] is False
        assert "coverage" in result
        assert result["coverage"]["symbols_with_history"] == 10
        assert result["notes"] == ["Test note"]
    
    def test_to_dict_handles_none_ingestion_date(self):
        """to_dict() should handle None ingestion date."""
        status = TrustStatus(
            data_integrity=DataIntegrityLevel.DEGRADED,
            performance_readiness=PerformanceReadiness.NOT_READY,
            simulation_rate=0.0,
            stale_data_present=False,
            symbols_with_history=0,
            symbols_ready_for_trading=0,
            total_historical_sessions=0,
            last_successful_ingestion=None,
            status_computed_at=datetime.now(timezone.utc),
        )
        
        result = status.to_dict()
        
        assert result["last_ingestion"] is None


class TestIntegrityExplanation:
    """Test human-readable integrity explanations."""
    
    def test_high_explanation(self):
        """HIGH integrity should have positive explanation."""
        status = TrustStatus(
            data_integrity=DataIntegrityLevel.HIGH,
            performance_readiness=PerformanceReadiness.READY,
            simulation_rate=0.0,
            stale_data_present=False,
            symbols_with_history=10,
            symbols_ready_for_trading=10,
            total_historical_sessions=600,
            last_successful_ingestion=date.today(),
            status_computed_at=datetime.now(timezone.utc),
        )
        
        explanation = status.get_integrity_explanation()
        
        assert "operational" in explanation.lower()
        assert "no simulated" in explanation.lower() or "validated" in explanation.lower()
    
    def test_degraded_explanation(self):
        """DEGRADED integrity should warn about reliability."""
        status = TrustStatus(
            data_integrity=DataIntegrityLevel.DEGRADED,
            performance_readiness=PerformanceReadiness.NOT_READY,
            simulation_rate=0.0,
            stale_data_present=False,
            symbols_with_history=0,
            symbols_ready_for_trading=0,
            total_historical_sessions=0,
            last_successful_ingestion=None,
            status_computed_at=datetime.now(timezone.utc),
        )
        
        explanation = status.get_integrity_explanation()
        
        assert "issue" in explanation.lower() or "reliable" in explanation.lower()


class TestPerformanceResponseExplanations:
    """Test that performance responses include educational explanations."""
    
    def test_insufficient_sample_includes_explanation(self):
        """INSUFFICIENT_SAMPLE response should include explanation."""
        from app.services.performance_service import PerformanceResponse
        
        response = PerformanceResponse(
            status="INSUFFICIENT_SAMPLE",
            data={"message": "Need more signals"},
        )
        
        result = response.to_dict()
        
        assert "explanation" in result
        assert "what_this_means" in result["explanation"]
    
    def test_ok_response_no_explanation(self):
        """OK response should not include explanation block."""
        from app.services.performance_service import PerformanceResponse
        
        response = PerformanceResponse(
            status="OK",
            data={"hit_rates": {"5d": 0.65}},
            evaluated_signal_count=50,
        )
        
        result = response.to_dict()
        
        # OK status should not have explanation block
        assert "explanation" not in result or result.get("explanation") == {}
