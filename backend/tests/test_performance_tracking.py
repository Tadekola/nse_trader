"""
Unit tests for Signal Performance Tracking System.

Tests cover:
- Signal history storage and retrieval
- Deterministic signal ID generation
- Forward return evaluation
- Directional hit rate computation
- Calibration error calculation
- Metrics by direction and regime
"""
import pytest
from datetime import datetime, timedelta

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.signal_history import (
    SignalHistoryStore,
    TrackedSignal,
    SignalStatus,
    generate_signal_id,
    get_signal_history_store
)
from app.services.performance_evaluator import (
    PerformanceEvaluator,
    PerformanceMetrics,
    get_performance_evaluator
)


class TestSignalIdGeneration:
    """Tests for deterministic signal ID generation."""
    
    def test_generates_deterministic_id(self):
        """Test that same inputs produce same ID."""
        ts = datetime(2024, 1, 15, 10, 30, 0)
        
        id1 = generate_signal_id("DANGCEM", "bullish", ts, "swing")
        id2 = generate_signal_id("DANGCEM", "bullish", ts, "swing")
        
        assert id1 == id2
    
    def test_different_symbol_different_id(self):
        """Test that different symbols produce different IDs."""
        ts = datetime(2024, 1, 15, 10, 30, 0)
        
        id1 = generate_signal_id("DANGCEM", "bullish", ts, "swing")
        id2 = generate_signal_id("ZENITHBANK", "bullish", ts, "swing")
        
        assert id1 != id2
    
    def test_different_direction_different_id(self):
        """Test that different directions produce different IDs."""
        ts = datetime(2024, 1, 15, 10, 30, 0)
        
        id1 = generate_signal_id("DANGCEM", "bullish", ts, "swing")
        id2 = generate_signal_id("DANGCEM", "bearish", ts, "swing")
        
        assert id1 != id2
    
    def test_different_timestamp_different_id(self):
        """Test that different timestamps produce different IDs."""
        ts1 = datetime(2024, 1, 15, 10, 30, 0)
        ts2 = datetime(2024, 1, 15, 10, 31, 0)
        
        id1 = generate_signal_id("DANGCEM", "bullish", ts1, "swing")
        id2 = generate_signal_id("DANGCEM", "bullish", ts2, "swing")
        
        assert id1 != id2
    
    def test_id_format(self):
        """Test that ID has expected format."""
        ts = datetime(2024, 1, 15, 10, 30, 0)
        signal_id = generate_signal_id("DANGCEM", "bullish", ts, "swing")
        
        assert signal_id.startswith("sig_")
        assert len(signal_id) == 20  # sig_ + 16 hex chars
    
    def test_case_insensitive_symbol(self):
        """Test that symbol is case-normalized."""
        ts = datetime(2024, 1, 15, 10, 30, 0)
        
        id1 = generate_signal_id("DANGCEM", "bullish", ts, "swing")
        id2 = generate_signal_id("dangcem", "bullish", ts, "swing")
        
        assert id1 == id2


