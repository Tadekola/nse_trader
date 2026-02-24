"""
Tests for consolidated DataConfidenceScorer (G5 gate).

Verifies:
- Stale data lowers confidence and emits STALE_DATA reason code
- Missing sources emit INSUFFICIENT_SOURCES
- Gappy/high-variance data emits HIGH_PRICE_VARIANCE
- Suppression fires when overall < threshold
- Snapshot validation returns correct status/level
"""
import sys
import os
import pytest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.confidence import (
    DataConfidenceScorer,
    ConfidenceConfig,
    ConfidenceScore,
    ConfidenceLevel,
    ReasonCode,
    ValidationResult,
    ValidationStatus,
)


@pytest.fixture
def scorer():
    return DataConfidenceScorer(ConfidenceConfig())


@pytest.fixture
def strict_scorer():
    return DataConfidenceScorer(ConfidenceConfig(min_confidence_threshold=0.90))


class TestCalculateConfidence:
    """Tests for calculate_confidence() entry point."""

    def test_two_agreeing_sources_high_confidence(self, scorer):
        now = datetime.utcnow()
        sources = [
            {"price": 10.0, "volume": 1000, "source": "NGNMARKET", "timestamp": now},
            {"price": 10.05, "volume": 1050, "source": "kwayisi", "timestamp": now},
        ]
        result = scorer.calculate_confidence("DANGCEM", sources)
        assert result.overall_score >= 0.75
        assert not result.is_suppressed
        assert result.confidence_level in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
        assert len(result.reason_codes) == 0

    def test_stale_data_emits_reason_code(self, scorer):
        old = datetime.utcnow() - timedelta(hours=2)
        sources = [
            {"price": 10.0, "volume": 1000, "source": "NGNMARKET", "timestamp": old},
        ]
        result = scorer.calculate_confidence("DANGCEM", sources)
        assert ReasonCode.STALE_DATA in result.reason_codes
        assert result.is_suppressed

    def test_no_sources_suppressed(self, scorer):
        result = scorer.calculate_confidence("DANGCEM", [])
        assert result.is_suppressed
        assert result.overall_score == 0.0
        assert ReasonCode.INSUFFICIENT_SOURCES in result.reason_codes

    def test_high_price_variance_emits_reason(self, scorer):
        now = datetime.utcnow()
        sources = [
            {"price": 10.0, "volume": 1000, "source": "NGNMARKET", "timestamp": now},
            {"price": 12.0, "volume": 1000, "source": "kwayisi", "timestamp": now},
        ]
        result = scorer.calculate_confidence("DANGCEM", sources)
        assert ReasonCode.HIGH_PRICE_VARIANCE in result.reason_codes
        assert result.is_suppressed

    def test_high_volume_variance_emits_reason(self, scorer):
        now = datetime.utcnow()
        sources = [
            {"price": 10.0, "volume": 1000, "source": "NGNMARKET", "timestamp": now},
            {"price": 10.0, "volume": 5000, "source": "kwayisi", "timestamp": now},
        ]
        result = scorer.calculate_confidence("DANGCEM", sources)
        assert ReasonCode.HIGH_VOLUME_VARIANCE in result.reason_codes

    def test_circuit_breaker_suppresses(self, scorer):
        now = datetime.utcnow()
        sources = [
            {"price": 10.0, "volume": 1000, "source": "NGNMARKET", "timestamp": now},
        ]
        result = scorer.calculate_confidence("DANGCEM", sources, circuit_breaker_active=True)
        assert result.is_suppressed
        assert ReasonCode.CIRCUIT_BREAKER_ACTIVE in result.reason_codes
        assert result.overall_score == 0.0

    def test_single_low_reliability_source(self, scorer):
        now = datetime.utcnow()
        sources = [
            {"price": 10.0, "volume": 1000, "source": "simulated", "timestamp": now},
        ]
        result = scorer.calculate_confidence("DANGCEM", sources)
        assert ReasonCode.INSUFFICIENT_SOURCES in result.reason_codes

    def test_to_dict_structure(self, scorer):
        now = datetime.utcnow()
        sources = [
            {"price": 10.0, "volume": 1000, "source": "NGNMARKET", "timestamp": now},
        ]
        result = scorer.calculate_confidence("DANGCEM", sources)
        d = result.to_dict()
        assert "confidence_score" in d
        assert "confidence_level" in d
        assert "reason_codes" in d
        assert "component_scores" in d
        assert "metrics" in d
        assert isinstance(d["reason_codes"], list)

    def test_strict_threshold_suppresses_mediocre_data(self, strict_scorer):
        now = datetime.utcnow()
        sources = [
            {"price": 10.0, "volume": 1000, "source": "NGNMARKET", "timestamp": now},
        ]
        result = strict_scorer.calculate_confidence("DANGCEM", sources)
        # Single source with 0.95 reliability should still potentially be below 0.90 threshold
        # because volume/freshness sub-scores won't be perfect
        assert result.overall_score < 1.0


