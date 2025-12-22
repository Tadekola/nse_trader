"""
Composite indicators that combine multiple signals.
"""
from typing import Optional, List, Dict
import pandas as pd
from app.indicators.base import BaseIndicator, IndicatorResult, SignalDirection
from app.indicators.trend import SMAIndicator, EMAIndicator, MACDIndicator, GoldenDeathCrossIndicator
from app.indicators.momentum import RSIIndicator, StochasticIndicator, ADXIndicator
from app.indicators.volatility import ATRIndicator, BollingerBandsIndicator
from app.indicators.volume import OBVIndicator, VolumeRatioIndicator, LiquidityScoreIndicator


class CompositeIndicator(BaseIndicator):
    """
    Composite indicator that aggregates signals from multiple indicators.
    
    Provides:
    - Overall signal direction
    - Confidence based on indicator agreement
    - Weighted scoring based on indicator importance
    """
    
    def __init__(self):
        super().__init__("Composite")
        
        # Initialize all indicators with their weights
        self.indicators = {
            # Trend indicators (weight: 0.25 total)
            'sma_50': (SMAIndicator(50), 0.08),
            'sma_200': (SMAIndicator(200), 0.08),
            'macd': (MACDIndicator(), 0.09),
            
            # Momentum indicators (weight: 0.30 total)
            'rsi': (RSIIndicator(14), 0.12),
            'stochastic': (StochasticIndicator(), 0.08),
            'adx': (ADXIndicator(), 0.10),
            
            # Volatility indicators (weight: 0.15 total)
            'bollinger': (BollingerBandsIndicator(), 0.10),
            'atr': (ATRIndicator(), 0.05),
            
            # Volume indicators (weight: 0.15 total)
            'obv': (OBVIndicator(), 0.08),
            'volume_ratio': (VolumeRatioIndicator(), 0.07),
            
            # Liquidity (weight: 0.15)
            'liquidity': (LiquidityScoreIndicator(), 0.15),
        }
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if df is None or df.empty or len(df) < 50:
            return None
        
        results = {}
        signals = []
        weighted_score = 0.0
        total_weight = 0.0
        
        # Calculate each indicator
        for name, (indicator, weight) in self.indicators.items():
            result = indicator.calculate(df)
            if result:
                results[name] = result
                signals.append(result)
                
                # Add to weighted score
                weighted_score += result.strength * weight
                total_weight += weight
        
        if not signals:
            return None
        
        # Normalize weighted score
        if total_weight > 0:
            weighted_score = weighted_score / total_weight
        
        # Count bullish/bearish/neutral signals
        bullish_count = sum(1 for s in signals if s.signal == SignalDirection.BULLISH)
        bearish_count = sum(1 for s in signals if s.signal == SignalDirection.BEARISH)
        neutral_count = sum(1 for s in signals if s.signal == SignalDirection.NEUTRAL)
        
        # Determine overall signal
        signal, strength = self._determine_signal(
            bullish_count, bearish_count, neutral_count, weighted_score
        )
        
        # Calculate confidence based on agreement
        confidence = self._calculate_confidence(
            bullish_count, bearish_count, neutral_count, len(signals)
        )
        
        return IndicatorResult(
            name=self.name,
            value=weighted_score,
            signal=signal,
            strength=strength,
            description=self._get_description(
                signal, confidence, bullish_count, bearish_count, neutral_count
            ),
            raw_values={
                'weighted_score': weighted_score,
                'bullish_count': bullish_count,
                'bearish_count': bearish_count,
                'neutral_count': neutral_count,
                'confidence': confidence,
                'individual_results': {k: v.to_dict() for k, v in results.items()}
            }
        )
    
    def get_signal(self, value: float) -> tuple[SignalDirection, float]:
        if value > 0.3:
            return SignalDirection.BULLISH, value
        elif value < -0.3:
            return SignalDirection.BEARISH, value
        return SignalDirection.NEUTRAL, value
    
    def _determine_signal(
        self, bullish: int, bearish: int, neutral: int, weighted: float
    ) -> tuple[SignalDirection, float]:
        """Determine overall signal from indicator consensus and weighted score."""
        
        # Strong consensus
        if bullish >= bearish + 3:
            return SignalDirection.BULLISH, min(weighted + 0.2, 1.0)
        if bearish >= bullish + 3:
            return SignalDirection.BEARISH, max(weighted - 0.2, -1.0)
        
        # Moderate consensus - use weighted score
        if weighted > 0.2:
            return SignalDirection.BULLISH, weighted
        elif weighted < -0.2:
            return SignalDirection.BEARISH, weighted
        
        return SignalDirection.NEUTRAL, weighted
    
    def _calculate_confidence(
        self, bullish: int, bearish: int, neutral: int, total: int
    ) -> float:
        """Calculate confidence 0-1 based on indicator agreement."""
        if total == 0:
            return 0.0
        
        # Calculate agreement ratio
        max_agreement = max(bullish, bearish, neutral)
        agreement_ratio = max_agreement / total
        
        # Adjust for conflict
        if bullish > 0 and bearish > 0:
            conflict_penalty = min(bullish, bearish) / total * 0.3
            agreement_ratio -= conflict_penalty
        
        return max(0.0, min(1.0, agreement_ratio))
    
    def _get_description(
        self, signal: SignalDirection, confidence: float,
        bullish: int, bearish: int, neutral: int
    ) -> str:
        total = bullish + bearish + neutral
        
        if signal == SignalDirection.BULLISH:
            return f"Composite signal BULLISH ({bullish}/{total} indicators agree, {confidence*100:.0f}% confidence)"
        elif signal == SignalDirection.BEARISH:
            return f"Composite signal BEARISH ({bearish}/{total} indicators agree, {confidence*100:.0f}% confidence)"
        return f"Composite signal NEUTRAL (mixed signals: {bullish} bullish, {bearish} bearish, {neutral} neutral)"
    
    def get_individual_results(self, df: pd.DataFrame) -> Dict[str, IndicatorResult]:
        """Get individual indicator results for detailed analysis."""
        results = {}
        for name, (indicator, _) in self.indicators.items():
            result = indicator.calculate(df)
            if result:
                results[name] = result
        return results


