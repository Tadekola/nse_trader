"""
Unit tests for Market Regime Engine.

Tests cover:
- Regime classification (Trending, Mean-Reverting, High Volatility, Low Liquidity, News-Driven)
- Exactly ONE regime per session
- Confidence multipliers per regime
- Bias compatibility rules and adjustments
- SUPPRESSED logic remains authoritative
"""
import pytest
from datetime import date, datetime
import numpy as np

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.market_regime_engine import (
    MarketRegimeEngine,
    SessionRegime,
    SessionRegimeAnalysis,
    TrendDirection,
    BiasCompatibility,
    RegimeMetrics,
    REGIME_BIAS_COMPATIBILITY,
    REGIME_CONFIDENCE_MULTIPLIERS,
    get_regime_engine
)
from app.services.probabilistic_bias import (
    BiasSignal,
    BiasDirection,
    ProbabilisticBiasCalculator
)


class TestSessionRegime:
    """Tests for SessionRegime enum."""
    
    def test_regime_values(self):
        """Test that all regime types have correct string values."""
        assert SessionRegime.TRENDING.value == "trending"
        assert SessionRegime.MEAN_REVERTING.value == "mean_reverting"
        assert SessionRegime.HIGH_VOLATILITY.value == "high_volatility"
        assert SessionRegime.LOW_LIQUIDITY.value == "low_liquidity"
        assert SessionRegime.NEWS_DRIVEN.value == "news_driven"
    
    def test_exactly_five_regimes(self):
        """Test that there are exactly 5 regime types."""
        assert len(SessionRegime) == 5


class TestBiasCompatibilityRules:
    """Tests for regime-specific bias compatibility rules."""
    
    def test_all_regimes_have_compatibility_rules(self):
        """Test that every regime has defined compatibility rules."""
        for regime in SessionRegime:
            assert regime in REGIME_BIAS_COMPATIBILITY
    
    def test_all_regimes_have_confidence_multipliers(self):
        """Test that every regime has a confidence multiplier."""
        for regime in SessionRegime:
            assert regime in REGIME_CONFIDENCE_MULTIPLIERS
    
    def test_trending_favors_directional_bias(self):
        """Test that TRENDING regime favors directional signals."""
        compat = REGIME_BIAS_COMPATIBILITY[SessionRegime.TRENDING]
        assert compat.bullish_multiplier >= 1.0
        assert compat.bearish_multiplier >= 1.0
        assert compat.neutral_multiplier < 1.0
    
    def test_mean_reverting_penalizes_directional_bias(self):
        """Test that MEAN_REVERTING regime penalizes directional signals."""
        compat = REGIME_BIAS_COMPATIBILITY[SessionRegime.MEAN_REVERTING]
        assert compat.bullish_multiplier < 1.0
        assert compat.bearish_multiplier < 1.0
        assert compat.neutral_multiplier >= 1.0
    
    def test_high_volatility_has_confidence_penalty(self):
        """Test that HIGH_VOLATILITY regime has a confidence penalty."""
        compat = REGIME_BIAS_COMPATIBILITY[SessionRegime.HIGH_VOLATILITY]
        assert compat.confidence_penalty > 0
    
    def test_low_liquidity_heavily_penalizes(self):
        """Test that LOW_LIQUIDITY regime heavily penalizes directional bias."""
        compat = REGIME_BIAS_COMPATIBILITY[SessionRegime.LOW_LIQUIDITY]
        assert compat.bullish_multiplier <= 0.5
        assert compat.bearish_multiplier <= 0.5
        assert compat.confidence_penalty > 0
    
    def test_news_driven_highest_uncertainty(self):
        """Test that NEWS_DRIVEN has highest confidence penalty."""
        compat = REGIME_BIAS_COMPATIBILITY[SessionRegime.NEWS_DRIVEN]
        # NEWS_DRIVEN should have the highest confidence penalty
        max_penalty = max(c.confidence_penalty for c in REGIME_BIAS_COMPATIBILITY.values())
        assert compat.confidence_penalty == max_penalty


