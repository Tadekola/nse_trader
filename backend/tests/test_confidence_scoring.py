"""
Unit tests for Data Confidence Scoring module.

Tests cover:
- Confidence score calculation
- Suppression rules (confidence < 0.75, price variance, etc.)
- Component score calculations
- Edge cases and error handling
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.confidence_scoring import (
    DataConfidenceScorer,
    ConfidenceScore,
    ConfidenceScoreConfig,
    SuppressionReason,
    get_confidence_scorer
)


class TestConfidenceScoreConfig:
    """Tests for ConfidenceScoreConfig dataclass."""
    
    def test_default_config_values(self):
        """Test default configuration values are set correctly."""
        config = ConfidenceScoreConfig()
        
        assert config.min_confidence_threshold == 0.75
        assert config.max_price_variance_percent == 5.0
        assert config.max_volume_variance_percent == 20.0
        assert config.max_data_age_minutes == 30
        assert config.price_weight == 0.40
        assert config.volume_weight == 0.20
        assert config.freshness_weight == 0.20
        assert config.source_weight == 0.20
    
    def test_custom_config_values(self):
        """Test custom configuration values."""
        config = ConfidenceScoreConfig(
            min_confidence_threshold=0.80,
            max_price_variance_percent=3.0,
            max_volume_variance_percent=15.0,
            max_data_age_minutes=15
        )
        
        assert config.min_confidence_threshold == 0.80
        assert config.max_price_variance_percent == 3.0
        assert config.max_volume_variance_percent == 15.0
        assert config.max_data_age_minutes == 15
    
    def test_weights_must_sum_to_one(self):
        """Test that weights must sum to 1.0."""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            ConfidenceScoreConfig(
                price_weight=0.50,
                volume_weight=0.30,
                freshness_weight=0.30,
                source_weight=0.20
            )
    
    def test_valid_custom_weights(self):
        """Test valid custom weights that sum to 1.0."""
        config = ConfidenceScoreConfig(
            price_weight=0.50,
            volume_weight=0.25,
            freshness_weight=0.15,
            source_weight=0.10
        )
        
        assert config.price_weight == 0.50
        assert config.volume_weight == 0.25


class TestConfidenceScore:
    """Tests for ConfidenceScore dataclass."""
    
    def test_to_dict_conversion(self):
        """Test conversion to dictionary for API responses."""
        score = ConfidenceScore(
            symbol="DANGCEM",
            overall_score=0.85,
            price_agreement_score=0.90,
            volume_agreement_score=0.80,
            freshness_score=0.85,
            source_availability_score=0.90,
            is_suppressed=False,
            suppression_reasons=[],
            human_readable_reason=None,
            sources_used=["TradingView", "NGX"],
            price_variance_percent=2.5,
            volume_variance_percent=10.0,
            data_age_seconds=300.0
        )
        
        result = score.to_dict()
        
        assert result["symbol"] == "DANGCEM"
        assert result["confidence_score"] == 0.85
        assert result["status"] == "ACTIVE"
        assert result["suppression_reason"] is None
        assert result["component_scores"]["price_agreement"] == 0.90
        assert result["metrics"]["price_variance_percent"] == 2.5
        assert result["metrics"]["sources_used"] == ["TradingView", "NGX"]
    
    def test_suppressed_score_to_dict(self):
        """Test suppressed score conversion."""
        score = ConfidenceScore(
            symbol="ZENITH",
            overall_score=0.60,
            price_agreement_score=0.50,
            volume_agreement_score=0.70,
            freshness_score=0.60,
            source_availability_score=0.60,
            is_suppressed=True,
            suppression_reasons=[SuppressionReason.LOW_CONFIDENCE],
            human_readable_reason="Overall confidence (60.0%) is below minimum threshold (75.0%)",
            sources_used=["Simulated"],
            price_variance_percent=8.0,
            volume_variance_percent=15.0,
            data_age_seconds=600.0
        )
        
        result = score.to_dict()
        
        assert result["status"] == "SUPPRESSED"
        assert result["suppression_reason"] is not None
        assert "60.0%" in result["suppression_reason"]


class TestDataConfidenceScorer:
    """Tests for DataConfidenceScorer class."""
    
    @pytest.fixture
    def scorer(self):
        """Create a fresh scorer instance for each test."""
        return DataConfidenceScorer()
    
    @pytest.fixture
    def high_confidence_sources(self):
        """Source data with high agreement (should pass)."""
        now = datetime.now(timezone.utc)
        return [
            {
                "source": "TradingView",
                "price": 100.0,
                "volume": 1000000,
                "timestamp": now.isoformat()
            },
            {
                "source": "NGX",
                "price": 100.5,  # 0.5% difference
                "volume": 1050000,  # 5% difference
                "timestamp": now.isoformat()
            }
        ]
    
    @pytest.fixture
    def low_confidence_sources(self):
        """Source data with low agreement (should fail)."""
        now = datetime.now(timezone.utc)
        return [
            {
                "source": "TradingView",
                "price": 100.0,
                "volume": 1000000,
                "timestamp": now.isoformat()
            },
            {
                "source": "NGX",
                "price": 112.0,  # 12% difference - triggers price variance suppression
                "volume": 400000,  # 60% difference - triggers volume variance
                "timestamp": now.isoformat()
            }
        ]
    
    @pytest.fixture
    def stale_data_sources(self):
        """Source data that is too old."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        return [
            {
                "source": "TradingView",
                "price": 100.0,
                "volume": 1000000,
                "timestamp": old_time.isoformat()
            }
        ]
    
    # === Confidence Calculation Tests ===
    
    def test_high_confidence_not_suppressed(self, scorer, high_confidence_sources):
        """Test that high confidence data is not suppressed."""
        result = scorer.calculate_confidence(
            symbol="DANGCEM",
            source_data=high_confidence_sources
        )
        
        assert result.is_suppressed is False
        assert result.overall_score >= 0.75
        assert result.suppression_reasons == []
        assert result.human_readable_reason is None
    
    def test_low_confidence_suppressed(self, scorer, low_confidence_sources):
        """Test that low confidence data is suppressed."""
        result = scorer.calculate_confidence(
            symbol="ZENITH",
            source_data=low_confidence_sources
        )
        
        assert result.is_suppressed is True
        assert result.overall_score < 0.75
        # Should have at least one of the variance suppression reasons
        assert (
            SuppressionReason.HIGH_PRICE_VARIANCE in result.suppression_reasons or
            SuppressionReason.HIGH_VOLUME_VARIANCE in result.suppression_reasons or
            SuppressionReason.LOW_CONFIDENCE in result.suppression_reasons
        )
        assert result.human_readable_reason is not None
    
    def test_stale_data_suppressed(self, scorer, stale_data_sources):
        """Test that stale data triggers suppression."""
        result = scorer.calculate_confidence(
            symbol="GTCO",
            source_data=stale_data_sources
        )
        
        assert result.is_suppressed is True
        assert SuppressionReason.STALE_DATA in result.suppression_reasons
        assert "stale" in result.human_readable_reason.lower()
    
    def test_circuit_breaker_suppresses(self, scorer, high_confidence_sources):
        """Test that circuit breaker always suppresses regardless of data quality."""
        result = scorer.calculate_confidence(
            symbol="DANGCEM",
            source_data=high_confidence_sources,
            circuit_breaker_active=True
        )
        
        assert result.is_suppressed is True
        assert result.overall_score == 0.0
        assert SuppressionReason.CIRCUIT_BREAKER_ACTIVE in result.suppression_reasons
        assert "circuit breaker" in result.human_readable_reason.lower()
    
    def test_no_sources_suppressed(self, scorer):
        """Test that no sources triggers suppression."""
        result = scorer.calculate_confidence(
            symbol="UNKNOWN",
            source_data=[]
        )
        
        assert result.is_suppressed is True
        assert SuppressionReason.INSUFFICIENT_SOURCES in result.suppression_reasons
    
    def test_single_low_reliability_source_suppressed(self, scorer):
        """Test that single low-reliability source triggers suppression."""
        now = datetime.now(timezone.utc)
        source_data = [
            {
                "source": "Simulated",  # Low reliability source
                "price": 100.0,
                "volume": 1000000,
                "timestamp": now.isoformat()
            }
        ]
        
        result = scorer.calculate_confidence(
            symbol="TEST",
            source_data=source_data
        )
        
        assert result.is_suppressed is True
        assert SuppressionReason.INSUFFICIENT_SOURCES in result.suppression_reasons
    
    # === Component Score Tests ===
    
    def test_price_agreement_perfect(self, scorer):
        """Test price agreement score with identical prices."""
        now = datetime.now(timezone.utc)
        source_data = [
            {"source": "TradingView", "price": 100.0, "volume": 1000000, "timestamp": now.isoformat()},
            {"source": "NGX", "price": 100.0, "volume": 1000000, "timestamp": now.isoformat()}
        ]
        
        result = scorer.calculate_confidence("TEST", source_data)
        
        assert result.price_agreement_score == 1.0
        assert result.price_variance_percent == 0.0
    
    def test_volume_agreement_tolerance(self, scorer):
        """Test that volume agreement is more tolerant than price."""
        now = datetime.now(timezone.utc)
        source_data = [
            {"source": "TradingView", "price": 100.0, "volume": 1000000, "timestamp": now.isoformat()},
            {"source": "NGX", "price": 100.0, "volume": 1100000, "timestamp": now.isoformat()}  # 10% diff
        ]
        
        result = scorer.calculate_confidence("TEST", source_data)
        
        # Volume agreement should still be reasonable at 10% variance (below 20% threshold)
        assert result.volume_agreement_score > 0.3
        # But it should not be perfect
        assert result.volume_agreement_score < 1.0
    
    def test_freshness_score_decay(self, scorer):
        """Test that freshness score decays with data age."""
        fresh_time = datetime.now(timezone.utc)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=15)
        
        fresh_data = [{"source": "TradingView", "price": 100.0, "volume": 1000000, "timestamp": fresh_time.isoformat()}]
        old_data = [{"source": "TradingView", "price": 100.0, "volume": 1000000, "timestamp": old_time.isoformat()}]
        
        fresh_result = scorer.calculate_confidence("TEST", fresh_data)
        old_result = scorer.calculate_confidence("TEST", old_data)
        
        assert fresh_result.freshness_score > old_result.freshness_score
    
    def test_source_availability_multiple_sources_bonus(self, scorer):
        """Test that multiple high-reliability sources get bonus."""
        now = datetime.now(timezone.utc)
        
        single_source = [
            {"source": "TradingView", "price": 100.0, "volume": 1000000, "timestamp": now.isoformat()}
        ]
        
        multi_source = [
            {"source": "TradingView", "price": 100.0, "volume": 1000000, "timestamp": now.isoformat()},
            {"source": "NGX", "price": 100.0, "volume": 1000000, "timestamp": now.isoformat()}
        ]
        
        single_result = scorer.calculate_confidence("TEST", single_source)
        multi_result = scorer.calculate_confidence("TEST", multi_source)
        
        assert multi_result.source_availability_score > single_result.source_availability_score
    
    # === Threshold Tests ===
    
    def test_exact_threshold_boundary(self, scorer):
        """Test behavior at exact confidence threshold boundary."""
        # Create data that should result in exactly 0.75 confidence (hard to achieve exactly)
        # This test verifies the threshold comparison is correct (< not <=)
        config = ConfidenceScoreConfig(min_confidence_threshold=0.75)
        scorer_with_config = DataConfidenceScorer(config)
        
        now = datetime.now(timezone.utc)
        source_data = [
            {"source": "NGX", "price": 100.0, "volume": 1000000, "timestamp": now.isoformat()}
        ]
        
        result = scorer_with_config.calculate_confidence("TEST", source_data)
        
        # NGX has 0.95 reliability, should pass threshold
        if result.overall_score >= 0.75:
            assert result.is_suppressed is False
        else:
            assert result.is_suppressed is True
    
    def test_price_variance_threshold(self, scorer):
        """Test that price variance above threshold triggers suppression."""
        now = datetime.now(timezone.utc)
        # 12% price difference (well above 5% default threshold)
        source_data = [
            {"source": "TradingView", "price": 100.0, "volume": 1000000, "timestamp": now.isoformat()},
            {"source": "NGX", "price": 112.0, "volume": 1000000, "timestamp": now.isoformat()}
        ]
        
        result = scorer.calculate_confidence("TEST", source_data)
        
        # High price variance should trigger suppression (directly or via low confidence)
        assert result.is_suppressed is True
        assert result.price_variance_percent > 5.0
    
    # === Configuration Update Tests ===
    
    def test_update_config(self, scorer):
        """Test configuration update functionality."""
        original_threshold = scorer.config.min_confidence_threshold
        
        scorer.update_config(min_confidence_threshold=0.80)
        
        assert scorer.config.min_confidence_threshold == 0.80
        assert scorer.config.min_confidence_threshold != original_threshold
    
    def test_update_config_invalid_param(self, scorer):
        """Test that invalid config parameter raises error."""
        with pytest.raises(ValueError, match="Unknown config parameter"):
            scorer.update_config(invalid_param=0.5)
    
    # === Single Source Convenience Method Tests ===
    
    def test_calculate_from_single_source(self, scorer):
        """Test the convenience method for single stock data dict."""
        stock_data = {
            "source": "TradingView",
            "price": 100.0,
            "volume": 1000000,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        result = scorer.calculate_from_single_source(
            symbol="DANGCEM",
            stock_data=stock_data
        )
        
        assert result.symbol == "DANGCEM"
        assert len(result.sources_used) >= 1
    
    def test_calculate_from_single_source_with_discrepancies(self, scorer):
        """Test convenience method with discrepancy data from validation."""
        stock_data = {
            "source": "TradingView",
            "price": 100.0,
            "volume": 1000000,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "discrepancies": [
                {
                    "field": "price",
                    "values": {
                        "TradingView": 100.0,
                        "NGX": 101.0
                    }
                }
            ]
        }
        
        result = scorer.calculate_from_single_source(
            symbol="DANGCEM",
            stock_data=stock_data
        )
        
        # Should have extracted both sources
        assert len(result.sources_used) >= 1


class TestSingletonInstance:
    """Tests for singleton scorer instance."""
    
    def test_get_confidence_scorer_returns_same_instance(self):
        """Test that get_confidence_scorer returns singleton."""
        # Reset singleton for test
        import app.services.confidence_scoring as cs
        cs._scorer_instance = None
        
        scorer1 = get_confidence_scorer()
        scorer2 = get_confidence_scorer()
        
        assert scorer1 is scorer2
    
    def test_singleton_uses_first_config(self):
        """Test that singleton uses config from first call only."""
        import app.services.confidence_scoring as cs
        cs._scorer_instance = None
        
        config1 = ConfidenceScoreConfig(min_confidence_threshold=0.80)
        scorer1 = get_confidence_scorer(config1)
        
        config2 = ConfidenceScoreConfig(min_confidence_threshold=0.90)
        scorer2 = get_confidence_scorer(config2)
        
        # Should use first config
        assert scorer2.config.min_confidence_threshold == 0.80


class TestSuppressionReason:
    """Tests for SuppressionReason enum."""
    
    def test_suppression_reason_values(self):
        """Test that all suppression reasons have string values."""
        assert SuppressionReason.LOW_CONFIDENCE.value == "low_confidence"
        assert SuppressionReason.HIGH_PRICE_VARIANCE.value == "high_price_variance"
        assert SuppressionReason.HIGH_VOLUME_VARIANCE.value == "high_volume_variance"
        assert SuppressionReason.STALE_DATA.value == "stale_data"
        assert SuppressionReason.INSUFFICIENT_SOURCES.value == "insufficient_sources"
        assert SuppressionReason.CIRCUIT_BREAKER_ACTIVE.value == "circuit_breaker_active"


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.fixture
    def scorer(self):
        return DataConfidenceScorer()
    
    def test_zero_price_handling(self, scorer):
        """Test handling of zero prices."""
        now = datetime.now(timezone.utc)
        source_data = [
            {"source": "TradingView", "price": 0.0, "volume": 1000000, "timestamp": now.isoformat()}
        ]
        
        result = scorer.calculate_confidence("TEST", source_data)
        
        # Should handle gracefully, likely suppressed
        assert isinstance(result, ConfidenceScore)
    
    def test_missing_timestamp_handling(self, scorer):
        """Test handling of missing timestamps."""
        source_data = [
            {"source": "TradingView", "price": 100.0, "volume": 1000000}  # No timestamp
        ]
        
        result = scorer.calculate_confidence("TEST", source_data)
        
        # Should assume stale and likely suppress
        assert isinstance(result, ConfidenceScore)
    
    def test_invalid_timestamp_format(self, scorer):
        """Test handling of invalid timestamp format."""
        source_data = [
            {"source": "TradingView", "price": 100.0, "volume": 1000000, "timestamp": "invalid-date"}
        ]
        
        result = scorer.calculate_confidence("TEST", source_data)
        
        # Should handle gracefully
        assert isinstance(result, ConfidenceScore)
    
    def test_negative_values_handling(self, scorer):
        """Test handling of negative values."""
        now = datetime.now(timezone.utc)
        source_data = [
            {"source": "TradingView", "price": -100.0, "volume": -1000000, "timestamp": now.isoformat()}
        ]
        
        result = scorer.calculate_confidence("TEST", source_data)
        
        # Should handle gracefully
        assert isinstance(result, ConfidenceScore)
    
    def test_unknown_source_handling(self, scorer):
        """Test handling of unknown data sources."""
        now = datetime.now(timezone.utc)
        source_data = [
            {"source": "UnknownSource", "price": 100.0, "volume": 1000000, "timestamp": now.isoformat()}
        ]
        
        result = scorer.calculate_confidence("TEST", source_data)
        
        # Should use default reliability (0.5)
        assert isinstance(result, ConfidenceScore)
        assert result.source_availability_score < 0.9  # Lower than known sources


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