class TechnicalScore(BaseIndicator):
    """
    Simplified technical score for quick assessment.
    
    Returns a score from -100 to +100:
    - +100: Extremely bullish
    - +50 to +100: Bullish
    - -50 to +50: Neutral
    - -50 to -100: Bearish
    - -100: Extremely bearish
    """
    
    def __init__(self):
        super().__init__("Technical_Score")
        self.composite = CompositeIndicator()
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        composite_result = self.composite.calculate(df)
        if not composite_result:
            return None
        
        # Convert weighted score (-1 to +1) to -100 to +100
        score = composite_result.strength * 100
        
        signal, strength = self.get_signal(score)
        
        return IndicatorResult(
            name=self.name,
            value=score,
            signal=signal,
            strength=strength,
            description=self._get_description(score),
            raw_values={
                'score': score,
                'rating': self._get_rating(score),
                'composite_data': composite_result.raw_values
            }
        )
    
    def get_signal(self, score: float) -> tuple[SignalDirection, float]:
        if score >= 30:
            return SignalDirection.BULLISH, score / 100
        elif score <= -30:
            return SignalDirection.BEARISH, score / 100
        return SignalDirection.NEUTRAL, score / 100
    
    def _get_rating(self, score: float) -> str:
        if score >= 70:
            return "STRONG_BUY"
        elif score >= 30:
            return "BUY"
        elif score >= -30:
            return "HOLD"
        elif score >= -70:
            return "SELL"
        return "STRONG_SELL"
    
    def _get_description(self, score: float) -> str:
        rating = self._get_rating(score)
        
        descriptions = {
            "STRONG_BUY": f"Technical score {score:.0f}/100 - Strong buy signal with multiple confirming indicators",
            "BUY": f"Technical score {score:.0f}/100 - Buy signal with positive indicator alignment",
            "HOLD": f"Technical score {score:.0f}/100 - Neutral/Hold with mixed or weak signals",
            "SELL": f"Technical score {score:.0f}/100 - Sell signal with negative indicator alignment",
            "STRONG_SELL": f"Technical score {score:.0f}/100 - Strong sell signal with multiple confirming indicators"
        }
        
        return descriptions.get(rating, f"Technical score: {score:.0f}/100")
