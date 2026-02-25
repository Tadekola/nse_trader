"""
Unit tests for Signal Lifecycle Governance Module.

Tests cover:
- TTL calculation and expiry enforcement
- NO_TRADE state triggering conditions
- Signal state transitions
- NO_TRADE decision logging
- Human-readable explanations
"""
import pytest
from datetime import datetime, timedelta, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.signal_lifecycle import (
    SignalLifecycleManager,
    SignalState,
    NoTradeReason,
    NoTradeDecision,
    LifecycleConfig,
    SignalLifecycleResult,
    get_lifecycle_manager
)


class TestSignalState:
    """Tests for SignalState enum."""
    
    def test_all_states_defined(self):
        """Test that all required states are defined."""
        assert SignalState.ACTIVE.value == "active"
        assert SignalState.SUPPRESSED.value == "suppressed"
        assert SignalState.INVALID.value == "invalid"
        assert SignalState.NO_TRADE.value == "no_trade"
    
    def test_exactly_four_states(self):
        """Test that there are exactly 4 signal states."""
        assert len(SignalState) == 4


class TestNoTradeReason:
    """Tests for NoTradeReason enum."""
    
    def test_all_reasons_defined(self):
        """Test that all NO_TRADE reasons are defined."""
        assert NoTradeReason.LOW_DATA_CONFIDENCE.value == "low_data_confidence"
        assert NoTradeReason.HOSTILE_REGIME.value == "hostile_regime"
        assert NoTradeReason.WEAK_INDICATOR_AGREEMENT.value == "weak_indicator_agreement"
        assert NoTradeReason.LOW_CALIBRATION_CONFIDENCE.value == "low_calibration_confidence"
        assert NoTradeReason.CONFLICTING_SIGNALS.value == "conflicting_signals"
        assert NoTradeReason.EXTREME_VOLATILITY.value == "extreme_volatility"
        assert NoTradeReason.INSUFFICIENT_LIQUIDITY.value == "insufficient_liquidity"
        assert NoTradeReason.MULTIPLE_FACTORS.value == "multiple_factors"


class TestLifecycleConfig:
    """Tests for LifecycleConfig defaults."""
    
    def test_default_ttl_values(self):
        """Test default TTL values."""
        config = LifecycleConfig()
        
        assert config.short_term_ttl_hours == 8
        assert config.swing_ttl_hours == 72
        assert config.long_term_ttl_hours == 168
        assert config.default_ttl_hours == 24
    
    def test_default_thresholds(self):
        """Test default NO_TRADE thresholds."""
        config = LifecycleConfig()
        
        assert config.min_data_confidence == 0.70
        assert config.min_indicator_agreement == 0.40
        assert config.min_calibration_confidence == 0.50
        assert config.max_regime_hostility == 0.70
    
    def test_hostile_regimes_defined(self):
        """Test hostile regime thresholds are defined."""
        config = LifecycleConfig()
        
        assert "news_driven" in config.hostile_regimes
        assert "high_volatility" in config.hostile_regimes
        assert "low_liquidity" in config.hostile_regimes


class TestTTLCalculation:
    """Tests for TTL calculation and expiry."""
    
    @pytest.fixture
    def manager(self):
        """Create a fresh lifecycle manager."""
        manager = SignalLifecycleManager()
        manager.clear_log()
        return manager
    
    def test_short_term_ttl(self, manager):
        """Test short-term signals get 8-hour TTL."""
        now = datetime.now(timezone.utc)
        expires = manager.calculate_expiry("short_term", now)
        
        expected = now + timedelta(hours=8)
        assert abs((expires - expected).total_seconds()) < 1
    
    def test_swing_ttl(self, manager):
        """Test swing signals get 72-hour TTL."""
        now = datetime.now(timezone.utc)
        expires = manager.calculate_expiry("swing", now)
        
        expected = now + timedelta(hours=72)
        assert abs((expires - expected).total_seconds()) < 1
    
    def test_long_term_ttl(self, manager):
        """Test long-term signals get 168-hour (7-day) TTL."""
        now = datetime.now(timezone.utc)
        expires = manager.calculate_expiry("long_term", now)
        
        expected = now + timedelta(hours=168)
        assert abs((expires - expected).total_seconds()) < 1
    
    def test_unknown_horizon_uses_default(self, manager):
        """Test unknown horizon uses default TTL."""
        now = datetime.now(timezone.utc)
        expires = manager.calculate_expiry("unknown_horizon", now)
        
        expected = now + timedelta(hours=24)
        assert abs((expires - expected).total_seconds()) < 1
    
    def test_is_expired_false_for_future(self, manager):
        """Test is_expired returns False for future expiry."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        assert manager.is_expired(future) == False
    
    def test_is_expired_true_for_past(self, manager):
        """Test is_expired returns True for past expiry."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        assert manager.is_expired(past) == True


