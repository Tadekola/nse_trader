"""
Probabilistic Bias Module for NSE Trader.

Converts deterministic recommendation actions (BUY/HOLD/SELL) into
probabilistic directional bias signals with uncertainty quantification.

This module provides:
- Bias direction mapping (bullish/neutral/bearish)
- Bias probability computation based on indicator agreement and data confidence
- Market regime integration for confidence adjustments
- Uncertainty-aware language generation

Integrates with MarketRegimeEngine to adjust probabilities based on
regime compatibility (e.g., suppress bullish in mean-reverting regimes).
"""
import logging
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class BiasDirection(str, Enum):
    """Directional bias for probabilistic signals."""
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"


# Mapping from internal deterministic actions to probabilistic bias
ACTION_TO_BIAS_MAP = {
    "STRONG_BUY": BiasDirection.BULLISH,
    "BUY": BiasDirection.BULLISH,
    "HOLD": BiasDirection.NEUTRAL,
    "SELL": BiasDirection.BEARISH,
    "STRONG_SELL": BiasDirection.BEARISH,
    "AVOID": BiasDirection.NEUTRAL,  # AVOID maps to neutral with low probability
}

# Base probability ranges for each action type
ACTION_BASE_PROBABILITY = {
    "STRONG_BUY": (75, 95),
    "BUY": (55, 75),
    "HOLD": (40, 60),
    "SELL": (55, 75),
    "STRONG_SELL": (75, 95),
    "AVOID": (30, 50),
}


@dataclass
class BiasSignal:
    """
    Probabilistic bias signal for a recommendation.
    
    Attributes:
        bias_direction: bullish | neutral | bearish
        bias_probability: Probability strength (0-100), None if suppressed
        indicator_agreement: Proportion of indicators agreeing with bias (0.0-1.0)
        signal_magnitude: Average magnitude of aligned signals (0.0-1.0)
        data_confidence_factor: Adjustment factor from data confidence (0.0-1.0)
        regime_adjustment_factor: Adjustment from market regime (0.0-1.5)
        pre_regime_probability: Probability before regime adjustment
        reasoning: Uncertainty-aware explanation text
        is_suppressed: Whether this signal is suppressed
        suppression_reason: Reason for suppression if applicable
        regime_metadata: Market regime information attached to signal
    """
    bias_direction: BiasDirection
    bias_probability: Optional[int]  # None when suppressed
    indicator_agreement: float
    signal_magnitude: float
    data_confidence_factor: float
    reasoning: str
    is_suppressed: bool = False
    suppression_reason: Optional[str] = None
    regime_adjustment_factor: float = 1.0
    pre_regime_probability: Optional[int] = None
    regime_metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        result = {
            "bias_direction": self.bias_direction.value,
            "indicator_agreement": round(self.indicator_agreement, 3),
            "signal_magnitude": round(self.signal_magnitude, 3),
            "data_confidence_factor": round(self.data_confidence_factor, 3),
            "regime_adjustment_factor": round(self.regime_adjustment_factor, 3),
            "reasoning": self.reasoning,
            "is_suppressed": self.is_suppressed,
            "timestamp": self.timestamp.isoformat()
        }
        
        # Only include bias_probability for ACTIVE (non-suppressed) signals
        if not self.is_suppressed and self.bias_probability is not None:
            result["bias_probability"] = self.bias_probability
            if self.pre_regime_probability is not None:
                result["pre_regime_probability"] = self.pre_regime_probability
        
        # Include suppression_reason only when suppressed
        if self.is_suppressed:
            result["suppression_reason"] = self.suppression_reason
        
        # Include regime metadata if available
        if self.regime_metadata:
            result["market_regime"] = self.regime_metadata
        
        return result