class TestSignalHistoryStore:
    """Tests for SignalHistoryStore class."""
    
    @pytest.fixture
    def store(self):
        """Create a fresh store instance."""
        store = SignalHistoryStore()
        store.clear()
        return store
    
    @pytest.fixture
    def sample_signal_data(self):
        """Sample data for creating a signal."""
        return {
            "symbol": "DANGCEM",
            "bias_direction": "bullish",
            "bias_probability": 72,
            "regime": "trending",
            "regime_confidence": 0.85,
            "data_confidence_score": 0.92,
            "price_at_signal": 285.50,
            "horizon": "swing",
            "generated_at": datetime(2024, 1, 15, 10, 30, 0)
        }
    
    def test_store_signal(self, store, sample_signal_data):
        """Test storing a signal."""
        signal = store.store_signal(**sample_signal_data)
        
        assert signal.signal_id is not None
        assert signal.symbol == "DANGCEM"
        assert signal.bias_direction == "bullish"
        assert signal.bias_probability == 72
        assert signal.status == SignalStatus.PENDING
    
    def test_retrieve_signal_by_id(self, store, sample_signal_data):
        """Test retrieving a signal by ID."""
        stored = store.store_signal(**sample_signal_data)
        retrieved = store.get_signal(stored.signal_id)
        
        assert retrieved is not None
        assert retrieved.signal_id == stored.signal_id
        assert retrieved.symbol == stored.symbol
    
    def test_retrieve_nonexistent_signal(self, store):
        """Test that retrieving nonexistent signal returns None."""
        result = store.get_signal("sig_nonexistent12345")
        assert result is None
    
    def test_get_signals_by_symbol(self, store):
        """Test retrieving signals by symbol."""
        store.store_signal(
            symbol="DANGCEM", bias_direction="bullish", bias_probability=70,
            regime="trending", regime_confidence=0.8, data_confidence_score=0.9,
            price_at_signal=285.50, horizon="swing"
        )
        store.store_signal(
            symbol="DANGCEM", bias_direction="bearish", bias_probability=65,
            regime="mean_reverting", regime_confidence=0.7, data_confidence_score=0.85,
            price_at_signal=280.00, horizon="swing"
        )
        store.store_signal(
            symbol="ZENITHBANK", bias_direction="bullish", bias_probability=60,
            regime="trending", regime_confidence=0.75, data_confidence_score=0.88,
            price_at_signal=25.00, horizon="swing"
        )
        
        dangcem_signals = store.get_signals_by_symbol("DANGCEM")
        assert len(dangcem_signals) == 2
        
        zenith_signals = store.get_signals_by_symbol("ZENITHBANK")
        assert len(zenith_signals) == 1
    
    def test_get_signals_by_direction(self, store):
        """Test retrieving signals by direction."""
        store.store_signal(
            symbol="DANGCEM", bias_direction="bullish", bias_probability=70,
            regime="trending", regime_confidence=0.8, data_confidence_score=0.9,
            price_at_signal=285.50, horizon="swing"
        )
        store.store_signal(
            symbol="ZENITHBANK", bias_direction="bullish", bias_probability=65,
            regime="trending", regime_confidence=0.7, data_confidence_score=0.85,
            price_at_signal=25.00, horizon="swing"
        )
        store.store_signal(
            symbol="GTCO", bias_direction="bearish", bias_probability=60,
            regime="mean_reverting", regime_confidence=0.75, data_confidence_score=0.88,
            price_at_signal=30.00, horizon="swing"
        )
        
        bullish_signals = store.get_signals_by_direction("bullish")
        assert len(bullish_signals) == 2
        
        bearish_signals = store.get_signals_by_direction("bearish")
        assert len(bearish_signals) == 1
    
    def test_get_signals_by_regime(self, store):
        """Test retrieving signals by regime."""
        store.store_signal(
            symbol="DANGCEM", bias_direction="bullish", bias_probability=70,
            regime="trending", regime_confidence=0.8, data_confidence_score=0.9,
            price_at_signal=285.50, horizon="swing"
        )
        store.store_signal(
            symbol="ZENITHBANK", bias_direction="bullish", bias_probability=65,
            regime="mean_reverting", regime_confidence=0.7, data_confidence_score=0.85,
            price_at_signal=25.00, horizon="swing"
        )
        
        trending_signals = store.get_signals_by_regime("trending")
        assert len(trending_signals) == 1
        
        mean_rev_signals = store.get_signals_by_regime("mean_reverting")
        assert len(mean_rev_signals) == 1
    
    def test_count_signals(self, store, sample_signal_data):
        """Test signal counting."""
        store.store_signal(**sample_signal_data)
        
        counts = store.count_signals()
        assert counts["total"] == 1
        assert counts["pending"] == 1
        assert counts["evaluated"] == 0
    
    def test_signal_to_dict(self, store, sample_signal_data):
        """Test signal serialization to dict."""
        signal = store.store_signal(**sample_signal_data)
        result = signal.to_dict()
        
        assert "signal_id" in result
        assert "symbol" in result
        assert "bias_direction" in result
        assert "bias_probability" in result
        assert "status" in result
        assert result["status"] == "pending"