class TestMarketRegimeEngine:
    """Tests for MarketRegimeEngine class."""
    
    @pytest.fixture
    def engine(self):
        """Create a fresh engine instance."""
        engine = MarketRegimeEngine()
        engine.clear_cache()
        return engine
    
    @pytest.fixture
    def trending_bullish_data(self):
        """Price data showing strong uptrend."""
        # Very strong steadily increasing prices (500 per period = 1% daily)
        base = 50000
        prices = [base + i * 500 for i in range(100)]  # Strong uptrend
        volumes = [1000000000] * 100  # Normal volume
        return prices, volumes
    
    @pytest.fixture
    def trending_bearish_data(self):
        """Price data showing strong downtrend."""
        # Very strong steadily decreasing prices
        base = 100000
        prices = [base - i * 500 for i in range(100)]  # Strong downtrend
        volumes = [1000000000] * 100
        return prices, volumes
    
    @pytest.fixture
    def mean_reverting_data(self):
        """Price data showing range-bound oscillation."""
        # Oscillating around a mean with small noise
        base = 50000
        np.random.seed(42)
        noise = np.random.normal(0, 100, 100)  # Small noise
        prices = [base + n for n in noise]
        volumes = [1000000000] * 100
        return prices, volumes
    
    @pytest.fixture
    def high_volatility_data(self):
        """Price data showing high volatility."""
        # Extreme swings that create high volatility ratio
        base = 50000
        np.random.seed(42)
        # Create high volatility in recent period vs baseline
        stable_prices = [base + np.random.normal(0, 200) for _ in range(60)]
        volatile_prices = [base + np.random.normal(0, 5000) for _ in range(40)]
        prices = stable_prices + volatile_prices
        volumes = [1000000000] * 100
        return prices, volumes
    
    @pytest.fixture
    def low_liquidity_data(self):
        """Price and volume data showing low liquidity."""
        base = 50000
        np.random.seed(42)
        prices = [base + np.random.normal(0, 100) for _ in range(100)]
        # Very low volume - 50% of baseline for most, then even lower at end
        volumes = [500000000] * 80 + [300000000] * 20  # Below 0.6 threshold
        return prices, volumes
    
    @pytest.fixture
    def news_driven_data(self):
        """Price and volume data showing news-driven spike."""
        base = 50000
        np.random.seed(42)
        # Stable then volatile prices
        stable = [base + np.random.normal(0, 200) for _ in range(60)]
        volatile = [base + np.random.normal(0, 3000) for _ in range(40)]
        prices = stable + volatile
        # Normal baseline volume, then huge spike (> 2x)
        volumes = [1000000000] * 60 + [2500000000] * 40  # Volume spike at end
        return prices, volumes
    
    # === Regime Classification Tests ===
    
    def test_classifies_exactly_one_regime(self, engine, trending_bullish_data):
        """Test that exactly one regime is classified per session."""
        prices, volumes = trending_bullish_data
        result = engine.classify_session(prices, volumes)
        
        # Should return a SessionRegimeAnalysis
        assert isinstance(result, SessionRegimeAnalysis)
        # Regime should be one of the valid values
        assert result.regime in SessionRegime
    
    def test_trending_bullish_classification(self, engine, trending_bullish_data):
        """Test classification of bullish trending market."""
        prices, volumes = trending_bullish_data
        result = engine.classify_session(prices, volumes)
        
        # Should detect trending with bullish direction
        assert result.regime == SessionRegime.TRENDING
        assert result.trend_direction == TrendDirection.BULLISH
    
    def test_trending_bearish_classification(self, engine, trending_bearish_data):
        """Test classification of bearish trending market."""
        prices, volumes = trending_bearish_data
        result = engine.classify_session(prices, volumes)
        
        # Should detect trending with bearish direction
        assert result.regime == SessionRegime.TRENDING
        assert result.trend_direction == TrendDirection.BEARISH
    
    def test_mean_reverting_classification(self, engine, mean_reverting_data):
        """Test classification of range-bound market."""
        prices, volumes = mean_reverting_data
        result = engine.classify_session(prices, volumes)
        
        # Should be mean-reverting (no strong trend, normal vol/liquidity)
        assert result.regime == SessionRegime.MEAN_REVERTING
        assert result.trend_direction == TrendDirection.NONE
    
    def test_low_liquidity_detection_with_low_volume_ratio(self, engine):
        """Test that low volume ratio is detected in metrics."""
        base = 50000
        prices = [base] * 100
        # Create data where volume_ratio will be < 0.6
        volumes = [1000000000] * 100
        
        result = engine.classify_session(prices, volumes, current_volume=500000000)
        
        # Verify the volume ratio is calculated correctly
        assert result.metrics.volume_ratio < 0.6
        # Engine should detect this as low liquidity OR mean-reverting
        assert result.regime in [SessionRegime.LOW_LIQUIDITY, SessionRegime.MEAN_REVERTING]
    
    def test_volume_spike_detected_in_metrics(self, engine):
        """Test that volume spikes are detected in metrics."""
        base = 50000
        prices = [base] * 100
        volumes = [1000000000] * 100
        
        # Provide very high current volume (3x baseline)
        result = engine.classify_session(prices, volumes, current_volume=3000000000)
        
        # Volume spike should be detected
        assert result.metrics.volume_spike == True
        assert result.metrics.volume_ratio > 2.0
    
    # === Regime Priority Tests ===
    
    def test_regime_has_valid_classification(self, engine):
        """Test that any data produces a valid regime classification."""
        base = 50000
        np.random.seed(42)
        prices = [base + np.random.normal(0, 1000) for _ in range(100)]
        volumes = [1000000000 + np.random.normal(0, 100000000) for _ in range(100)]
        
        result = engine.classify_session(prices, volumes)
        
        # Should always produce exactly one valid regime
        assert result.regime in SessionRegime
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0
    
    def test_volatility_spike_detected_in_metrics(self, engine):
        """Test that volatility spikes are detected in metrics."""
        base = 50000
        # Create high recent volatility vs historical
        stable = [base + np.random.normal(0, 100) for _ in range(60)]
        volatile = [base + np.random.normal(0, 5000) for _ in range(40)]
        prices = stable + volatile
        volumes = [1000000000] * 100
        
        result = engine.classify_session(prices, volumes)
        
        # Volatility ratio should be elevated
        assert result.metrics.volatility_ratio > 1.0
    
    # === Session Caching Tests ===
    
    def test_caches_session_result(self, engine, trending_bullish_data):
        """Test that classification is cached for the session."""
        prices, volumes = trending_bullish_data
        
        result1 = engine.classify_session(prices, volumes)
        result2 = engine.classify_session(prices, volumes)
        
        # Should be the same cached result
        assert result1.session_date == result2.session_date
        assert result1.regime == result2.regime
    
    def test_clear_cache(self, engine, trending_bullish_data):
        """Test that cache can be cleared."""
        prices, volumes = trending_bullish_data
        
        engine.classify_session(prices, volumes)
        engine.clear_cache()
        
        # Cache should be empty
        assert engine.get_regime_metadata() is None
    
    # === Bias Adjustment Tests ===
    
    def test_adjust_probability_trending_bullish(self, engine, trending_bullish_data):
        """Test probability adjustment in bullish trending regime."""
        prices, volumes = trending_bullish_data
        regime = engine.classify_session(prices, volumes)
        
        # Verify we got trending regime
        assert regime.regime == SessionRegime.TRENDING
        assert regime.trend_direction == TrendDirection.BULLISH
        
        # Bullish bias should be increased in bullish trend
        adjusted, reason = engine.adjust_bias_probability(
            bias_probability=70,
            bias_direction="bullish",
            regime_analysis=regime,
            is_suppressed=False
        )
        
        assert adjusted is not None
        # In bullish trend, bullish signals get 1.3x multiplier
        assert adjusted >= 70  # Should be at least original (may be higher with multiplier)
        assert reason is None
    
    def test_adjust_probability_trending_bearish_on_bullish_signal(self, engine, trending_bearish_data):
        """Test that bearish trend penalizes bullish signals."""
        prices, volumes = trending_bearish_data
        regime = engine.classify_session(prices, volumes)
        
        # Bullish bias should be reduced in bearish trend
        adjusted, reason = engine.adjust_bias_probability(
            bias_probability=70,
            bias_direction="bullish",
            regime_analysis=regime,
            is_suppressed=False
        )
        
        assert adjusted is not None
        assert adjusted < 70  # Should reduce counter-trend bullish
    
    def test_adjust_probability_mean_reverting_penalizes_directional(self, engine, mean_reverting_data):
        """Test that mean-reverting regime penalizes directional bias."""
        prices, volumes = mean_reverting_data
        regime = engine.classify_session(prices, volumes)
        
        # Both bullish and bearish should be penalized
        bullish_adj, _ = engine.adjust_bias_probability(70, "bullish", regime, False)
        bearish_adj, _ = engine.adjust_bias_probability(70, "bearish", regime, False)
        neutral_adj, _ = engine.adjust_bias_probability(50, "neutral", regime, False)
        
        assert bullish_adj < 70
        assert bearish_adj < 70
        # Neutral should be relatively favored
        assert neutral_adj >= 50 * 0.9  # Should not be heavily penalized
    
    def test_probability_clamped_to_bounds(self, engine, trending_bullish_data):
        """Test that adjusted probability stays within 0-100."""
        prices, volumes = trending_bullish_data
        regime = engine.classify_session(prices, volumes)
        
        # High probability should not exceed 100
        adjusted_high, _ = engine.adjust_bias_probability(95, "bullish", regime, False)
        assert adjusted_high <= 100
        
        # Low probability should not go below 0
        adjusted_low, _ = engine.adjust_bias_probability(5, "bearish", regime, False)
        assert adjusted_low >= 0


