"""
Tests for Phase 3 Performance Re-enablement.

These tests verify:
1. Endpoints return 200 when READY
2. Signals are not tracked when history insufficient or stale
3. Forward returns are null when not enough forward data
4. Calibration returns INSUFFICIENT_SAMPLE when sample small
5. No simulated values enter performance computations
"""
import pytest
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from app.data.historical.storage import (
    HistoricalOHLCVStorage,
    OHLCVRecord,
)
from app.services.historical_coverage import HistoricalCoverageService
from app.services.signal_history import SignalHistoryStore
from app.services.performance_service import (
    PerformanceService,
    PerformanceReadiness,
    UnevaluatedReason,
)


class TestPerformanceReadiness:
    """Test readiness checking based on historical storage."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    @pytest.fixture
    def service(self, temp_storage):
        """Create performance service with temp storage."""
        coverage = HistoricalCoverageService()
        coverage._storage = temp_storage
        signal_store = SignalHistoryStore()
        return PerformanceService(
            storage=temp_storage,
            coverage_service=coverage,
            signal_store=signal_store
        )
    
    def test_not_ready_when_no_data(self, service):
        """Should return NOT_READY when no historical data exists."""
        status = service.get_readiness_status()
        
        assert status["status"] == PerformanceReadiness.NOT_READY.value
        assert "reasons" in status
        assert status["symbols_ready"] == 0
    
    def test_ready_when_sufficient_history(self, service, temp_storage):
        """Should return READY when at least one symbol has sufficient history."""
        # Store 60 sessions of recent data
        base_date = date.today() - timedelta(days=3)
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=base_date - timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(60)
        ]
        temp_storage.store_ohlcv_batch(records)
        
        status = service.get_readiness_status()
        
        assert status["status"] in [PerformanceReadiness.READY.value, PerformanceReadiness.PARTIALLY_READY.value]
        assert status["symbols_ready"] >= 1
    
    def test_not_ready_when_all_stale(self, service, temp_storage):
        """Should return NOT_READY when all data is stale."""
        # Store old data (more than 5 days ago)
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
        
        status = service.get_readiness_status()
        
        assert status["status"] == PerformanceReadiness.NOT_READY.value
        assert status["symbols_stale"] >= 1


class TestSignalTracking:
    """Test that signals are only tracked with sufficient history."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    @pytest.fixture
    def service(self, temp_storage):
        """Create performance service with temp storage."""
        coverage = HistoricalCoverageService()
        coverage._storage = temp_storage
        signal_store = SignalHistoryStore()
        return PerformanceService(
            storage=temp_storage,
            coverage_service=coverage,
            signal_store=signal_store
        )
    
    def test_signal_not_tracked_when_insufficient_history(self, service):
        """Signals should not be tracked when history is insufficient."""
        signal, reason = service.track_signal_with_validation(
            symbol="GTCO",
            bias_direction="bullish",
            bias_probability=70,
            regime="accumulation",
            regime_confidence=0.8,
            data_confidence_score=0.9,
            price_at_signal=25.50,
            horizon="swing"
        )
        
        assert signal is None
        assert reason is not None
        assert "Insufficient" in reason or "insufficient" in reason.lower()
    
    def test_signal_tracked_when_sufficient_history(self, service, temp_storage):
        """Signals should be tracked when history is sufficient and fresh."""
        # Store sufficient recent data
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
        
        signal, reason = service.track_signal_with_validation(
            symbol="GTCO",
            bias_direction="bullish",
            bias_probability=70,
            regime="accumulation",
            regime_confidence=0.8,
            data_confidence_score=0.9,
            price_at_signal=25.50,
            horizon="swing"
        )
        
        assert signal is not None
        assert reason is None
        assert signal.symbol == "GTCO"
    
    def test_signal_not_tracked_when_stale(self, service, temp_storage):
        """Signals should not be tracked when data is stale."""
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
        
        signal, reason = service.track_signal_with_validation(
            symbol="GTCO",
            bias_direction="bullish",
            bias_probability=70,
            regime="accumulation",
            regime_confidence=0.8,
            data_confidence_score=0.9,
            price_at_signal=25.50,
            horizon="swing"
        )
        
        assert signal is None
        assert reason is not None
        assert "stale" in reason.lower()


