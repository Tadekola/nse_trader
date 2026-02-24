"""
Unit tests for Probabilistic Bias module.

Tests cover:
- Probability bounds (0-100)
- Correct bias mapping (BUY→bullish, HOLD→neutral, SELL→bearish)
- No probabilities for SUPPRESSED signals
- Confidence penalty calculation
- Uncertainty-aware text generation
"""
import pytest
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.probabilistic_bias import (
    ProbabilisticBiasCalculator,
    BiasSignal,
    BiasDirection,
    convert_action_to_bias_label,
    generate_uncertainty_text,
    get_bias_calculator,
    ACTION_TO_BIAS_MAP,
    ACTION_BASE_PROBABILITY
)


class TestBiasDirection:
    """Tests for BiasDirection enum."""
    
    def test_bias_direction_values(self):
        """Test that all bias directions have correct string values."""
        assert BiasDirection.BULLISH.value == "bullish"
        assert BiasDirection.NEUTRAL.value == "neutral"
        assert BiasDirection.BEARISH.value == "bearish"


class TestActionToBiasMapping:
    """Tests for action to bias mapping."""
    
    def test_buy_maps_to_bullish(self):
        """Test BUY actions map to bullish bias."""
        assert ACTION_TO_BIAS_MAP["BUY"] == BiasDirection.BULLISH
        assert ACTION_TO_BIAS_MAP["STRONG_BUY"] == BiasDirection.BULLISH
    
    def test_sell_maps_to_bearish(self):
        """Test SELL actions map to bearish bias."""
        assert ACTION_TO_BIAS_MAP["SELL"] == BiasDirection.BEARISH
        assert ACTION_TO_BIAS_MAP["STRONG_SELL"] == BiasDirection.BEARISH
    
    def test_hold_maps_to_neutral(self):
        """Test HOLD maps to neutral bias."""
        assert ACTION_TO_BIAS_MAP["HOLD"] == BiasDirection.NEUTRAL
    
    def test_avoid_maps_to_neutral(self):
        """Test AVOID maps to neutral bias."""
        assert ACTION_TO_BIAS_MAP["AVOID"] == BiasDirection.NEUTRAL


class TestConvertActionToBiasLabel:
    """Tests for convert_action_to_bias_label function."""
    
    def test_buy_to_bullish_bias_label(self):
        """Test BUY converts to 'Bullish Bias' label."""
        assert convert_action_to_bias_label("BUY") == "Bullish Bias"
        assert convert_action_to_bias_label("STRONG_BUY") == "Bullish Bias"
    
    def test_sell_to_bearish_bias_label(self):
        """Test SELL converts to 'Bearish Bias' label."""
        assert convert_action_to_bias_label("SELL") == "Bearish Bias"
        assert convert_action_to_bias_label("STRONG_SELL") == "Bearish Bias"
    
    def test_hold_to_neutral_bias_label(self):
        """Test HOLD converts to 'Neutral Bias' label."""
        assert convert_action_to_bias_label("HOLD") == "Neutral Bias"
    
    def test_case_insensitive(self):
        """Test that conversion is case insensitive."""
        assert convert_action_to_bias_label("buy") == "Bullish Bias"
        assert convert_action_to_bias_label("Buy") == "Bullish Bias"
        assert convert_action_to_bias_label("sell") == "Bearish Bias"
    
    def test_unknown_action_returns_neutral(self):
        """Test unknown action returns neutral bias."""
        assert convert_action_to_bias_label("UNKNOWN") == "Neutral Bias"


class TestBiasSignal:
    """Tests for BiasSignal dataclass."""
    
    def test_active_signal_to_dict(self):
        """Test active signal conversion to dict includes probability."""
        signal = BiasSignal(
            bias_direction=BiasDirection.BULLISH,
            bias_probability=75,
            indicator_agreement=0.8,
            signal_magnitude=0.6,
            data_confidence_factor=1.0,
            reasoning="Test reasoning",
            is_suppressed=False
        )
        
        result = signal.to_dict()
        
        assert result["bias_direction"] == "bullish"
        assert result["bias_probability"] == 75
        assert result["indicator_agreement"] == 0.8
        assert result["is_suppressed"] is False
        assert "suppression_reason" not in result
    
    def test_suppressed_signal_to_dict_no_probability(self):
        """Test suppressed signal does NOT include probability."""
        signal = BiasSignal(
            bias_direction=BiasDirection.NEUTRAL,
            bias_probability=None,
            indicator_agreement=0.0,
            signal_magnitude=0.0,
            data_confidence_factor=0.5,
            reasoning="Suppressed due to low confidence",
            is_suppressed=True,
            suppression_reason="Data quality below threshold"
        )
        
        result = signal.to_dict()
        
        assert result["bias_direction"] == "neutral"
        assert "bias_probability" not in result  # Must NOT be present
        assert result["is_suppressed"] is True
        assert result["suppression_reason"] == "Data quality below threshold"