class TestNoTradeEvaluation:
    """Tests for NO_TRADE state evaluation."""
    
    @pytest.fixture
    def manager(self):
        manager = SignalLifecycleManager()
        manager.clear_log()
        return manager
    
    @pytest.fixture
    def good_signal_params(self):
        """Parameters for a healthy signal that should be ACTIVE."""
        return {
            "symbol": "DANGCEM",
            "horizon": "swing",
            "data_confidence": 0.85,
            "indicator_agreement": 0.65,
            "regime": "trending",
            "regime_confidence": 0.80,
            "bias_probability": 72,
            "is_suppressed": False
        }
    
    def test_active_signal_with_good_params(self, manager, good_signal_params):
        """Test that good parameters produce ACTIVE state."""
        result = manager.evaluate_lifecycle(**good_signal_params)
        
        assert result.state == SignalState.ACTIVE
        assert result.is_valid == True
        assert result.no_trade_decision is None
    
    def test_no_trade_low_data_confidence(self, manager, good_signal_params):
        """Test NO_TRADE is triggered by low data confidence."""
        good_signal_params["data_confidence"] = 0.50  # Below 0.70 threshold
        
        result = manager.evaluate_lifecycle(**good_signal_params)
        
        assert result.state == SignalState.NO_TRADE
        assert result.is_valid == False
        assert result.no_trade_decision is not None
        assert NoTradeReason.LOW_DATA_CONFIDENCE in result.no_trade_decision.reasons
    
    def test_no_trade_weak_indicator_agreement(self, manager, good_signal_params):
        """Test NO_TRADE is triggered by weak indicator agreement."""
        good_signal_params["indicator_agreement"] = 0.25  # Below 0.40 threshold
        
        result = manager.evaluate_lifecycle(**good_signal_params)
        
        assert result.state == SignalState.NO_TRADE
        assert result.is_valid == False
        assert NoTradeReason.WEAK_INDICATOR_AGREEMENT in result.no_trade_decision.reasons
    
    def test_no_trade_low_calibration_confidence(self, manager, good_signal_params):
        """Test NO_TRADE is triggered by low calibration confidence."""
        good_signal_params["calibration_confidence"] = 0.30  # Below 0.50 threshold
        
        result = manager.evaluate_lifecycle(**good_signal_params)
        
        assert result.state == SignalState.NO_TRADE
        assert result.is_valid == False
        assert NoTradeReason.LOW_CALIBRATION_CONFIDENCE in result.no_trade_decision.reasons
    
    def test_no_trade_hostile_regime(self, manager, good_signal_params):
        """Test NO_TRADE is triggered by hostile regime."""
        good_signal_params["regime"] = "news_driven"
        good_signal_params["regime_confidence"] = 0.30  # High hostility
        
        result = manager.evaluate_lifecycle(**good_signal_params)
        
        assert result.state == SignalState.NO_TRADE
        assert result.is_valid == False
        assert NoTradeReason.HOSTILE_REGIME in result.no_trade_decision.reasons
    
    def test_no_trade_multiple_factors(self, manager, good_signal_params):
        """Test multiple factors trigger MULTIPLE_FACTORS reason."""
        good_signal_params["data_confidence"] = 0.50
        good_signal_params["indicator_agreement"] = 0.25
        good_signal_params["calibration_confidence"] = 0.30
        
        result = manager.evaluate_lifecycle(**good_signal_params)
        
        assert result.state == SignalState.NO_TRADE
        assert len(result.no_trade_decision.reasons) >= 3
        assert result.no_trade_decision.primary_reason == NoTradeReason.MULTIPLE_FACTORS
    
    def test_suppressed_signal_stays_suppressed(self, manager, good_signal_params):
        """Test that already-suppressed signals stay SUPPRESSED."""
        good_signal_params["is_suppressed"] = True
        good_signal_params["suppression_reason"] = "Data quality below threshold"
        
        result = manager.evaluate_lifecycle(**good_signal_params)
        
        assert result.state == SignalState.SUPPRESSED
        assert result.is_valid == False
        assert result.suppression_reason == "Data quality below threshold"