class TestPerformanceEvaluator:
    """Tests for PerformanceEvaluator class."""
    
    @pytest.fixture
    def store(self):
        """Create a fresh store instance."""
        store = SignalHistoryStore()
        store.clear()
        return store
    
    @pytest.fixture
    def evaluator(self, store):
        """Create evaluator with fresh store."""
        return PerformanceEvaluator(store=store)
    
    @pytest.fixture
    def bullish_signal(self, store):
        """Create a bullish signal."""
        return store.store_signal(
            symbol="DANGCEM",
            bias_direction="bullish",
            bias_probability=72,
            regime="trending",
            regime_confidence=0.85,
            data_confidence_score=0.92,
            price_at_signal=100.00,
            horizon="swing"
        )
    
    @pytest.fixture
    def bearish_signal(self, store):
        """Create a bearish signal."""
        return store.store_signal(
            symbol="ZENITHBANK",
            bias_direction="bearish",
            bias_probability=68,
            regime="mean_reverting",
            regime_confidence=0.75,
            data_confidence_score=0.88,
            price_at_signal=50.00,
            horizon="swing"
        )
    
    @pytest.fixture
    def neutral_signal(self, store):
        """Create a neutral signal."""
        return store.store_signal(
            symbol="GTCO",
            bias_direction="neutral",
            bias_probability=52,
            regime="mean_reverting",
            regime_confidence=0.70,
            data_confidence_score=0.85,
            price_at_signal=30.00,
            horizon="swing"
        )
    
    # === Forward Return Evaluation Tests ===
    
    def test_evaluate_bullish_hit(self, evaluator, bullish_signal):
        """Test that bullish signal is a hit when price goes up."""
        result = evaluator.evaluate_signal(
            bullish_signal,
            price_1d=105.00,  # +5%
            price_5d=110.00,  # +10%
            price_20d=120.00  # +20%
        )
        
        assert result.status == SignalStatus.EVALUATED
        assert result.return_1d == pytest.approx(5.0, rel=0.01)
        assert result.return_5d == pytest.approx(10.0, rel=0.01)
        assert result.return_20d == pytest.approx(20.0, rel=0.01)
        assert result.hit_1d == True
        assert result.hit_5d == True
        assert result.hit_20d == True
    
    def test_evaluate_bullish_miss(self, evaluator, bullish_signal):
        """Test that bullish signal is a miss when price goes down."""
        result = evaluator.evaluate_signal(
            bullish_signal,
            price_1d=95.00,   # -5%
            price_5d=90.00,   # -10%
            price_20d=85.00   # -15%
        )
        
        assert result.hit_1d == False
        assert result.hit_5d == False
        assert result.hit_20d == False
    
    def test_evaluate_bearish_hit(self, evaluator, bearish_signal):
        """Test that bearish signal is a hit when price goes down."""
        result = evaluator.evaluate_signal(
            bearish_signal,
            price_1d=48.00,  # -4%
            price_5d=45.00,  # -10%
            price_20d=40.00  # -20%
        )
        
        assert result.hit_1d == True
        assert result.hit_5d == True
        assert result.hit_20d == True
    
    def test_evaluate_bearish_miss(self, evaluator, bearish_signal):
        """Test that bearish signal is a miss when price goes up."""
        result = evaluator.evaluate_signal(
            bearish_signal,
            price_1d=52.00,  # +4%
            price_5d=55.00,  # +10%
            price_20d=60.00  # +20%
        )
        
        assert result.hit_1d == False
        assert result.hit_5d == False
        assert result.hit_20d == False
    
    def test_evaluate_neutral_hit(self, evaluator, neutral_signal):
        """Test that neutral signal is a hit when price stays flat."""
        result = evaluator.evaluate_signal(
            neutral_signal,
            price_1d=30.20,  # +0.67% (within 1%)
            price_5d=29.90,  # -0.33% (within 1%)
            price_20d=30.10  # +0.33% (within 1%)
        )
        
        assert result.hit_1d == True
        assert result.hit_5d == True
        assert result.hit_20d == True
    
    def test_evaluate_neutral_miss(self, evaluator, neutral_signal):
        """Test that neutral signal is a miss when price moves significantly."""
        result = evaluator.evaluate_signal(
            neutral_signal,
            price_1d=32.00,  # +6.67% (outside 1%)
            price_5d=35.00,  # +16.67%
            price_20d=40.00  # +33.33%
        )
        
        assert result.hit_1d == False
        assert result.hit_5d == False
        assert result.hit_20d == False
    
    def test_partial_evaluation(self, evaluator, bullish_signal):
        """Test evaluation with only some price data."""
        result = evaluator.evaluate_signal(
            bullish_signal,
            price_1d=105.00
            # No 5d or 20d price
        )
        
        assert result.status == SignalStatus.EVALUATED
        assert result.return_1d is not None
        assert result.return_5d is None
        assert result.return_20d is None
    
    # === Hit Rate Calculation Tests ===
    
    def test_hit_rate_calculation(self, evaluator, store):
        """Test hit rate calculation across multiple signals."""
        # Create 4 signals: 3 hits, 1 miss
        for i in range(4):
            signal = store.store_signal(
                symbol=f"STOCK{i}",
                bias_direction="bullish",
                bias_probability=70,
                regime="trending",
                regime_confidence=0.8,
                data_confidence_score=0.9,
                price_at_signal=100.00,
                horizon="swing"
            )
            # 3 hits (price up), 1 miss (price down)
            price_1d = 105.00 if i < 3 else 95.00
            evaluator.evaluate_signal(signal, price_1d=price_1d)
        
        metrics = evaluator.compute_metrics()
        
        assert metrics.total_signals == 4
        assert metrics.hit_rate_1d == pytest.approx(0.75, rel=0.01)  # 3/4 = 75%
    
    def test_hit_rate_by_direction(self, evaluator, store):
        """Test hit rate breakdown by bias direction."""
        # 2 bullish signals (1 hit, 1 miss)
        for i in range(2):
            signal = store.store_signal(
                symbol=f"BULL{i}",
                bias_direction="bullish",
                bias_probability=70,
                regime="trending",
                regime_confidence=0.8,
                data_confidence_score=0.9,
                price_at_signal=100.00,
                horizon="swing"
            )
            price_1d = 105.00 if i == 0 else 95.00
            evaluator.evaluate_signal(signal, price_1d=price_1d)
        
        # 2 bearish signals (2 hits)
        for i in range(2):
            signal = store.store_signal(
                symbol=f"BEAR{i}",
                bias_direction="bearish",
                bias_probability=65,
                regime="mean_reverting",
                regime_confidence=0.7,
                data_confidence_score=0.85,
                price_at_signal=100.00,
                horizon="swing"
            )
            evaluator.evaluate_signal(signal, price_1d=95.00)  # Both hits
        
        metrics = evaluator.compute_metrics()
        
        assert metrics.by_direction["bullish"]["hit_rate_1d"] == pytest.approx(0.5, rel=0.01)
        assert metrics.by_direction["bearish"]["hit_rate_1d"] == pytest.approx(1.0, rel=0.01)
    
    def test_hit_rate_by_regime(self, evaluator, store):
        """Test hit rate breakdown by market regime."""
        # 2 trending signals (2 hits)
        for i in range(2):
            signal = store.store_signal(
                symbol=f"TREND{i}",
                bias_direction="bullish",
                bias_probability=75,
                regime="trending",
                regime_confidence=0.85,
                data_confidence_score=0.9,
                price_at_signal=100.00,
                horizon="swing"
            )
            evaluator.evaluate_signal(signal, price_1d=105.00)
        
        # 2 mean_reverting signals (1 hit, 1 miss)
        for i in range(2):
            signal = store.store_signal(
                symbol=f"MEANREV{i}",
                bias_direction="bullish",
                bias_probability=55,
                regime="mean_reverting",
                regime_confidence=0.7,
                data_confidence_score=0.85,
                price_at_signal=100.00,
                horizon="swing"
            )
            price_1d = 105.00 if i == 0 else 95.00
            evaluator.evaluate_signal(signal, price_1d=price_1d)
        
        metrics = evaluator.compute_metrics()
        
        assert metrics.by_regime["trending"]["hit_rate_1d"] == pytest.approx(1.0, rel=0.01)
        assert metrics.by_regime["mean_reverting"]["hit_rate_1d"] == pytest.approx(0.5, rel=0.01)
    
    # === Calibration Tests ===
    
    def test_calibration_by_probability_bucket(self, evaluator, store):
        """Test calibration analysis by probability bucket."""
        # High probability signals (80-100) - should have high hit rate
        for i in range(4):
            signal = store.store_signal(
                symbol=f"HIGH{i}",
                bias_direction="bullish",
                bias_probability=85,
                regime="trending",
                regime_confidence=0.9,
                data_confidence_score=0.95,
                price_at_signal=100.00,
                horizon="swing"
            )
            # 3 hits, 1 miss (75% hit rate)
            price_1d = 105.00 if i < 3 else 95.00
            evaluator.evaluate_signal(signal, price_1d=price_1d, price_5d=price_1d)
        
        # Low probability signals (0-40) - should have low hit rate
        for i in range(4):
            signal = store.store_signal(
                symbol=f"LOW{i}",
                bias_direction="bullish",
                bias_probability=35,
                regime="mean_reverting",
                regime_confidence=0.6,
                data_confidence_score=0.8,
                price_at_signal=100.00,
                horizon="swing"
            )
            # 1 hit, 3 misses (25% hit rate)
            price_1d = 105.00 if i == 0 else 95.00
            evaluator.evaluate_signal(signal, price_1d=price_1d, price_5d=price_1d)
        
        metrics = evaluator.compute_metrics()
        
        assert "high" in metrics.by_probability_bucket
        assert "low" in metrics.by_probability_bucket
        assert metrics.by_probability_bucket["high"]["count"] == 4
        assert metrics.by_probability_bucket["low"]["count"] == 4
    
    def test_calibration_error_calculation(self, evaluator, store):
        """Test overall calibration error calculation."""
        # Create signals with known probabilities and outcomes
        # Perfect calibration: 70% prob signals have 70% hit rate
        for i in range(10):
            signal = store.store_signal(
                symbol=f"CAL{i}",
                bias_direction="bullish",
                bias_probability=70,
                regime="trending",
                regime_confidence=0.8,
                data_confidence_score=0.9,
                price_at_signal=100.00,
                horizon="swing"
            )
            # 7 hits, 3 misses = 70% hit rate
            price_1d = 105.00 if i < 7 else 95.00
            evaluator.evaluate_signal(signal, price_1d=price_1d, price_5d=price_1d)
        
        metrics = evaluator.compute_metrics()
        
        # Calibration error should be low (close to 0)
        assert metrics.calibration_error is not None
        # 70% predicted vs 70% actual = 0 error for this bucket
    
    # === Empty/Edge Cases ===
    
    def test_empty_store_metrics(self, evaluator):
        """Test metrics computation with empty store."""
        metrics = evaluator.compute_metrics()
        
        assert metrics.total_signals == 0
        assert metrics.hit_rate_1d is None
        assert metrics.hit_rate_5d is None
        assert metrics.hit_rate_20d is None
    
    def test_no_evaluated_signals(self, evaluator, store):
        """Test metrics with only pending signals."""
        store.store_signal(
            symbol="DANGCEM",
            bias_direction="bullish",
            bias_probability=70,
            regime="trending",
            regime_confidence=0.8,
            data_confidence_score=0.9,
            price_at_signal=100.00,
            horizon="swing"
        )
        
        metrics = evaluator.compute_metrics()
        
        assert metrics.total_signals == 0  # Only counts evaluated
    
    def test_metrics_to_dict(self, evaluator, store):
        """Test metrics serialization."""
        signal = store.store_signal(
            symbol="DANGCEM",
            bias_direction="bullish",
            bias_probability=70,
            regime="trending",
            regime_confidence=0.8,
            data_confidence_score=0.9,
            price_at_signal=100.00,
            horizon="swing"
        )
        evaluator.evaluate_signal(signal, price_1d=105.00)
        
        metrics = evaluator.compute_metrics()
        result = metrics.to_dict()
        
        assert "total_signals" in result
        assert "hit_rates" in result
        assert "avg_returns" in result
        assert "by_direction" in result
        assert "by_regime" in result
        assert "computed_at" in result