class TestProbabilisticBiasCalculator:
    """Tests for ProbabilisticBiasCalculator class."""
    
    @pytest.fixture
    def calculator(self):
        """Create a fresh calculator instance."""
        return ProbabilisticBiasCalculator()
    
    @pytest.fixture
    def bullish_signals(self):
        """Signals that agree on bullish direction."""
        return [
            {"direction": "bullish", "strength": 0.8},
            {"direction": "bullish", "strength": 0.6},
            {"direction": "bullish", "strength": 0.5},
            {"direction": "neutral", "strength": 0.1}
        ]
    
    @pytest.fixture
    def bearish_signals(self):
        """Signals that agree on bearish direction."""
        return [
            {"direction": "bearish", "strength": -0.7},
            {"direction": "bearish", "strength": -0.5},
            {"direction": "bearish", "strength": -0.4}
        ]
    
    @pytest.fixture
    def mixed_signals(self):
        """Mixed signals with no clear direction."""
        return [
            {"direction": "bullish", "strength": 0.3},
            {"direction": "bearish", "strength": -0.3},
            {"direction": "neutral", "strength": 0.0}
        ]
    
    # === Probability Bounds Tests ===
    
    def test_probability_is_integer(self, calculator, bullish_signals):
        """Test that bias_probability is always an integer."""
        result = calculator.calculate_bias(
            internal_action="BUY",
            signals=bullish_signals,
            recommendation_confidence=80.0,
            data_confidence_score=0.95,
            is_suppressed=False
        )
        
        assert isinstance(result.bias_probability, int)
    
    def test_probability_minimum_bound(self, calculator, mixed_signals):
        """Test that probability is never below 0."""
        result = calculator.calculate_bias(
            internal_action="HOLD",
            signals=mixed_signals,
            recommendation_confidence=10.0,
            data_confidence_score=0.5,
            is_suppressed=False
        )
        
        assert result.bias_probability >= 0
    
    def test_probability_maximum_bound(self, calculator, bullish_signals):
        """Test that probability is never above 100."""
        result = calculator.calculate_bias(
            internal_action="STRONG_BUY",
            signals=bullish_signals,
            recommendation_confidence=100.0,
            data_confidence_score=1.0,
            is_suppressed=False
        )
        
        assert result.bias_probability <= 100
    
    def test_probability_within_bounds_all_actions(self, calculator, bullish_signals):
        """Test probability bounds for all action types."""
        for action in ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL", "AVOID"]:
            result = calculator.calculate_bias(
                internal_action=action,
                signals=bullish_signals,
                recommendation_confidence=75.0,
                data_confidence_score=0.9,
                is_suppressed=False
            )
            
            assert 0 <= result.bias_probability <= 100, f"Failed for action {action}"
    
    # === Bias Direction Mapping Tests ===
    
    def test_buy_action_maps_to_bullish(self, calculator, bullish_signals):
        """Test BUY action results in bullish bias direction."""
        result = calculator.calculate_bias(
            internal_action="BUY",
            signals=bullish_signals,
            recommendation_confidence=70.0,
            data_confidence_score=0.9,
            is_suppressed=False
        )
        
        assert result.bias_direction == BiasDirection.BULLISH
    
    def test_sell_action_maps_to_bearish(self, calculator, bearish_signals):
        """Test SELL action results in bearish bias direction."""
        result = calculator.calculate_bias(
            internal_action="SELL",
            signals=bearish_signals,
            recommendation_confidence=70.0,
            data_confidence_score=0.9,
            is_suppressed=False
        )
        
        assert result.bias_direction == BiasDirection.BEARISH
    
    def test_hold_action_maps_to_neutral(self, calculator, mixed_signals):
        """Test HOLD action results in neutral bias direction."""
        result = calculator.calculate_bias(
            internal_action="HOLD",
            signals=mixed_signals,
            recommendation_confidence=50.0,
            data_confidence_score=0.9,
            is_suppressed=False
        )
        
        assert result.bias_direction == BiasDirection.NEUTRAL
    
    # === Suppression Tests ===
    
    def test_suppressed_signal_has_no_probability(self, calculator, bullish_signals):
        """Test that SUPPRESSED signals have NULL probability."""
        result = calculator.calculate_bias(
            internal_action="BUY",
            signals=bullish_signals,
            recommendation_confidence=80.0,
            data_confidence_score=0.5,
            is_suppressed=True,
            suppression_reason="Data quality below threshold"
        )
        
        assert result.is_suppressed is True
        assert result.bias_probability is None
    
    def test_suppressed_signal_has_neutral_direction(self, calculator, bullish_signals):
        """Test that SUPPRESSED signals have neutral direction."""
        result = calculator.calculate_bias(
            internal_action="STRONG_BUY",  # Would be bullish if not suppressed
            signals=bullish_signals,
            recommendation_confidence=90.0,
            data_confidence_score=0.9,
            is_suppressed=True,
            suppression_reason="Circuit breaker active"
        )
        
        assert result.bias_direction == BiasDirection.NEUTRAL
    
    def test_suppressed_signal_includes_suppression_reason(self, calculator, bullish_signals):
        """Test that SUPPRESSED signals include the reason."""
        reason = "Price variance exceeds threshold"
        result = calculator.calculate_bias(
            internal_action="BUY",
            signals=bullish_signals,
            recommendation_confidence=80.0,
            data_confidence_score=0.6,
            is_suppressed=True,
            suppression_reason=reason
        )
        
        assert result.suppression_reason == reason
        assert reason in result.reasoning
    
    # === Confidence Penalty Tests ===
    
    def test_no_penalty_above_threshold(self, calculator, bullish_signals):
        """Test no confidence penalty when data confidence >= 0.9."""
        result = calculator.calculate_bias(
            internal_action="BUY",
            signals=bullish_signals,
            recommendation_confidence=70.0,
            data_confidence_score=0.95,
            is_suppressed=False
        )
        
        assert result.data_confidence_factor == 1.0
    
    def test_penalty_below_threshold(self, calculator, bullish_signals):
        """Test confidence penalty when data confidence < 0.9."""
        result = calculator.calculate_bias(
            internal_action="BUY",
            signals=bullish_signals,
            recommendation_confidence=70.0,
            data_confidence_score=0.75,
            is_suppressed=False
        )
        
        assert result.data_confidence_factor < 1.0
    
    def test_higher_confidence_yields_less_penalty(self, calculator, bullish_signals):
        """Test that higher data confidence yields less penalty."""
        result_low = calculator.calculate_bias(
            internal_action="BUY",
            signals=bullish_signals,
            recommendation_confidence=70.0,
            data_confidence_score=0.5,
            is_suppressed=False
        )
        
        result_high = calculator.calculate_bias(
            internal_action="BUY",
            signals=bullish_signals,
            recommendation_confidence=70.0,
            data_confidence_score=0.8,
            is_suppressed=False
        )
        
        assert result_high.data_confidence_factor > result_low.data_confidence_factor
    
    def test_penalty_reduces_probability(self, calculator, bullish_signals):
        """Test that confidence penalty reduces the final probability."""
        # Same conditions except data confidence
        high_confidence_result = calculator.calculate_bias(
            internal_action="BUY",
            signals=bullish_signals,
            recommendation_confidence=70.0,
            data_confidence_score=0.95,
            is_suppressed=False
        )
        
        low_confidence_result = calculator.calculate_bias(
            internal_action="BUY",
            signals=bullish_signals,
            recommendation_confidence=70.0,
            data_confidence_score=0.6,
            is_suppressed=False
        )
        
        assert high_confidence_result.bias_probability > low_confidence_result.bias_probability
    
    # === Indicator Agreement Tests ===
    
    def test_high_agreement_increases_probability(self, calculator):
        """Test that high indicator agreement increases probability."""
        # All bullish signals
        high_agreement_signals = [
            {"direction": "bullish", "strength": 0.7},
            {"direction": "bullish", "strength": 0.6},
            {"direction": "bullish", "strength": 0.5}
        ]
        
        # Mixed signals
        low_agreement_signals = [
            {"direction": "bullish", "strength": 0.5},
            {"direction": "bearish", "strength": -0.3},
            {"direction": "neutral", "strength": 0.0}
        ]
        
        high_result = calculator.calculate_bias(
            internal_action="BUY",
            signals=high_agreement_signals,
            recommendation_confidence=70.0,
            data_confidence_score=0.95,
            is_suppressed=False
        )
        
        low_result = calculator.calculate_bias(
            internal_action="BUY",
            signals=low_agreement_signals,
            recommendation_confidence=70.0,
            data_confidence_score=0.95,
            is_suppressed=False
        )
        
        assert high_result.indicator_agreement > low_result.indicator_agreement
    
    # === Reasoning Text Tests ===
    
    def test_reasoning_includes_probability(self, calculator, bullish_signals):
        """Test that reasoning text includes the probability."""
        result = calculator.calculate_bias(
            internal_action="BUY",
            signals=bullish_signals,
            recommendation_confidence=70.0,
            data_confidence_score=0.95,
            is_suppressed=False
        )
        
        assert f"{result.bias_probability}%" in result.reasoning
    
    def test_reasoning_uses_uncertainty_language(self, calculator, bullish_signals):
        """Test that reasoning uses probabilistic language, not deterministic."""
        result = calculator.calculate_bias(
            internal_action="BUY",
            signals=bullish_signals,
            recommendation_confidence=70.0,
            data_confidence_score=0.95,
            is_suppressed=False
        )
        
        # Should use probabilistic language
        probabilistic_terms = ["suggests", "indicates", "leans", "probability", "bias"]
        assert any(term in result.reasoning.lower() for term in probabilistic_terms)
        
        # Should NOT use deterministic language
        deterministic_terms = ["strong buy", "definitely", "certain", "guaranteed"]
        assert not any(term in result.reasoning.lower() for term in deterministic_terms)