class TestNoTradeDecision:
    """Tests for NoTradeDecision dataclass."""
    
    def test_to_dict_contains_all_fields(self):
        """Test that to_dict includes all required fields."""
        decision = NoTradeDecision(
            symbol="DANGCEM",
            timestamp=datetime.now(timezone.utc),
            reasons=[NoTradeReason.LOW_DATA_CONFIDENCE],
            primary_reason=NoTradeReason.LOW_DATA_CONFIDENCE,
            human_readable="NO_TRADE for DANGCEM: Low data confidence",
            data_confidence=0.50,
            regime="trending",
            regime_confidence=0.80,
            indicator_agreement=0.65,
            calibration_confidence=0.60,
            thresholds_breached={"data_confidence": (0.50, 0.70)}
        )
        
        result = decision.to_dict()
        
        assert "symbol" in result
        assert "timestamp" in result
        assert "state" in result
        assert result["state"] == "no_trade"
        assert "reasons" in result
        assert "primary_reason" in result
        assert "human_readable" in result
        assert "context" in result
        assert "thresholds_breached" in result
    
    def test_human_readable_is_clear(self):
        """Test that human_readable explanation is clear."""
        decision = NoTradeDecision(
            symbol="DANGCEM",
            timestamp=datetime.now(timezone.utc),
            reasons=[NoTradeReason.LOW_DATA_CONFIDENCE],
            primary_reason=NoTradeReason.LOW_DATA_CONFIDENCE,
            human_readable="NO_TRADE for DANGCEM: Data confidence (50%) is below threshold (70%)"
        )
        
        assert "DANGCEM" in decision.human_readable
        assert "50%" in decision.human_readable or "threshold" in decision.human_readable.lower()


class TestNoTradeLogging:
    """Tests for NO_TRADE decision logging."""
    
    @pytest.fixture
    def manager(self):
        manager = SignalLifecycleManager()
        manager.clear_log()
        return manager
    
    def test_no_trade_is_logged(self, manager):
        """Test that NO_TRADE decisions are logged."""
        result = manager.evaluate_lifecycle(
            symbol="DANGCEM",
            horizon="swing",
            data_confidence=0.50,  # Triggers NO_TRADE
            indicator_agreement=0.65,
            regime="trending",
            regime_confidence=0.80,
            bias_probability=72
        )
        
        assert result.state == SignalState.NO_TRADE
        
        log = manager.get_no_trade_log()
        assert len(log) >= 1
        assert log[0].symbol == "DANGCEM"
    
    def test_get_no_trade_log_by_symbol(self, manager):
        """Test filtering NO_TRADE log by symbol."""
        # Create NO_TRADE for two different symbols
        manager.evaluate_lifecycle(
            symbol="DANGCEM", horizon="swing", data_confidence=0.50,
            indicator_agreement=0.65, regime="trending",
            regime_confidence=0.80, bias_probability=72
        )
        manager.evaluate_lifecycle(
            symbol="ZENITHBANK", horizon="swing", data_confidence=0.50,
            indicator_agreement=0.65, regime="trending",
            regime_confidence=0.80, bias_probability=72
        )
        
        dangcem_log = manager.get_no_trade_log(symbol="DANGCEM")
        assert len(dangcem_log) == 1
        assert dangcem_log[0].symbol == "DANGCEM"
    
    def test_get_no_trade_stats(self, manager):
        """Test NO_TRADE statistics."""
        # Create multiple NO_TRADE decisions
        for _ in range(3):
            manager.evaluate_lifecycle(
                symbol="DANGCEM", horizon="swing", data_confidence=0.50,
                indicator_agreement=0.65, regime="trending",
                regime_confidence=0.80, bias_probability=72
            )
        
        manager.evaluate_lifecycle(
            symbol="ZENITHBANK", horizon="swing", data_confidence=0.85,
            indicator_agreement=0.25,  # Different reason
            regime="trending", regime_confidence=0.80, bias_probability=72
        )
        
        stats = manager.get_no_trade_stats()
        
        assert stats["total"] == 4
        assert "by_reason" in stats
        assert "by_regime" in stats