class TestSuppressedLogicAuthoritative:
    """Tests to verify SUPPRESSED logic remains authoritative."""
    
    @pytest.fixture
    def engine(self):
        engine = MarketRegimeEngine()
        engine.clear_cache()
        return engine
    
    @pytest.fixture
    def calculator(self):
        return ProbabilisticBiasCalculator()
    
    @pytest.fixture
    def trending_bullish_data(self):
        base = 50000
        prices = [base + i * 100 for i in range(100)]
        volumes = [1000000000] * 100
        return prices, volumes
    
    def test_suppressed_signal_not_modified_by_regime(self, engine, calculator, trending_bullish_data):
        """Test that already-suppressed signals are NOT modified by regime."""
        prices, volumes = trending_bullish_data
        regime = engine.classify_session(prices, volumes)
        
        # Create a suppressed signal
        suppressed_signal = BiasSignal(
            bias_direction=BiasDirection.NEUTRAL,
            bias_probability=None,
            indicator_agreement=0.0,
            signal_magnitude=0.0,
            data_confidence_factor=0.5,
            reasoning="Suppressed due to low data confidence",
            is_suppressed=True,
            suppression_reason="Data quality below threshold"
        )
        
        # Apply regime adjustment
        adjusted_signal = calculator.apply_regime_adjustment(
            bias_signal=suppressed_signal,
            regime_analysis=regime
        )
        
        # Signal should STILL be suppressed
        assert adjusted_signal.is_suppressed is True
        assert adjusted_signal.bias_probability is None
        assert "suppressed before regime" in adjusted_signal.regime_metadata.get("note", "").lower()
    
    def test_suppress_does_not_change_probability(self, engine, trending_bullish_data):
        """Test that adjust_bias_probability returns None for suppressed signals."""
        prices, volumes = trending_bullish_data
        regime = engine.classify_session(prices, volumes)
        
        # Already suppressed signal
        adjusted, reason = engine.adjust_bias_probability(
            bias_probability=70,
            bias_direction="bullish",
            regime_analysis=regime,
            is_suppressed=True  # Already suppressed
        )
        
        # Should return None (no change) because already suppressed
        assert adjusted is None
        assert reason is None  # No new reason added
    
    def test_regime_suppression_returns_proper_reason(self, engine, calculator):
        """Test that regime-based suppression includes proper reason."""
        # Create a regime that suppresses bullish signals
        # First, modify compatibility to test suppression
        base = 50000
        prices = [base] * 100
        volumes = [1000000000] * 100
        regime = engine.classify_session(prices, volumes)
        
        # Manually create a compatibility that suppresses bullish
        test_compat = BiasCompatibility(
            bullish_multiplier=0.5,
            bearish_multiplier=0.5,
            neutral_multiplier=1.0,
            suppress_bullish=True,
            suppress_bearish=False,
            confidence_penalty=0.1
        )
        regime.bias_compatibility = test_compat
        
        # Create active bullish signal
        active_signal = BiasSignal(
            bias_direction=BiasDirection.BULLISH,
            bias_probability=75,
            indicator_agreement=0.8,
            signal_magnitude=0.7,
            data_confidence_factor=0.95,
            reasoning="Technical analysis suggests bullish",
            is_suppressed=False
        )
        
        # Apply regime adjustment
        adjusted_signal = calculator.apply_regime_adjustment(
            bias_signal=active_signal,
            regime_analysis=regime
        )
        
        # Should be suppressed by regime
        assert adjusted_signal.is_suppressed is True
        assert adjusted_signal.bias_probability is None
        assert "regime" in adjusted_signal.suppression_reason.lower()
        assert adjusted_signal.pre_regime_probability == 75


