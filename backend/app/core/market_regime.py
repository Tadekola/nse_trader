"""
Market Regime Detection for NSE Trader.

Detects overall market conditions to adjust signal interpretation:
- Bull market: Favor trend-following, increase exposure
- Bear market: Favor defensive, reduce exposure
- Range-bound: Favor mean-reversion, tighter stops
- High volatility: Reduce position sizes
- Low liquidity: Widen entry expectations
- Crisis: Reduce all signals to HOLD
"""
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np

from app.indicators.base import calculate_sma, calculate_atr


class MarketRegime(str, Enum):
    """Market regime classification."""
    BULL = "bull"
    BEAR = "bear"
    RANGE_BOUND = "range_bound"
    HIGH_VOLATILITY = "high_volatility"
    LOW_LIQUIDITY = "low_liquidity"
    CRISIS = "crisis"


class MarketTrend(str, Enum):
    """Market trend direction."""
    STRONGLY_BULLISH = "strongly_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONGLY_BEARISH = "strongly_bearish"


@dataclass
class RegimeAnalysis:
    """Complete market regime analysis."""
    regime: MarketRegime
    trend: MarketTrend
    confidence: float  # 0-1
    duration_days: int
    
    # Key metrics
    asi_vs_sma_50: float
    asi_vs_sma_200: float
    volatility_percentile: float
    breadth_ratio: float  # Advancing / (Advancing + Declining)
    volume_ratio: float   # Current volume vs average
    
    # Recommendations
    recommended_strategy: str
    position_size_modifier: float  # 0.5 to 1.5
    risk_adjustment: str
    sectors_to_favor: List[str]
    sectors_to_avoid: List[str]
    
    # Warning flags
    warnings: List[str]
    
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class MarketRegimeDetector:
    """
    Detects current market regime and provides regime-aware guidance.
    
    Uses ASI (All-Share Index) data and market breadth to determine regime.
    """
    
    def __init__(self):
        self._regime_history: List[Tuple[datetime, MarketRegime]] = []
        self._current_regime: Optional[MarketRegime] = None
        self._regime_start_date: Optional[datetime] = None
    
    def detect(
        self,
        asi_data: pd.DataFrame,
        breadth_data: Optional[Dict] = None,
        volume_data: Optional[Dict] = None
    ) -> RegimeAnalysis:
        """
        Detect current market regime.
        
        Args:
            asi_data: DataFrame with ASI OHLCV data
            breadth_data: Dict with 'advancing', 'declining', 'unchanged' counts
            volume_data: Dict with 'current_volume', 'avg_volume'
        
        Returns:
            RegimeAnalysis with complete market assessment
        """
        # Calculate ASI metrics
        asi_close = asi_data['Close']
        sma_50 = calculate_sma(asi_close, 50).iloc[-1]
        sma_200 = calculate_sma(asi_close, 200).iloc[-1] if len(asi_close) >= 200 else sma_50
        current_price = asi_close.iloc[-1]
        
        asi_vs_sma_50 = ((current_price - sma_50) / sma_50) * 100
        asi_vs_sma_200 = ((current_price - sma_200) / sma_200) * 100
        
        # Calculate volatility
        returns = asi_close.pct_change().dropna()
        current_vol = returns.iloc[-20:].std() * np.sqrt(252) if len(returns) >= 20 else 0.2
        historical_vol = returns.std() * np.sqrt(252) if len(returns) > 0 else 0.2
        volatility_percentile = self._calculate_volatility_percentile(returns)
        
        # Calculate breadth ratio
        breadth_ratio = 0.5  # Default neutral
        if breadth_data:
            total = breadth_data.get('advancing', 0) + breadth_data.get('declining', 0)
            if total > 0:
                breadth_ratio = breadth_data.get('advancing', 0) / total
        
        # Calculate volume ratio
        volume_ratio = 1.0  # Default normal
        if volume_data:
            avg_vol = volume_data.get('avg_volume', 1)
            if avg_vol > 0:
                volume_ratio = volume_data.get('current_volume', avg_vol) / avg_vol
        
        # Detect regime
        regime = self._determine_regime(
            asi_vs_sma_50, asi_vs_sma_200, volatility_percentile,
            breadth_ratio, volume_ratio
        )
        
        # Detect trend
        trend = self._determine_trend(asi_vs_sma_50, asi_vs_sma_200, breadth_ratio)
        
        # Calculate confidence
        confidence = self._calculate_confidence(
            regime, asi_vs_sma_50, volatility_percentile, breadth_ratio
        )
        
        # Track regime duration
        duration_days = self._update_regime_history(regime)
        
        # Generate recommendations
        strategy, position_mod, risk_adj = self._get_strategy_recommendations(regime, trend)
        sectors_favor, sectors_avoid = self._get_sector_recommendations(regime, trend)
        warnings = self._generate_warnings(
            regime, volatility_percentile, breadth_ratio, volume_ratio
        )
        
        return RegimeAnalysis(
            regime=regime,
            trend=trend,
            confidence=confidence,
            duration_days=duration_days,
            asi_vs_sma_50=asi_vs_sma_50,
            asi_vs_sma_200=asi_vs_sma_200,
            volatility_percentile=volatility_percentile,
            breadth_ratio=breadth_ratio,
            volume_ratio=volume_ratio,
            recommended_strategy=strategy,
            position_size_modifier=position_mod,
            risk_adjustment=risk_adj,
            sectors_to_favor=sectors_favor,
            sectors_to_avoid=sectors_avoid,
            warnings=warnings
        )
    
    def _determine_regime(
        self,
        asi_vs_50: float,
        asi_vs_200: float,
        vol_pct: float,
        breadth: float,
        volume: float
    ) -> MarketRegime:
        """Determine market regime based on multiple factors."""
        
        # Crisis: Extreme volatility or severe breadth deterioration
        if vol_pct > 90 and breadth < 0.3:
            return MarketRegime.CRISIS
        
        # Low liquidity: Very low volume
        if volume < 0.5:
            return MarketRegime.LOW_LIQUIDITY
        
        # High volatility: Elevated volatility regardless of direction
        if vol_pct > 75:
            return MarketRegime.HIGH_VOLATILITY
        
        # Bull: Above both SMAs with positive breadth
        if asi_vs_50 > 2 and asi_vs_200 > 0 and breadth > 0.55:
            return MarketRegime.BULL
        
        # Bear: Below both SMAs with negative breadth
        if asi_vs_50 < -2 and asi_vs_200 < 0 and breadth < 0.45:
            return MarketRegime.BEAR
        
        # Default: Range-bound
        return MarketRegime.RANGE_BOUND
    
    def _determine_trend(
        self, asi_vs_50: float, asi_vs_200: float, breadth: float
    ) -> MarketTrend:
        """Determine market trend direction and strength."""
        
        # Strongly bullish: Far above SMAs with strong breadth
        if asi_vs_50 > 5 and asi_vs_200 > 10 and breadth > 0.65:
            return MarketTrend.STRONGLY_BULLISH
        
        # Bullish: Above SMAs
        if asi_vs_50 > 0 and asi_vs_200 > 0:
            return MarketTrend.BULLISH
        
        # Strongly bearish: Far below SMAs with weak breadth
        if asi_vs_50 < -5 and asi_vs_200 < -10 and breadth < 0.35:
            return MarketTrend.STRONGLY_BEARISH
        
        # Bearish: Below SMAs
        if asi_vs_50 < 0 and asi_vs_200 < 0:
            return MarketTrend.BEARISH
        
        return MarketTrend.NEUTRAL
    
    def _calculate_volatility_percentile(self, returns: pd.Series) -> float:
        """Calculate where current volatility ranks historically."""
        if len(returns) < 60:
            return 50.0  # Not enough data
        
        # Calculate rolling 20-day volatility
        rolling_vol = returns.rolling(20).std()
        current_vol = rolling_vol.iloc[-1]
        
        # Calculate percentile
        percentile = (rolling_vol < current_vol).sum() / len(rolling_vol) * 100
        return float(percentile)
    
    def _calculate_confidence(
        self, regime: MarketRegime, asi_vs_50: float,
        vol_pct: float, breadth: float
    ) -> float:
        """Calculate confidence in regime classification."""
        confidence = 0.5  # Base confidence
        
        # Clear directional signals increase confidence
        if regime in [MarketRegime.BULL, MarketRegime.BEAR]:
            if abs(asi_vs_50) > 5:
                confidence += 0.2
            if abs(breadth - 0.5) > 0.15:
                confidence += 0.1
        
        # Clear volatility signals
        if regime == MarketRegime.HIGH_VOLATILITY and vol_pct > 85:
            confidence += 0.2
        
        # Crisis with multiple confirming signals
        if regime == MarketRegime.CRISIS:
            confidence = min(0.9, confidence + 0.3)
        
        return min(1.0, confidence)
    
    def _update_regime_history(self, regime: MarketRegime) -> int:
        """Update regime history and return duration in days."""
        now = datetime.utcnow()
        
        if self._current_regime != regime:
            self._current_regime = regime
            self._regime_start_date = now
            self._regime_history.append((now, regime))
            return 1
        
        if self._regime_start_date:
            return (now - self._regime_start_date).days + 1
        return 1
    
    def _get_strategy_recommendations(
        self, regime: MarketRegime, trend: MarketTrend
    ) -> Tuple[str, float, str]:
        """Get strategy, position size modifier, and risk adjustment."""
        
        strategies = {
            MarketRegime.BULL: (
                "Trend-following strategies favored. Look for pullbacks to enter long positions.",
                1.2,  # Increase position sizes
                "Normal stops, can give trades more room"
            ),
            MarketRegime.BEAR: (
                "Defensive strategies. Reduce exposure, focus on quality/dividend stocks.",
                0.7,  # Reduce position sizes
                "Tighter stops, quick to cut losses"
            ),
            MarketRegime.RANGE_BOUND: (
                "Mean-reversion strategies. Buy at support, sell at resistance.",
                1.0,  # Normal position sizes
                "Tight stops near range boundaries"
            ),
            MarketRegime.HIGH_VOLATILITY: (
                "Reduce trading frequency. Smaller positions, wider stops.",
                0.6,  # Smaller positions
                "Wide stops to avoid whipsaws, smaller targets"
            ),
            MarketRegime.LOW_LIQUIDITY: (
                "Limited trading recommended. Focus on liquid large-caps only.",
                0.5,  # Small positions
                "Very wide stops, patient entries"
            ),
            MarketRegime.CRISIS: (
                "Capital preservation mode. Reduce equity exposure, hold cash.",
                0.3,  # Minimal positions
                "No new positions, protect existing"
            )
        }
        
        return strategies.get(regime, ("Hold current positions", 1.0, "Normal risk management"))
    
    def _get_sector_recommendations(
        self, regime: MarketRegime, trend: MarketTrend
    ) -> Tuple[List[str], List[str]]:
        """Get sector rotation recommendations."""
        
        if regime == MarketRegime.BULL:
            return (
                ["Financial Services", "Consumer Goods", "Industrial Goods"],
                ["Defensive sectors"]
            )
        elif regime == MarketRegime.BEAR:
            return (
                ["Consumer Goods (staples)", "ICT"],
                ["Financial Services", "Industrial Goods", "Oil & Gas"]
            )
        elif regime == MarketRegime.HIGH_VOLATILITY:
            return (
                ["Large-cap liquid stocks only"],
                ["Small-caps", "Low-liquidity stocks"]
            )
        elif regime == MarketRegime.CRISIS:
            return (
                ["Cash", "Government bonds"],
                ["All equity sectors"]
            )
        
        return ([], [])  # No strong preferences for range-bound
    
    def _generate_warnings(
        self, regime: MarketRegime, vol_pct: float,
        breadth: float, volume: float
    ) -> List[str]:
        """Generate warning messages for current conditions."""
        warnings = []
        
        if regime == MarketRegime.CRISIS:
            warnings.append("⚠️ MARKET IN CRISIS MODE - Extreme caution advised")
        
        if vol_pct > 80:
            warnings.append(f"⚠️ Volatility at {vol_pct:.0f}th percentile - Reduce position sizes")
        
        if breadth < 0.35:
            warnings.append("⚠️ Poor market breadth - Most stocks declining")
        elif breadth > 0.75:
            warnings.append("⚠️ Extreme bullish breadth - Market may be overextended")
        
        if volume < 0.5:
            warnings.append("⚠️ Very low market volume - Liquidity concerns")
        
        return warnings
    
    def get_regime_adjustment(
        self, raw_signal_strength: float, regime: MarketRegime
    ) -> float:
        """
        Adjust a raw signal strength based on market regime.
        
        Args:
            raw_signal_strength: Original signal strength (-1 to 1)
            regime: Current market regime
        
        Returns:
            Adjusted signal strength
        """
        adjustments = {
            MarketRegime.BULL: 1.1,      # Slightly amplify bullish signals
            MarketRegime.BEAR: 0.8,      # Dampen signals
            MarketRegime.RANGE_BOUND: 1.0,
            MarketRegime.HIGH_VOLATILITY: 0.7,  # Reduce all signals
            MarketRegime.LOW_LIQUIDITY: 0.6,    # Reduce signals
            MarketRegime.CRISIS: 0.3,           # Drastically reduce
        }
        
        modifier = adjustments.get(regime, 1.0)
        adjusted = raw_signal_strength * modifier
        
        # Cap at reasonable bounds
        return max(-1.0, min(1.0, adjusted))
    
    def should_trade(self, regime: MarketRegime, liquidity_score: float) -> Tuple[bool, str]:
        """
        Determine if trading is advisable given regime and liquidity.
        
        Returns:
            Tuple of (should_trade: bool, reason: str)
        """
        if regime == MarketRegime.CRISIS:
            return False, "Market in crisis mode - avoid new positions"
        
        if liquidity_score < 0.3:
            return False, "Insufficient liquidity for safe trading"
        
        if regime == MarketRegime.LOW_LIQUIDITY and liquidity_score < 0.5:
            return False, "Low market liquidity combined with poor stock liquidity"
        
        return True, "Trading conditions acceptable"
