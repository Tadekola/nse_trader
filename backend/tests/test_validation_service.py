"""
Tests for Multi-Source Validation Service.

Tests cover:
1. Agreement case - sources match within threshold
2. Divergence case - sources differ significantly  
3. Secondary missing - no secondary data available
4. Secondary stale - secondary data too old
5. Confidence scoring
6. Batch validation
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from app.market_data.providers.base import PriceSnapshot, DataSource, FetchResult
from app.services.data_confidence import (
    DataConfidenceScorer,
    ValidationResult,
    ValidationStatus,
    ConfidenceLevel,
    ConfidenceConfig,
)
from app.services.validation_service import (
    ValidationService,
    ValidatedSnapshot,
    ValidationServiceResult,
)


class TestDataConfidenceScorer:
    """Test the DataConfidenceScorer class."""
    
    @pytest.fixture
    def scorer(self):
        """Create a scorer with default config."""
        return DataConfidenceScorer()
    
    @pytest.fixture
    def primary_snapshot(self):
        """Create a sample primary snapshot."""
        return PriceSnapshot(
            symbol="GTCO",
            price=50.00,
            open=49.50,
            high=50.50,
            low=49.00,
            close=50.00,
            change=0.50,
            change_percent=1.0,
            volume=1000000,
            value=50000000.0,
            timestamp=datetime.utcnow(),
            source=DataSource.NGX_OFFICIAL,
        )
    
    def test_agreement_case_high_confidence(self, scorer, primary_snapshot):
        """Sources agree within 1% - should be HIGH confidence."""
        secondary = PriceSnapshot(
            symbol="GTCO",
            price=50.25,  # 0.5% difference
            open=49.50,
            high=50.50,
            low=49.00,
            close=50.25,
            change=0.50,
            change_percent=1.0,
            volume=1000000,
            value=50000000.0,
            timestamp=datetime.utcnow(),
            source=DataSource.UNKNOWN,
        )
        
        result = scorer.validate(primary_snapshot, secondary)
        
        assert result.status == ValidationStatus.VALIDATED
        assert result.confidence_level == ConfidenceLevel.HIGH
        assert result.confidence_score >= 0.9
        assert result.price_difference_percent < 1.0
    
    def test_minor_divergence_medium_confidence(self, scorer, primary_snapshot):
        """Sources differ by 1-3% - should be MEDIUM confidence."""
        secondary = PriceSnapshot(
            symbol="GTCO",
            price=51.00,  # 2% difference
            open=49.50,
            high=50.50,
            low=49.00,
            close=51.00,
            change=0.50,
            change_percent=1.0,
            volume=1000000,
            value=50000000.0,
            timestamp=datetime.utcnow(),
            source=DataSource.UNKNOWN,
        )
        
        result = scorer.validate(primary_snapshot, secondary)
        
        assert result.status == ValidationStatus.VALIDATED
        assert result.confidence_level == ConfidenceLevel.MEDIUM
        assert 1.0 <= result.price_difference_percent <= 3.0
    
    def test_major_divergence_divergent_status(self, scorer, primary_snapshot):
        """Sources differ by 3-5% - should be DIVERGENT status."""
        secondary = PriceSnapshot(
            symbol="GTCO",
            price=52.00,  # 4% difference
            open=49.50,
            high=50.50,
            low=49.00,
            close=52.00,
            change=0.50,
            change_percent=1.0,
            volume=1000000,
            value=50000000.0,
            timestamp=datetime.utcnow(),
            source=DataSource.UNKNOWN,
        )
        
        result = scorer.validate(primary_snapshot, secondary)
        
        assert result.status == ValidationStatus.DIVERGENT
        assert result.confidence_level == ConfidenceLevel.MEDIUM
        assert 3.0 <= result.price_difference_percent <= 5.0
    
    def test_severe_divergence_low_confidence(self, scorer, primary_snapshot):
        """Sources differ by 5-10% - should be LOW confidence."""
        secondary = PriceSnapshot(
            symbol="GTCO",
            price=54.00,  # 8% difference
            open=49.50,
            high=50.50,
            low=49.00,
            close=54.00,
            change=0.50,
            change_percent=1.0,
            volume=1000000,
            value=50000000.0,
            timestamp=datetime.utcnow(),
            source=DataSource.UNKNOWN,
        )
        
        result = scorer.validate(primary_snapshot, secondary)
        
        assert result.status == ValidationStatus.DIVERGENT
        assert result.confidence_level == ConfidenceLevel.LOW
        assert result.price_difference_percent >= 5.0
    
    def test_extreme_divergence_suppressed(self, scorer, primary_snapshot):
        """Sources differ by >10% - should be SUPPRESSED."""
        secondary = PriceSnapshot(
            symbol="GTCO",
            price=60.00,  # 20% difference
            open=49.50,
            high=50.50,
            low=49.00,
            close=60.00,
            change=0.50,
            change_percent=1.0,
            volume=1000000,
            value=50000000.0,
            timestamp=datetime.utcnow(),
            source=DataSource.UNKNOWN,
        )
        
        result = scorer.validate(primary_snapshot, secondary)
        
        assert result.status == ValidationStatus.DIVERGENT
        assert result.confidence_level == ConfidenceLevel.SUPPRESSED
        assert result.confidence_score == 0.0
    
    def test_secondary_missing_primary_only(self, scorer, primary_snapshot):
        """No secondary data - should be PRIMARY_ONLY status."""
        result = scorer.validate(primary_snapshot, None)
        
        assert result.status == ValidationStatus.PRIMARY_ONLY
        assert result.confidence_level == ConfidenceLevel.MEDIUM
        assert result.secondary_price is None
        # Should have base single-source confidence
        assert 0.6 <= result.confidence_score <= 0.8
    
    def test_secondary_stale_ignored(self, scorer, primary_snapshot):
        """Stale secondary data - should be SECONDARY_STALE status."""
        stale_time = datetime.utcnow() - timedelta(hours=48)
        secondary = PriceSnapshot(
            symbol="GTCO",
            price=50.25,
            open=49.50,
            high=50.50,
            low=49.00,
            close=50.25,
            change=0.50,
            change_percent=1.0,
            volume=1000000,
            value=50000000.0,
            timestamp=stale_time,  # 48 hours old
            source=DataSource.UNKNOWN,
        )
        
        result = scorer.validate(primary_snapshot, secondary)
        
        assert result.status == ValidationStatus.SECONDARY_STALE
        assert result.confidence_level == ConfidenceLevel.MEDIUM
    
    def test_batch_validation(self, scorer):
        """Test batch validation of multiple symbols."""
        primary_snapshots = {
            "GTCO": PriceSnapshot(
                symbol="GTCO", price=50.0, open=49.5, high=50.5, low=49.0,
                close=50.0, change=0.5, change_percent=1.0, volume=1000000,
                value=50000000.0, timestamp=datetime.utcnow(), source=DataSource.NGX_OFFICIAL,
            ),
            "ZENITHBANK": PriceSnapshot(
                symbol="ZENITHBANK", price=30.0, open=29.5, high=30.5, low=29.0,
                close=30.0, change=0.5, change_percent=1.7, volume=500000,
                value=15000000.0, timestamp=datetime.utcnow(), source=DataSource.NGX_OFFICIAL,
            ),
        }
        
        secondary_snapshots = {
            "GTCO": PriceSnapshot(
                symbol="GTCO", price=50.25, open=49.5, high=50.5, low=49.0,
                close=50.25, change=0.5, change_percent=1.0, volume=1000000,
                value=50000000.0, timestamp=datetime.utcnow(), source=DataSource.UNKNOWN,
            ),
            # ZENITHBANK missing from secondary
        }
        
        results = scorer.validate_batch(primary_snapshots, secondary_snapshots)
        
        assert len(results) == 2
        assert results["GTCO"].status == ValidationStatus.VALIDATED
        assert results["ZENITHBANK"].status == ValidationStatus.PRIMARY_ONLY
    
    def test_aggregate_stats(self, scorer):
        """Test aggregate statistics calculation."""
        results = {
            "GTCO": ValidationResult(
                symbol="GTCO", primary_price=50.0, secondary_price=50.25,
                status=ValidationStatus.VALIDATED, confidence_level=ConfidenceLevel.HIGH,
                confidence_score=0.95,
            ),
            "ZENITHBANK": ValidationResult(
                symbol="ZENITHBANK", primary_price=30.0, secondary_price=None,
                status=ValidationStatus.PRIMARY_ONLY, confidence_level=ConfidenceLevel.MEDIUM,
                confidence_score=0.70,
            ),
            "DANGCEM": ValidationResult(
                symbol="DANGCEM", primary_price=500.0, secondary_price=525.0,
                status=ValidationStatus.DIVERGENT, confidence_level=ConfidenceLevel.LOW,
                confidence_score=0.50,
            ),
        }
        
        stats = scorer.get_aggregate_stats(results)
        
        assert stats["total"] == 3
        assert stats["validated"] == 1
        assert stats["divergent"] == 1
        assert stats["secondary_missing"] == 1
        assert stats["confidence_distribution"]["high"] == 1
        assert stats["confidence_distribution"]["medium"] == 1
        assert stats["confidence_distribution"]["low"] == 1


class TestValidatedSnapshot:
    """Test the ValidatedSnapshot class."""
    
    def test_is_validated_true(self):
        """Test is_validated property when validated."""
        snapshot = PriceSnapshot(
            symbol="GTCO", price=50.0, open=49.5, high=50.5, low=49.0,
            close=50.0, change=0.5, change_percent=1.0, volume=1000000,
            value=50000000.0, timestamp=datetime.utcnow(), source=DataSource.NGX_OFFICIAL,
        )
        validation = ValidationResult(
            symbol="GTCO", primary_price=50.0, secondary_price=50.25,
            status=ValidationStatus.VALIDATED, confidence_level=ConfidenceLevel.HIGH,
            confidence_score=0.95,
        )
        
        validated = ValidatedSnapshot(snapshot=snapshot, validation=validation)
        
        assert validated.is_validated is True
        assert validated.confidence_level == ConfidenceLevel.HIGH
        assert validated.confidence_score == 0.95
    
    def test_is_validated_false_no_validation(self):
        """Test is_validated property when no validation."""
        snapshot = PriceSnapshot(
            symbol="GTCO", price=50.0, open=49.5, high=50.5, low=49.0,
            close=50.0, change=0.5, change_percent=1.0, volume=1000000,
            value=50000000.0, timestamp=datetime.utcnow(), source=DataSource.NGX_OFFICIAL,
        )
        
        validated = ValidatedSnapshot(snapshot=snapshot, validation=None)
        
        assert validated.is_validated is False
        assert validated.confidence_level == ConfidenceLevel.MEDIUM
        assert validated.confidence_score == 0.7
    
    def test_to_dict_includes_validation(self):
        """Test to_dict includes validation metadata."""
        snapshot = PriceSnapshot(
            symbol="GTCO", price=50.0, open=49.5, high=50.5, low=49.0,
            close=50.0, change=0.5, change_percent=1.0, volume=1000000,
            value=50000000.0, timestamp=datetime.utcnow(), source=DataSource.NGX_OFFICIAL,
        )
        validation = ValidationResult(
            symbol="GTCO", primary_price=50.0, secondary_price=50.25,
            status=ValidationStatus.VALIDATED, confidence_level=ConfidenceLevel.HIGH,
            confidence_score=0.95, price_difference_percent=0.5,
        )
        
        validated = ValidatedSnapshot(snapshot=snapshot, validation=validation)
        result = validated.to_dict()
        
        assert "validation" in result
        assert result["validation"]["is_validated"] is True
        assert result["validation"]["confidence_level"] == "HIGH"
        assert result["validation"]["sources_count"] == 2
        assert result["validation"]["divergence_pct"] == 0.5


class TestValidationServiceResult:
    """Test the ValidationServiceResult class."""
    
    def test_validation_rate(self):
        """Test validation_rate calculation."""
        result = ValidationServiceResult(
            primary_count=10,
            secondary_count=8,
            validated_count=7,
            divergent_count=1,
        )
        
        assert result.validation_rate == 0.8
    
    def test_agreement_rate(self):
        """Test agreement_rate calculation."""
        result = ValidationServiceResult(
            primary_count=10,
            secondary_count=8,
            validated_count=6,
            divergent_count=2,
        )
        
        assert result.agreement_rate == 0.75
    
    def test_get_stats(self):
        """Test get_stats output."""
        result = ValidationServiceResult(
            primary_count=10,
            secondary_count=8,
            validated_count=7,
            divergent_count=1,
            primary_fetch_ms=100.0,
            secondary_fetch_ms=150.0,
            total_time_ms=200.0,
        )
        
        stats = result.get_stats()
        
        assert stats["primary_count"] == 10
        assert stats["secondary_count"] == 8
        assert stats["validated_count"] == 7
        assert stats["timing"]["primary_ms"] == 100.0
        assert stats["timing"]["secondary_ms"] == 150.0


class TestConfidenceConfig:
    """Test custom confidence configurations."""
    
    def test_custom_thresholds(self):
        """Test scorer with custom thresholds."""
        config = ConfidenceConfig(
            agreement_threshold=0.5,  # Stricter
            minor_divergence=1.5,
            major_divergence=3.0,
            suppress_threshold=5.0,
        )
        scorer = DataConfidenceScorer(config)
        
        primary = PriceSnapshot(
            symbol="GTCO", price=50.0, open=49.5, high=50.5, low=49.0,
            close=50.0, change=0.5, change_percent=1.0, volume=1000000,
            value=50000000.0, timestamp=datetime.utcnow(), source=DataSource.NGX_OFFICIAL,
        )
        
        # 0.8% difference - would be agreement with default config
        # but with stricter 0.5% threshold, it's minor divergence
        secondary = PriceSnapshot(
            symbol="GTCO", price=50.40, open=49.5, high=50.5, low=49.0,
            close=50.40, change=0.5, change_percent=1.0, volume=1000000,
            value=50000000.0, timestamp=datetime.utcnow(), source=DataSource.UNKNOWN,
        )
        
        result = scorer.validate(primary, secondary)
        
        # With 0.5% threshold, 0.8% is minor divergence
        assert result.status == ValidationStatus.VALIDATED
        assert result.confidence_level == ConfidenceLevel.MEDIUM


class TestValidationResultSerialization:
    """Test ValidationResult serialization."""
    
    def test_to_dict(self):
        """Test ValidationResult.to_dict()."""
        result = ValidationResult(
            symbol="GTCO",
            primary_price=50.0,
            secondary_price=50.25,
            status=ValidationStatus.VALIDATED,
            confidence_level=ConfidenceLevel.HIGH,
            confidence_score=0.95,
            price_difference=0.25,
            price_difference_percent=0.5,
        )
        
        d = result.to_dict()
        
        assert d["symbol"] == "GTCO"
        assert d["validation_status"] == "VALIDATED"
        assert d["confidence_level"] == "HIGH"
        assert d["confidence_score"] == 0.95
        assert d["primary_price"] == 50.0
        assert d["secondary_price"] == 50.25
        assert d["price_difference_percent"] == 0.5