class ProbabilisticBiasCalculator:
    """
    Calculates probabilistic bias signals from recommendation data.
    
    Computes bias_probability based on:
    - Indicator agreement strength (how many indicators align)
    - Indicator signal magnitude (how strong the signals are)
    - Data confidence score (from confidence scoring layer)
    
    Applies penalties when data confidence < 0.9.
    """
    
    # Confidence threshold below which probability is penalized
    CONFIDENCE_PENALTY_THRESHOLD = 0.9
    
    # Maximum penalty factor for low confidence (reduces probability by up to this factor)
    MAX_CONFIDENCE_PENALTY = 0.25
    
    def __init__(self):
        pass
    
    def calculate_bias(
        self,
        internal_action: str,
        signals: List[Dict[str, Any]],
        recommendation_confidence: float,
        data_confidence_score: float,
        is_suppressed: bool = False,
        suppression_reason: Optional[str] = None
    ) -> BiasSignal:
        """
        Calculate probabilistic bias signal from recommendation components.
        
        Args:
            internal_action: Internal action (BUY, SELL, HOLD, etc.)
            signals: List of technical/fundamental signals with direction and strength
            recommendation_confidence: Engine confidence (0-100)
            data_confidence_score: Data quality confidence (0.0-1.0)
            is_suppressed: Whether recommendation is suppressed
            suppression_reason: Reason for suppression if applicable
        
        Returns:
            BiasSignal with probabilistic bias information
        """
        # Map action to bias direction
        bias_direction = self._map_action_to_bias(internal_action)
        
        # If suppressed, return signal without probability
        if is_suppressed:
            return BiasSignal(
                bias_direction=BiasDirection.NEUTRAL,  # Suppressed = no directional bias
                bias_probability=None,
                indicator_agreement=0.0,
                signal_magnitude=0.0,
                data_confidence_factor=data_confidence_score,
                reasoning=self._generate_suppressed_reasoning(suppression_reason),
                is_suppressed=True,
                suppression_reason=suppression_reason
            )
        
        # Calculate indicator agreement and magnitude
        indicator_agreement = self._calculate_indicator_agreement(signals, bias_direction)
        signal_magnitude = self._calculate_signal_magnitude(signals, bias_direction)
        
        # Calculate data confidence factor (penalty for low confidence)
        confidence_factor = self._calculate_confidence_factor(data_confidence_score)
        
        # Calculate final bias probability
        bias_probability = self._calculate_probability(
            internal_action=internal_action,
            indicator_agreement=indicator_agreement,
            signal_magnitude=signal_magnitude,
            recommendation_confidence=recommendation_confidence,
            confidence_factor=confidence_factor
        )
        
        # Generate uncertainty-aware reasoning
        reasoning = self._generate_reasoning(
            bias_direction=bias_direction,
            bias_probability=bias_probability,
            indicator_agreement=indicator_agreement,
            internal_action=internal_action
        )
        
        return BiasSignal(
            bias_direction=bias_direction,
            bias_probability=bias_probability,
            indicator_agreement=indicator_agreement,
            signal_magnitude=signal_magnitude,
            data_confidence_factor=confidence_factor,
            reasoning=reasoning,
            is_suppressed=False
        )
    
    def _map_action_to_bias(self, action: str) -> BiasDirection:
        """Map internal action to bias direction."""
        action_upper = action.upper()
        return ACTION_TO_BIAS_MAP.get(action_upper, BiasDirection.NEUTRAL)
    
    def _calculate_indicator_agreement(
        self,
        signals: List[Dict[str, Any]],
        bias_direction: BiasDirection
    ) -> float:
        """
        Calculate proportion of indicators agreeing with the bias direction.
        
        Returns:
            Agreement ratio (0.0-1.0)
        """
        if not signals:
            return 0.5  # Neutral agreement when no signals
        
        aligned_count = 0
        total_count = len(signals)
        
        for signal in signals:
            signal_direction = signal.get("direction", "").lower()
            signal_strength = signal.get("strength", 0)
            
            # Determine if signal aligns with bias
            if bias_direction == BiasDirection.BULLISH:
                if signal_direction == "bullish" or signal_strength > 0.2:
                    aligned_count += 1
            elif bias_direction == BiasDirection.BEARISH:
                if signal_direction == "bearish" or signal_strength < -0.2:
                    aligned_count += 1
            else:  # NEUTRAL
                if signal_direction == "neutral" or abs(signal_strength) <= 0.2:
                    aligned_count += 1
        
        return aligned_count / total_count if total_count > 0 else 0.5
    
    def _calculate_signal_magnitude(
        self,
        signals: List[Dict[str, Any]],
        bias_direction: BiasDirection
    ) -> float:
        """
        Calculate average magnitude of signals aligned with bias direction.
        
        Returns:
            Average magnitude (0.0-1.0)
        """
        if not signals:
            return 0.0
        
        aligned_magnitudes = []
        
        for signal in signals:
            strength = signal.get("strength", 0)
            
            # For bullish bias, consider positive strengths
            if bias_direction == BiasDirection.BULLISH and strength > 0:
                aligned_magnitudes.append(abs(strength))
            # For bearish bias, consider negative strengths
            elif bias_direction == BiasDirection.BEARISH and strength < 0:
                aligned_magnitudes.append(abs(strength))
            # For neutral, consider signals near zero
            elif bias_direction == BiasDirection.NEUTRAL:
                if abs(strength) <= 0.3:
                    aligned_magnitudes.append(1.0 - abs(strength))  # Higher magnitude for weaker signals
        
        if not aligned_magnitudes:
            return 0.3  # Default moderate magnitude
        
        return min(1.0, sum(aligned_magnitudes) / len(aligned_magnitudes))
    
    def _calculate_confidence_factor(self, data_confidence: float) -> float:
        """
        Calculate confidence adjustment factor.
        
        Penalizes probability when data confidence < 0.9.
        
        Returns:
            Factor between (1 - MAX_CONFIDENCE_PENALTY) and 1.0
        """
        if data_confidence >= self.CONFIDENCE_PENALTY_THRESHOLD:
            return 1.0
        
        # Linear penalty below threshold
        # At confidence = 0, factor = (1 - MAX_CONFIDENCE_PENALTY)
        # At confidence = 0.9, factor = 1.0
        shortfall = self.CONFIDENCE_PENALTY_THRESHOLD - data_confidence
        penalty = (shortfall / self.CONFIDENCE_PENALTY_THRESHOLD) * self.MAX_CONFIDENCE_PENALTY
        
        return max(1.0 - self.MAX_CONFIDENCE_PENALTY, 1.0 - penalty)
    
    def _calculate_probability(
        self,
        internal_action: str,
        indicator_agreement: float,
        signal_magnitude: float,
        recommendation_confidence: float,
        confidence_factor: float
    ) -> int:
        """
        Calculate final bias probability (0-100).
        
        Combines:
        - Base probability range from action type
        - Indicator agreement adjustment
        - Signal magnitude adjustment
        - Recommendation confidence scaling
        - Data confidence penalty
        
        Returns:
            Probability as integer 0-100
        """
        action_upper = internal_action.upper()
        base_range = ACTION_BASE_PROBABILITY.get(action_upper, (40, 60))
        base_low, base_high = base_range
        
        # Start with midpoint of base range
        base_prob = (base_low + base_high) / 2
        range_width = base_high - base_low
        
        # Adjust based on indicator agreement (±half range)
        agreement_adjustment = (indicator_agreement - 0.5) * range_width
        
        # Adjust based on signal magnitude (±quarter range)
        magnitude_adjustment = (signal_magnitude - 0.5) * (range_width / 2)
        
        # Scale by recommendation confidence (normalized to 0-1)
        confidence_scale = recommendation_confidence / 100.0
        
        # Combine adjustments
        raw_probability = base_prob + (agreement_adjustment + magnitude_adjustment) * confidence_scale
        
        # Apply data confidence penalty
        adjusted_probability = raw_probability * confidence_factor
        
        # Clamp to 0-100 range
        final_probability = max(0, min(100, int(round(adjusted_probability))))
        
        return final_probability
    
    def _generate_reasoning(
        self,
        bias_direction: BiasDirection,
        bias_probability: int,
        indicator_agreement: float,
        internal_action: str
    ) -> str:
        """
        Generate uncertainty-aware reasoning text.
        
        Uses probabilistic language instead of deterministic recommendations.
        """
        # Probability strength descriptors
        if bias_probability >= 80:
            strength = "strongly suggests"
            confidence_desc = "high confidence"
        elif bias_probability >= 65:
            strength = "suggests"
            confidence_desc = "moderate confidence"
        elif bias_probability >= 50:
            strength = "leans toward"
            confidence_desc = "modest confidence"
        else:
            strength = "shows slight indication of"
            confidence_desc = "low confidence"
        
        # Bias direction text
        direction_text = {
            BiasDirection.BULLISH: "bullish bias",
            BiasDirection.NEUTRAL: "neutral stance",
            BiasDirection.BEARISH: "bearish bias"
        }
        
        # Agreement descriptor
        if indicator_agreement >= 0.75:
            agreement_text = "Strong indicator consensus"
        elif indicator_agreement >= 0.5:
            agreement_text = "Moderate indicator agreement"
        else:
            agreement_text = "Mixed indicator signals"
        
        # Construct reasoning
        reasoning = (
            f"Technical analysis {strength} a {direction_text[bias_direction]} "
            f"with {confidence_desc} ({bias_probability}% probability). "
            f"{agreement_text} ({indicator_agreement:.0%} aligned). "
            f"This assessment reflects current market conditions and may change."
        )
        
        return reasoning
    
    def _generate_suppressed_reasoning(self, suppression_reason: Optional[str]) -> str:
        """Generate reasoning for suppressed signals."""
        base = "Signal analysis is currently suppressed due to insufficient data quality."
        if suppression_reason:
            return f"{base} Reason: {suppression_reason}"
        return base
    
    def apply_regime_adjustment(
        self,
        bias_signal: BiasSignal,
        regime_analysis: Any  # SessionRegimeAnalysis from market_regime_engine
    ) -> BiasSignal:
        """
        Apply market regime adjustments to a bias signal.
        
        SUPPRESSED logic remains authoritative - if already suppressed,
        no adjustment is made and original signal is returned.
        
        Args:
            bias_signal: The calculated bias signal
            regime_analysis: SessionRegimeAnalysis from MarketRegimeEngine
        
        Returns:
            BiasSignal with regime-adjusted probability and metadata
        """
        # SUPPRESSED is authoritative - don't modify
        if bias_signal.is_suppressed:
            # Just attach regime metadata for context
            bias_signal.regime_metadata = {
                "regime": regime_analysis.regime.value,
                "regime_confidence": regime_analysis.confidence,
                "note": "Signal suppressed before regime adjustment"
            }
            return bias_signal
        
        # Get regime compatibility rules
        compatibility = regime_analysis.bias_compatibility
        bias_dir = bias_signal.bias_direction.value
        
        # Check for regime-based suppression
        if bias_dir == "bullish" and compatibility.suppress_bullish:
            return BiasSignal(
                bias_direction=BiasDirection.NEUTRAL,
                bias_probability=None,
                indicator_agreement=bias_signal.indicator_agreement,
                signal_magnitude=bias_signal.signal_magnitude,
                data_confidence_factor=bias_signal.data_confidence_factor,
                reasoning=(
                    f"Bullish bias suppressed due to {regime_analysis.regime.value} regime. "
                    f"Original probability was {bias_signal.bias_probability}%."
                ),
                is_suppressed=True,
                suppression_reason=(
                    f"Regime incompatibility: {regime_analysis.regime.value} regime "
                    f"suppresses bullish signals"
                ),
                regime_adjustment_factor=0.0,
                pre_regime_probability=bias_signal.bias_probability,
                regime_metadata={
                    "regime": regime_analysis.regime.value,
                    "regime_confidence": regime_analysis.confidence,
                    "suppressed_by_regime": True
                }
            )
        
        if bias_dir == "bearish" and compatibility.suppress_bearish:
            return BiasSignal(
                bias_direction=BiasDirection.NEUTRAL,
                bias_probability=None,
                indicator_agreement=bias_signal.indicator_agreement,
                signal_magnitude=bias_signal.signal_magnitude,
                data_confidence_factor=bias_signal.data_confidence_factor,
                reasoning=(
                    f"Bearish bias suppressed due to {regime_analysis.regime.value} regime. "
                    f"Original probability was {bias_signal.bias_probability}%."
                ),
                is_suppressed=True,
                suppression_reason=(
                    f"Regime incompatibility: {regime_analysis.regime.value} regime "
                    f"suppresses bearish signals"
                ),
                regime_adjustment_factor=0.0,
                pre_regime_probability=bias_signal.bias_probability,
                regime_metadata={
                    "regime": regime_analysis.regime.value,
                    "regime_confidence": regime_analysis.confidence,
                    "suppressed_by_regime": True
                }
            )
        
        # Get appropriate multiplier based on bias direction
        if bias_dir == "bullish":
            multiplier = compatibility.bullish_multiplier
        elif bias_dir == "bearish":
            multiplier = compatibility.bearish_multiplier
        else:
            multiplier = compatibility.neutral_multiplier
        
        # Apply multiplier, confidence penalty, and regime confidence multiplier
        pre_regime_prob = bias_signal.bias_probability
        adjusted = pre_regime_prob * multiplier
        adjusted = adjusted * (1 - compatibility.confidence_penalty)
        adjusted = adjusted * regime_analysis.confidence_multiplier
        
        # Calculate total adjustment factor
        total_adjustment = multiplier * (1 - compatibility.confidence_penalty) * regime_analysis.confidence_multiplier
        
        # Clamp to valid range
        adjusted_prob = max(0, min(100, int(round(adjusted))))
        
        # Update reasoning to reflect regime adjustment
        regime_text = regime_analysis.regime.value.replace("_", " ")
        adjustment_desc = "increased" if total_adjustment > 1 else "reduced" if total_adjustment < 1 else "unchanged"
        
        updated_reasoning = (
            f"{bias_signal.reasoning} "
            f"[Regime adjustment: {regime_text} market {adjustment_desc} probability "
            f"from {pre_regime_prob}% to {adjusted_prob}%]"
        )
        
        return BiasSignal(
            bias_direction=bias_signal.bias_direction,
            bias_probability=adjusted_prob,
            indicator_agreement=bias_signal.indicator_agreement,
            signal_magnitude=bias_signal.signal_magnitude,
            data_confidence_factor=bias_signal.data_confidence_factor,
            reasoning=updated_reasoning,
            is_suppressed=False,
            suppression_reason=None,
            regime_adjustment_factor=total_adjustment,
            pre_regime_probability=pre_regime_prob,
            regime_metadata={
                "regime": regime_analysis.regime.value,
                "regime_confidence": regime_analysis.confidence,
                "trend_direction": regime_analysis.trend_direction.value,
                "confidence_multiplier": regime_analysis.confidence_multiplier,
                "bias_multiplier_applied": multiplier,
                "warnings": regime_analysis.warnings
            }
        )