class TestSignalValidation:
    """Tests for signal state validation."""
    
    @pytest.fixture
    def manager(self):
        return SignalLifecycleManager()
    
    def test_validate_active_not_expired(self, manager):
        """Test that active, non-expired signal is valid."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        state, is_valid = manager.validate_signal_state("active", future)
        
        assert state == SignalState.ACTIVE
        assert is_valid == True
    
    def test_validate_expired_signal(self, manager):
        """Test that expired signal is INVALID."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        state, is_valid = manager.validate_signal_state("active", past)
        
        assert state == SignalState.INVALID
        assert is_valid == False
    
    def test_validate_suppressed_signal(self, manager):
        """Test that suppressed signal stays suppressed and invalid."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        state, is_valid = manager.validate_signal_state("suppressed", future)
        
        assert state == SignalState.SUPPRESSED
        assert is_valid == False
    
    def test_validate_no_trade_signal(self, manager):
        """Test that NO_TRADE signal stays NO_TRADE and invalid."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        state, is_valid = manager.validate_signal_state("no_trade", future)
        
        assert state == SignalState.NO_TRADE
        assert is_valid == False
    
    def test_validate_invalid_state_string(self, manager):
        """Test that invalid state string returns INVALID."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        state, is_valid = manager.validate_signal_state("unknown_state", future)
        
        assert state == SignalState.INVALID
        assert is_valid == False


class TestLifecycleResult:
    """Tests for SignalLifecycleResult dataclass."""
    
    def test_active_result_to_dict(self):
        """Test ACTIVE result serialization."""
        result = SignalLifecycleResult(
            state=SignalState.ACTIVE,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            is_valid=True,
            reasoning="Signal is active and valid"
        )
        
        d = result.to_dict()
        
        assert d["state"] == "active"
        assert d["is_valid"] == True
        assert "expires_at" in d
        assert "reasoning" in d
    
    def test_no_trade_result_to_dict(self):
        """Test NO_TRADE result serialization."""
        decision = NoTradeDecision(
            symbol="DANGCEM",
            timestamp=datetime.now(timezone.utc),
            reasons=[NoTradeReason.LOW_DATA_CONFIDENCE],
            primary_reason=NoTradeReason.LOW_DATA_CONFIDENCE,
            human_readable="NO_TRADE: Low data confidence"
        )
        
        result = SignalLifecycleResult(
            state=SignalState.NO_TRADE,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            is_valid=False,
            no_trade_decision=decision,
            reasoning="NO_TRADE: Low data confidence"
        )
        
        d = result.to_dict()
        
        assert d["state"] == "no_trade"
        assert d["is_valid"] == False
        assert "no_trade_decision" in d


class TestSingletonInstance:
    """Tests for singleton lifecycle manager."""
    
    def test_get_lifecycle_manager_returns_same_instance(self):
        """Test that get_lifecycle_manager returns singleton."""
        import app.services.signal_lifecycle as sl
        sl._lifecycle_manager = None
        
        mgr1 = get_lifecycle_manager()
        mgr2 = get_lifecycle_manager()
        
        assert mgr1 is mgr2


class TestWarnings:
    """Tests for lifecycle warnings."""
    
    @pytest.fixture
    def manager(self):
        return SignalLifecycleManager()
    
    def test_warning_when_approaching_threshold(self, manager):
        """Test that warnings are generated when approaching thresholds."""
        result = manager.evaluate_lifecycle(
            symbol="DANGCEM",
            horizon="swing",
            data_confidence=0.75,  # Just above 0.70 threshold
            indicator_agreement=0.50,  # Just above 0.40 threshold
            regime="trending",
            regime_confidence=0.80,
            bias_probability=72
        )
        
        assert result.state == SignalState.ACTIVE
        assert len(result.warnings) > 0
    
    def test_warning_for_volatile_regime(self, manager):
        """Test that warnings are generated for volatile regimes."""
        result = manager.evaluate_lifecycle(
            symbol="DANGCEM",
            horizon="swing",
            data_confidence=0.90,
            indicator_agreement=0.80,
            regime="high_volatility",
            regime_confidence=0.90,  # High confidence, but volatile regime
            bias_probability=72
        )
        
        assert result.state == SignalState.ACTIVE
        # Should have warning about elevated uncertainty
        assert any("volatility" in w.lower() for w in result.warnings)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