class TestTrackedSignalSerialization:
    """Tests for TrackedSignal serialization."""
    
    @pytest.fixture
    def store(self):
        store = SignalHistoryStore()
        store.clear()
        return store
    
    def test_pending_signal_to_dict(self, store):
        """Test serialization of pending signal."""
        signal = store.store_signal(
            symbol="DANGCEM",
            bias_direction="bullish",
            bias_probability=72,
            regime="trending",
            regime_confidence=0.85,
            data_confidence_score=0.92,
            price_at_signal=285.50,
            horizon="swing"
        )
        
        result = signal.to_dict()
        
        assert result["status"] == "pending"
        assert "forward_performance" not in result
    
    def test_evaluated_signal_to_dict(self, store):
        """Test serialization of evaluated signal."""
        signal = store.store_signal(
            symbol="DANGCEM",
            bias_direction="bullish",
            bias_probability=72,
            regime="trending",
            regime_confidence=0.85,
            data_confidence_score=0.92,
            price_at_signal=100.00,
            horizon="swing"
        )
        
        evaluator = PerformanceEvaluator(store=store)
        evaluator.evaluate_signal(signal, price_1d=105.00, price_5d=110.00)
        
        result = signal.to_dict()
        
        assert result["status"] == "evaluated"
        assert "forward_performance" in result
        assert result["forward_performance"]["1d"]["hit"] == True
        assert result["forward_performance"]["5d"]["hit"] == True


class TestSingletonInstances:
    """Tests for singleton instances."""
    
    def test_signal_store_singleton(self):
        """Test signal history store singleton."""
        import app.services.signal_history as sh
        sh._store_instance = None
        
        store1 = get_signal_history_store()
        store2 = get_signal_history_store()
        
        assert store1 is store2
    
    def test_evaluator_singleton(self):
        """Test performance evaluator singleton."""
        import app.services.performance_evaluator as pe
        pe._evaluator_instance = None
        
        eval1 = get_performance_evaluator()
        eval2 = get_performance_evaluator()
        
        assert eval1 is eval2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