class TestGenerateUncertaintyText:
    """Tests for generate_uncertainty_text function."""
    
    def test_high_probability_uses_strong_language(self):
        """Test that high probability uses stronger uncertainty language."""
        text = generate_uncertainty_text(
            bias_direction=BiasDirection.BULLISH,
            bias_probability=85,
            internal_action="STRONG_BUY"
        )
        
        assert "strongly indicates" in text.lower()
    
    def test_medium_probability_uses_moderate_language(self):
        """Test that medium probability uses moderate uncertainty language."""
        text = generate_uncertainty_text(
            bias_direction=BiasDirection.BULLISH,
            bias_probability=60,
            internal_action="BUY"
        )
        
        assert "suggests" in text.lower() or "moderately" in text.lower()
    
    def test_low_probability_uses_weak_language(self):
        """Test that low probability uses weaker uncertainty language."""
        text = generate_uncertainty_text(
            bias_direction=BiasDirection.NEUTRAL,
            bias_probability=30,
            internal_action="HOLD"
        )
        
        assert "slight" in text.lower() or "weak" in text.lower()
    
    def test_no_deterministic_terms(self):
        """Test that no deterministic terms are used."""
        for prob in [20, 50, 80]:
            for bias in [BiasDirection.BULLISH, BiasDirection.BEARISH, BiasDirection.NEUTRAL]:
                text = generate_uncertainty_text(
                    bias_direction=bias,
                    bias_probability=prob,
                    internal_action="BUY"
                )
                
                # Verify no deterministic language
                assert "buy" not in text.lower()
                assert "sell" not in text.lower()
                assert "hold" not in text.lower()