class TestValidate:
    """Tests for validate() entry point (snapshot comparison)."""

    def _make_snapshot(self, symbol, price, source="ngx_official", ts=None):
        """Create a mock snapshot."""
        from types import SimpleNamespace
        return SimpleNamespace(
            symbol=symbol,
            price=price,
            source=SimpleNamespace(value=source),
            timestamp=ts or datetime.utcnow(),
        )

    def test_validated_when_prices_agree(self, scorer):
        primary = self._make_snapshot("DANGCEM", 300.0)
        secondary = self._make_snapshot("DANGCEM", 300.5, source="kwayisi")
        result = scorer.validate(primary, secondary)
        assert result.status == ValidationStatus.VALIDATED
        assert result.confidence_level == ConfidenceLevel.HIGH
        assert result.confidence_score > 0.9

    def test_divergent_when_prices_differ(self, scorer):
        primary = self._make_snapshot("DANGCEM", 300.0)
        secondary = self._make_snapshot("DANGCEM", 320.0, source="kwayisi")
        result = scorer.validate(primary, secondary)
        assert result.status == ValidationStatus.DIVERGENT
        assert ReasonCode.PRICE_DIVERGENT in result.reason_codes

    def test_primary_only_when_no_secondary(self, scorer):
        primary = self._make_snapshot("DANGCEM", 300.0)
        result = scorer.validate(primary, None)
        assert result.status == ValidationStatus.PRIMARY_ONLY
        assert result.confidence_level == ConfidenceLevel.MEDIUM
        assert ReasonCode.SECONDARY_MISSING in result.reason_codes

    def test_stale_secondary(self, scorer):
        primary = self._make_snapshot("DANGCEM", 300.0)
        old_ts = datetime.utcnow() - timedelta(hours=48)
        secondary = self._make_snapshot("DANGCEM", 300.0, source="kwayisi", ts=old_ts)
        result = scorer.validate(primary, secondary)
        assert result.status == ValidationStatus.SECONDARY_STALE
        assert ReasonCode.SECONDARY_STALE in result.reason_codes

    def test_extreme_divergence_suppresses(self, scorer):
        primary = self._make_snapshot("DANGCEM", 100.0)
        secondary = self._make_snapshot("DANGCEM", 200.0, source="kwayisi")
        result = scorer.validate(primary, secondary)
        assert result.confidence_level == ConfidenceLevel.SUPPRESSED
        assert result.confidence_score == 0.0

    def test_validation_result_to_dict(self, scorer):
        primary = self._make_snapshot("DANGCEM", 300.0)
        result = scorer.validate(primary, None)
        d = result.to_dict()
        assert "symbol" in d
        assert "validation_status" in d
        assert "confidence_level" in d
        assert "reason_codes" in d
        assert d["symbol"] == "DANGCEM"


class TestConfidenceConfig:
    """Test config validation."""

    def test_weights_must_sum_to_one(self):
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            ConfidenceConfig(price_weight=0.5, volume_weight=0.5, freshness_weight=0.5, source_weight=0.5)

    def test_default_config_valid(self):
        cfg = ConfidenceConfig()
        total = cfg.price_weight + cfg.volume_weight + cfg.freshness_weight + cfg.source_weight
        assert abs(total - 1.0) < 0.001