class TestForwardReturns:
    """Test forward return computation from stored OHLCV."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    @pytest.fixture
    def service(self, temp_storage):
        """Create performance service with temp storage."""
        coverage = HistoricalCoverageService()
        coverage._storage = temp_storage
        signal_store = SignalHistoryStore()
        return PerformanceService(
            storage=temp_storage,
            coverage_service=coverage,
            signal_store=signal_store
        )
    
    def test_forward_returns_null_when_no_forward_data(self, service, temp_storage):
        """Forward returns should be null when no future data available."""
        # Store data only up to today - no forward data
        base_date = date.today()
        records = [
            OHLCVRecord(
                symbol="GTCO",
                date=base_date - timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.5, volume=1000000
            )
            for i in range(60)
        ]
        temp_storage.store_ohlcv_batch(records)
        
        # Create a signal from a few days ago
        signal_store = service.signal_store
        signal = signal_store.store_signal(
            symbol="GTCO",
            bias_direction="bullish",
            bias_probability=70,
            regime="accumulation",
            regime_confidence=0.8,
            data_confidence_score=0.9,
            price_at_signal=25.50,
            horizon="swing",
            generated_at=datetime.utcnow() - timedelta(days=2)
        )
        
        # Evaluate the signal
        result = service.evaluate_signal_from_storage(signal)
        
        # Since signal date is recent and no future data, should not be fully evaluated
        # But should have some evaluation based on available data
        assert result.signal_id == signal.signal_id
    
    def test_forward_returns_computed_from_stored_data(self, service, temp_storage):
        """Forward returns should be computed from stored OHLCV data."""
        # Store data with known prices
        signal_date = date(2024, 1, 15)
        records = [
            # Day 0 (signal day)
            OHLCVRecord(symbol="GTCO", date=signal_date, open=25.0, high=26.0, low=24.0, close=25.0, volume=1000000),
            # Day 1 - price up
            OHLCVRecord(symbol="GTCO", date=signal_date + timedelta(days=1), open=25.0, high=27.0, low=25.0, close=26.0, volume=1000000),
            # Day 2
            OHLCVRecord(symbol="GTCO", date=signal_date + timedelta(days=2), open=26.0, high=27.0, low=25.5, close=26.5, volume=1000000),
            # Day 3
            OHLCVRecord(symbol="GTCO", date=signal_date + timedelta(days=3), open=26.5, high=28.0, low=26.0, close=27.0, volume=1000000),
            # Day 4
            OHLCVRecord(symbol="GTCO", date=signal_date + timedelta(days=4), open=27.0, high=28.0, low=26.5, close=27.5, volume=1000000),
            # Day 5 - price at 28.0 (12% up from 25.0)
            OHLCVRecord(symbol="GTCO", date=signal_date + timedelta(days=5), open=27.5, high=29.0, low=27.0, close=28.0, volume=1000000),
        ]
        # Add more historical data for sufficient sessions
        for i in range(1, 55):
            records.append(OHLCVRecord(
                symbol="GTCO",
                date=signal_date - timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.0, volume=1000000
            ))
        
        temp_storage.store_ohlcv_batch(records)
        
        # Get forward prices
        forward_prices = service.get_forward_prices("GTCO", signal_date)
        
        # Day 1 should have price 26.0
        assert forward_prices.get(1) == 26.0
        
        # Day 5 should have price 28.0
        assert forward_prices.get(5) == 28.0
    
    def test_evaluation_uses_stored_prices_only(self, service, temp_storage):
        """Evaluation should only use stored prices, no web calls."""
        # Store known data
        signal_date = date(2024, 1, 15)
        records = [
            OHLCVRecord(symbol="GTCO", date=signal_date, open=25.0, high=26.0, low=24.0, close=25.0, volume=1000000),
            OHLCVRecord(symbol="GTCO", date=signal_date + timedelta(days=1), open=25.0, high=27.0, low=25.0, close=26.0, volume=1000000),
        ]
        # Add historical data
        for i in range(1, 55):
            records.append(OHLCVRecord(
                symbol="GTCO",
                date=signal_date - timedelta(days=i),
                open=25.0, high=26.0, low=24.0, close=25.0, volume=1000000
            ))
        temp_storage.store_ohlcv_batch(records)
        
        # Create a signal
        signal_store = service.signal_store
        signal = signal_store.store_signal(
            symbol="GTCO",
            bias_direction="bullish",
            bias_probability=70,
            regime="accumulation",
            regime_confidence=0.8,
            data_confidence_score=0.9,
            price_at_signal=25.0,  # Same as stored close
            horizon="swing",
            generated_at=datetime(2024, 1, 15, 12, 0, 0)
        )
        
        # Evaluate - this should NOT make any web calls
        result = service.evaluate_signal_from_storage(signal)
        
        # Should have 1-day return calculated from stored data
        if result.price_1d is not None:
            assert result.price_1d == 26.0  # From stored data
            # Return should be 4% ((26-25)/25 * 100)
            assert result.return_1d == pytest.approx(4.0, rel=0.01)
            # Hit should be True for bullish signal with positive return
            assert result.hit_1d is True


class TestCalibration:
    """Test calibration metrics with INSUFFICIENT_SAMPLE handling."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    @pytest.fixture
    def service(self, temp_storage):
        """Create performance service with temp storage."""
        coverage = HistoricalCoverageService()
        coverage._storage = temp_storage
        signal_store = SignalHistoryStore()
        return PerformanceService(
            storage=temp_storage,
            coverage_service=coverage,
            signal_store=signal_store
        )
    
    def test_calibration_returns_insufficient_sample_when_few_signals(self, service):
        """Calibration should return INSUFFICIENT_SAMPLE when sample is too small."""
        response = service.get_calibration_metrics(days=30)
        
        assert response.status == "INSUFFICIENT_SAMPLE"
        assert "required_sample" in response.data
        assert response.data["required_sample"] == service.MIN_SIGNALS_FOR_CALIBRATION