def convert_action_to_bias_label(action: str) -> str:
    """
    Convert internal action to external bias label.
    
    Mapping:
    - BUY/STRONG_BUY → "Bullish Bias"
    - HOLD → "Neutral Bias"
    - SELL/STRONG_SELL → "Bearish Bias"
    - AVOID → "Neutral Bias"
    
    Args:
        action: Internal action string
    
    Returns:
        Human-readable bias label
    """
    bias = ACTION_TO_BIAS_MAP.get(action.upper(), BiasDirection.NEUTRAL)
    
    label_map = {
        BiasDirection.BULLISH: "Bullish Bias",
        BiasDirection.NEUTRAL: "Neutral Bias",
        BiasDirection.BEARISH: "Bearish Bias"
    }
    
    return label_map[bias]


def generate_uncertainty_text(
    bias_direction: BiasDirection,
    bias_probability: int,
    internal_action: str
) -> str:
    """
    Generate uncertainty-aware text for explanations.
    
    Replaces deterministic language like "strong buy" with
    probabilistic language like "suggests bullish bias".
    
    Args:
        bias_direction: The calculated bias direction
        bias_probability: Probability strength (0-100)
        internal_action: Original internal action
    
    Returns:
        Uncertainty-aware description text
    """
    # Probability-based qualifier
    if bias_probability >= 80:
        qualifier = "strongly indicates"
    elif bias_probability >= 65:
        qualifier = "suggests"
    elif bias_probability >= 50:
        qualifier = "moderately suggests"
    elif bias_probability >= 35:
        qualifier = "shows slight"
    else:
        qualifier = "weakly indicates"
    
    direction_phrases = {
        BiasDirection.BULLISH: "bullish bias with potential upside",
        BiasDirection.NEUTRAL: "neutral positioning with no clear directional edge",
        BiasDirection.BEARISH: "bearish bias with potential downside"
    }
    
    return f"Analysis {qualifier} {direction_phrases[bias_direction]}"


# Singleton instance
_calculator_instance: Optional[ProbabilisticBiasCalculator] = None


def get_bias_calculator() -> ProbabilisticBiasCalculator:
    """Get singleton bias calculator instance."""
    global _calculator_instance
    if _calculator_instance is None:
        _calculator_instance = ProbabilisticBiasCalculator()
    return _calculator_instance