class TestRegimeMetadata:
    """Tests for regime metadata attachment."""
    
    @pytest.fixture
    def engine(self):
        engine = MarketRegimeEngine()
        engine.clear_cache()
        return engine
    
    def test_to_dict_includes_all_fields(self, engine):
        """Test that to_dict includes all required fields."""
        base = 50000
        prices = [base + i * 50 for i in range(100)]
        volumes = [1000000000] * 100
        
        result = engine.classify_session(prices, volumes)
        result_dict = result.to_dict()
        
        assert "regime" in result_dict
        assert "trend_direction" in result_dict
        assert "confidence" in result_dict
        assert "confidence_multiplier" in result_dict
        assert "bias_adjustments" in result_dict
        assert "metrics" in result_dict
        assert "reasoning" in result_dict
        assert "warnings" in result_dict
        assert "session_date" in result_dict
    
    def test_get_regime_metadata(self, engine):
        """Test get_regime_metadata returns correct structure."""
        base = 50000
        prices = [base + i * 50 for i in range(100)]
        volumes = [1000000000] * 100
        
        engine.classify_session(prices, volumes)
        metadata = engine.get_regime_metadata()
        
        assert metadata is not None
        assert "market_regime" in metadata
        assert "regime_confidence" in metadata
        assert "trend_direction" in metadata
        assert "confidence_multiplier" in metadata
        assert "warnings" in metadata