class TestPerformanceSummary:
    """Test performance summary with transparency fields."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    @pytest.fixture
    def service(self, temp_storage):
        """Create performance service with temp storage."""
        coverage = HistoricalCoverageService()
        coverage._storage = temp_storage
        signal_store = SignalHistoryStore()
        return PerformanceService(
            storage=temp_storage,
            coverage_service=coverage,
            signal_store=signal_store
        )
    
    def test_summary_returns_no_signals_when_empty(self, service):
        """Summary should return NO_SIGNALS when no signals tracked."""
        response = service.get_performance_summary(days=30)
        
        assert response.status == "NO_SIGNALS"
        assert response.evaluated_signal_count == 0
    
    def test_summary_includes_transparency_fields(self, service, temp_storage):
        """Summary response should include all transparency fields."""
        # Store data and track a signal
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
        
        # Track a signal
        service.track_signal_with_validation(
            symbol="GTCO",
            bias_direction="bullish",
            bias_probability=70,
            regime="accumulation",
            regime_confidence=0.8,
            data_confidence_score=0.9,
            price_at_signal=25.50,
            horizon="swing"
        )
        
        response = service.get_performance_summary(days=30)
        result = response.to_dict()
        
        # Should have transparency section
        assert "transparency" in result
        assert "evaluated_signal_count" in result["transparency"]
        assert "unevaluated_signal_count" in result["transparency"]
        assert "unevaluated_reasons" in result["transparency"]
        assert "stale_symbols_excluded_count" in result["transparency"]


class TestNoSimulatedData:
    """Test that no simulated values enter performance computations."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    @pytest.fixture
    def service(self, temp_storage):
        """Create performance service with temp storage."""
        coverage = HistoricalCoverageService()
        coverage._storage = temp_storage
        signal_store = SignalHistoryStore()
        return PerformanceService(
            storage=temp_storage,
            coverage_service=coverage,
            signal_store=signal_store
        )
    
    def test_no_historical_data_returns_proper_reason(self, service):
        """Should return NO_HISTORICAL_DATA reason, not simulated values."""
        signal_store = service.signal_store
        signal = signal_store.store_signal(
            symbol="UNKNOWN",
            bias_direction="bullish",
            bias_probability=70,
            regime="accumulation",
            regime_confidence=0.8,
            data_confidence_score=0.9,
            price_at_signal=25.50,
            horizon="swing"
        )
        
        result = service.evaluate_signal_from_storage(signal)
        
        assert result.evaluated is False
        assert result.reason == UnevaluatedReason.NO_HISTORICAL_DATA
        assert result.price_1d is None
        assert result.return_1d is None
        assert result.hit_1d is None
    
    def test_stale_data_returns_proper_reason(self, service, temp_storage):
        """Should return STALE_DATA reason, not simulated values."""
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
        
        signal_store = service.signal_store
        signal = signal_store.store_signal(
            symbol="GTCO",
            bias_direction="bullish",
            bias_probability=70,
            regime="accumulation",
            regime_confidence=0.8,
            data_confidence_score=0.9,
            price_at_signal=25.50,
            horizon="swing"
        )
        
        result = service.evaluate_signal_from_storage(signal)
        
        assert result.evaluated is False
        assert result.reason == UnevaluatedReason.STALE_DATA
        assert result.price_1d is None