class TestSingletonInstance:
    """Tests for singleton bias calculator."""
    
    def test_get_bias_calculator_returns_same_instance(self):
        """Test that get_bias_calculator returns singleton."""
        import app.services.probabilistic_bias as pb
        pb._calculator_instance = None
        
        calc1 = get_bias_calculator()
        calc2 = get_bias_calculator()
        
        assert calc1 is calc2


class TestEdgeCases:
    """Tests for edge cases."""
    
    @pytest.fixture
    def calculator(self):
        return ProbabilisticBiasCalculator()
    
    def test_empty_signals_list(self, calculator):
        """Test handling of empty signals list."""
        result = calculator.calculate_bias(
            internal_action="HOLD",
            signals=[],
            recommendation_confidence=50.0,
            data_confidence_score=0.9,
            is_suppressed=False
        )
        
        assert isinstance(result, BiasSignal)
        assert result.bias_probability is not None
        assert 0 <= result.bias_probability <= 100
    
    def test_zero_recommendation_confidence(self, calculator):
        """Test handling of zero recommendation confidence."""
        signals = [{"direction": "bullish", "strength": 0.5}]
        result = calculator.calculate_bias(
            internal_action="BUY",
            signals=signals,
            recommendation_confidence=0.0,
            data_confidence_score=0.9,
            is_suppressed=False
        )
        
        assert result.bias_probability >= 0
    
    def test_extreme_signal_strengths(self, calculator):
        """Test handling of extreme signal strengths."""
        signals = [
            {"direction": "bullish", "strength": 1.0},
            {"direction": "bullish", "strength": 1.0}
        ]
        
        result = calculator.calculate_bias(
            internal_action="STRONG_BUY",
            signals=signals,
            recommendation_confidence=100.0,
            data_confidence_score=1.0,
            is_suppressed=False
        )
        
        assert result.bias_probability <= 100
    
    def test_unknown_action_handled(self, calculator):
        """Test handling of unknown action types."""
        signals = [{"direction": "neutral", "strength": 0.0}]
        result = calculator.calculate_bias(
            internal_action="UNKNOWN_ACTION",
            signals=signals,
            recommendation_confidence=50.0,
            data_confidence_score=0.9,
            is_suppressed=False
        )
        
        assert result.bias_direction == BiasDirection.NEUTRAL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