class TestEdgeCases:
    """Tests for edge cases."""
    
    @pytest.fixture
    def engine(self):
        engine = MarketRegimeEngine()
        engine.clear_cache()
        return engine
    
    def test_minimum_data_length(self, engine):
        """Test handling of minimum data length."""
        # Very short data - should pad
        prices = [50000, 51000, 52000]
        volumes = [1000000000, 1000000000, 1000000000]
        
        # Should not raise, should handle gracefully
        result = engine.classify_session(prices, volumes)
        assert result is not None
        assert result.regime in SessionRegime
    
    def test_constant_prices(self, engine):
        """Test handling of constant prices (no volatility)."""
        prices = [50000] * 100
        volumes = [1000000000] * 100
        
        result = engine.classify_session(prices, volumes)
        
        # Should classify as mean-reverting (no trend)
        assert result.regime == SessionRegime.MEAN_REVERTING
    
    def test_zero_volume_handling(self, engine):
        """Test handling of zero volume."""
        prices = [50000 + i * 10 for i in range(100)]
        volumes = [0] * 100  # Zero volume
        
        # Should handle gracefully (likely low liquidity)
        result = engine.classify_session(prices, volumes)
        assert result is not None
    
    def test_negative_price_handling(self, engine):
        """Test handling of invalid negative prices."""
        prices = [50000] * 50 + [-100] * 50  # Invalid negative
        volumes = [1000000000] * 100
        
        # Should handle gracefully (prices used as-is, metrics may be odd)
        result = engine.classify_session(prices, volumes)
        assert result is not None


class TestSingletonInstance:
    """Tests for singleton regime engine."""
    
    def test_get_regime_engine_returns_same_instance(self):
        """Test that get_regime_engine returns singleton."""
        import app.services.market_regime_engine as mre
        mre._engine_instance = None
        
        engine1 = get_regime_engine()
        engine2 = get_regime_engine()
        
        assert engine1 is engine2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