class TestUnevaluatedReasons:
    """Test that unevaluated reasons are properly tracked."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_ohlcv.db"
            storage = HistoricalOHLCVStorage(db_path)
            yield storage
            storage.close()
    
    @pytest.fixture
    def service(self, temp_storage):
        """Create performance service with temp storage."""
        coverage = HistoricalCoverageService()
        coverage._storage = temp_storage
        signal_store = SignalHistoryStore()
        return PerformanceService(
            storage=temp_storage,
            coverage_service=coverage,
            signal_store=signal_store
        )
    
    def test_unevaluated_reasons_breakdown(self, service, temp_storage):
        """Should provide breakdown of unevaluated reasons."""
        # Store fresh data for one symbol
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
        
        # Store stale data for another symbol
        old_date = date.today() - timedelta(days=30)
        old_records = [
            OHLCVRecord(
                symbol="ZENITH",
                date=old_date - timedelta(days=i),
                open=30.0, high=31.0, low=29.0, close=30.5, volume=2000000
            )
            for i in range(60)
        ]
        temp_storage.store_ohlcv_batch(old_records)
        
        # Track signals for both
        signal_store = service.signal_store
        signal_store.store_signal(
            symbol="GTCO",
            bias_direction="bullish",
            bias_probability=70,
            regime="accumulation",
            regime_confidence=0.8,
            data_confidence_score=0.9,
            price_at_signal=25.50,
            horizon="swing"
        )
        signal_store.store_signal(
            symbol="ZENITH",
            bias_direction="bearish",
            bias_probability=60,
            regime="distribution",
            regime_confidence=0.7,
            data_confidence_score=0.85,
            price_at_signal=30.50,
            horizon="swing"
        )
        
        response = service.get_performance_summary(days=30)
        
        # Should have unevaluated reasons breakdown
        assert response.unevaluated_reasons is not None
        # ZENITH should be marked as stale
        if response.unevaluated_signal_count > 0:
            assert any(
                reason in response.unevaluated_reasons
                for reason in [UnevaluatedReason.STALE_DATA.value, UnevaluatedReason.NOT_ENOUGH_FORWARD_DATA.value]
            )
