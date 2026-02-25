"""
Market Regime Engine for NSE Trader.

Classifies market-wide conditions into exactly ONE dominant regime per session
and adjusts signal confidence based on regime compatibility.

Regimes:
- TRENDING: Strong directional movement in ASI
- MEAN_REVERTING: Range-bound, oscillating market
- HIGH_VOLATILITY: Elevated volatility across the market
- LOW_LIQUIDITY: Below-average trading volume
- NEWS_DRIVEN: Volume + volatility spike (event-driven)

Runs once per market session and caches the result.
"""
import logging
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class SessionRegime(str, Enum):
    """
    Market regime classification for the current session.
    Exactly ONE regime is active per session.
    """
    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    HIGH_VOLATILITY = "high_volatility"
    LOW_LIQUIDITY = "low_liquidity"
    NEWS_DRIVEN = "news_driven"


class TrendDirection(str, Enum):
    """Direction of trend in TRENDING regime."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NONE = "none"


@dataclass
class RegimeMetrics:
    """
    Market-wide metrics used for regime classification.
    
    Attributes:
        asi_trend_strength: Strength of ASI trend (-1 to 1, negative=bearish)
        asi_vs_sma20: ASI deviation from 20-day SMA (%)
        asi_vs_sma50: ASI deviation from 50-day SMA (%)
        volatility_current: Current 20-day annualized volatility
        volatility_baseline: 60-day baseline volatility
        volatility_ratio: Current / baseline ratio
        volume_current: Current session volume
        volume_baseline: 20-day average volume
        volume_ratio: Current / baseline ratio
        volume_spike: Whether volume > 2x baseline
        volatility_spike: Whether volatility > 1.5x baseline
    """
    asi_trend_strength: float
    asi_vs_sma20: float
    asi_vs_sma50: float
    volatility_current: float
    volatility_baseline: float
    volatility_ratio: float
    volume_current: float
    volume_baseline: float
    volume_ratio: float
    volume_spike: bool
    volatility_spike: bool


@dataclass
class BiasCompatibility:
    """
    Defines how a regime affects different bias directions.
    
    Attributes:
        bullish_multiplier: Multiplier for bullish bias probability (0.0-1.5)
        bearish_multiplier: Multiplier for bearish bias probability (0.0-1.5)
        neutral_multiplier: Multiplier for neutral bias probability (0.0-1.5)
        suppress_bullish: Whether to suppress bullish signals entirely
        suppress_bearish: Whether to suppress bearish signals entirely
        confidence_penalty: Additional penalty to apply to all probabilities (0.0-0.5)
    """
    bullish_multiplier: float = 1.0
    bearish_multiplier: float = 1.0
    neutral_multiplier: float = 1.0
    suppress_bullish: bool = False
    suppress_bearish: bool = False
    confidence_penalty: float = 0.0


# Bias compatibility rules per regime
REGIME_BIAS_COMPATIBILITY: Dict[SessionRegime, BiasCompatibility] = {
    SessionRegime.TRENDING: BiasCompatibility(
        bullish_multiplier=1.2,   # Favor trend-following bullish in uptrend
        bearish_multiplier=1.2,   # Favor trend-following bearish in downtrend
        neutral_multiplier=0.7,   # Penalize neutral (missing the trend)
        confidence_penalty=0.0
    ),
    SessionRegime.MEAN_REVERTING: BiasCompatibility(
        bullish_multiplier=0.6,   # Suppress strong bullish (likely to revert)
        bearish_multiplier=0.6,   # Suppress strong bearish (likely to revert)
        neutral_multiplier=1.3,   # Favor neutral/range-bound strategies
        suppress_bullish=False,   # Don't fully suppress, just reduce
        suppress_bearish=False,
        confidence_penalty=0.1    # Add uncertainty in range-bound markets
    ),
    SessionRegime.HIGH_VOLATILITY: BiasCompatibility(
        bullish_multiplier=0.7,
        bearish_multiplier=0.7,
        neutral_multiplier=1.1,
        confidence_penalty=0.15   # Higher uncertainty in volatile markets
    ),
    SessionRegime.LOW_LIQUIDITY: BiasCompatibility(
        bullish_multiplier=0.5,   # Heavily penalize directional bets
        bearish_multiplier=0.5,
        neutral_multiplier=1.2,
        confidence_penalty=0.2    # High uncertainty in illiquid markets
    ),
    SessionRegime.NEWS_DRIVEN: BiasCompatibility(
        bullish_multiplier=0.8,
        bearish_multiplier=0.8,
        neutral_multiplier=1.0,
        confidence_penalty=0.25   # Highest uncertainty - unpredictable
    )
}

# Confidence multipliers per regime (applied to overall confidence)
REGIME_CONFIDENCE_MULTIPLIERS: Dict[SessionRegime, float] = {
    SessionRegime.TRENDING: 1.1,        # Higher confidence in trends
    SessionRegime.MEAN_REVERTING: 0.9,  # Lower confidence in range
    SessionRegime.HIGH_VOLATILITY: 0.75, # Much lower in high vol
    SessionRegime.LOW_LIQUIDITY: 0.7,   # Low confidence in illiquid
    SessionRegime.NEWS_DRIVEN: 0.6      # Lowest - unpredictable
}


@dataclass
class SessionRegimeAnalysis:
    """
    Complete regime analysis for a market session.
    
    Attributes:
        regime: The dominant regime for this session
        trend_direction: Direction if TRENDING, NONE otherwise
        confidence: Confidence in regime classification (0.0-1.0)
        metrics: Raw metrics used for classification
        bias_compatibility: Rules for adjusting bias probabilities
        confidence_multiplier: Multiplier for overall signal confidence
        reasoning: Human-readable explanation
        warnings: List of regime-specific warnings
        session_date: Date of the session
        timestamp: When analysis was performed
    """
    regime: SessionRegime
    trend_direction: TrendDirection
    confidence: float
    metrics: RegimeMetrics
    bias_compatibility: BiasCompatibility
    confidence_multiplier: float
    reasoning: str
    warnings: List[str]
    session_date: date
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "regime": self.regime.value,
            "trend_direction": self.trend_direction.value,
            "confidence": round(self.confidence, 3),
            "confidence_multiplier": round(self.confidence_multiplier, 3),
            "bias_adjustments": {
                "bullish_multiplier": self.bias_compatibility.bullish_multiplier,
                "bearish_multiplier": self.bias_compatibility.bearish_multiplier,
                "neutral_multiplier": self.bias_compatibility.neutral_multiplier,
                "suppress_bullish": self.bias_compatibility.suppress_bullish,
                "suppress_bearish": self.bias_compatibility.suppress_bearish,
                "confidence_penalty": self.bias_compatibility.confidence_penalty
            },
            "metrics": {
                "asi_trend_strength": round(self.metrics.asi_trend_strength, 3),
                "asi_vs_sma20": round(self.metrics.asi_vs_sma20, 2),
                "asi_vs_sma50": round(self.metrics.asi_vs_sma50, 2),
                "volatility_ratio": round(self.metrics.volatility_ratio, 2),
                "volume_ratio": round(self.metrics.volume_ratio, 2),
                "volume_spike": self.metrics.volume_spike,
                "volatility_spike": self.metrics.volatility_spike
            },
            "reasoning": self.reasoning,
            "warnings": self.warnings,
            "session_date": self.session_date.isoformat(),
            "timestamp": self.timestamp.isoformat()
        }


class MarketRegimeEngine:
    """
    Market Regime Engine that classifies market conditions once per session.
    
    Uses market-wide indicators:
    - NSE ASI trend strength
    - Aggregate market volatility
    - Aggregate volume vs baseline
    
    Classifies exactly ONE dominant regime per session and provides
    confidence multipliers and bias compatibility rules.
    """
    
    # Thresholds for regime classification
    TREND_STRENGTH_THRESHOLD = 0.4       # |strength| > 0.4 = trending
    VOLATILITY_SPIKE_THRESHOLD = 1.5     # vol > 1.5x baseline = high vol
    VOLUME_SPIKE_THRESHOLD = 2.0         # volume > 2x baseline = spike
    LOW_VOLUME_THRESHOLD = 0.6           # volume < 0.6x baseline = low liquidity
    NEWS_DRIVEN_VOL_THRESHOLD = 1.3      # vol spike for news-driven
    NEWS_DRIVEN_VOLUME_THRESHOLD = 1.8   # volume spike for news-driven
    
    def __init__(self):
        self._session_cache: Dict[date, SessionRegimeAnalysis] = {}
        self._cache_ttl = timedelta(hours=8)  # Cache valid for trading session
    
    def classify_session(
        self,
        asi_prices: List[float],
        asi_volumes: List[float],
        current_volume: Optional[float] = None
    ) -> SessionRegimeAnalysis:
        """
        Classify the current market session into exactly ONE regime.
        
        Args:
            asi_prices: List of ASI closing prices (most recent last), min 60 values
            asi_volumes: List of ASI volumes (most recent last), min 20 values
            current_volume: Current session volume (uses last value if not provided)
        
        Returns:
            SessionRegimeAnalysis with regime classification and adjustments
        """
        today = date.today()
        
        # Check cache
        if today in self._session_cache:
            cached = self._session_cache[today]
            if datetime.now(timezone.utc) - cached.timestamp < self._cache_ttl:
                logger.debug("Returning cached regime analysis for %s", today)
                return cached
        
        # Calculate metrics
        metrics = self._calculate_metrics(asi_prices, asi_volumes, current_volume)
        
        # Classify regime (exactly one)
        regime, trend_direction, confidence, reasoning = self._classify_regime(metrics)
        
        # Get compatibility rules
        bias_compatibility = REGIME_BIAS_COMPATIBILITY[regime]
        confidence_multiplier = REGIME_CONFIDENCE_MULTIPLIERS[regime]
        
        # Adjust compatibility for trend direction in TRENDING regime
        if regime == SessionRegime.TRENDING:
            bias_compatibility = self._adjust_trending_compatibility(
                bias_compatibility, trend_direction
            )
        
        # Generate warnings
        warnings = self._generate_warnings(regime, metrics)
        
        analysis = SessionRegimeAnalysis(
            regime=regime,
            trend_direction=trend_direction,
            confidence=confidence,
            metrics=metrics,
            bias_compatibility=bias_compatibility,
            confidence_multiplier=confidence_multiplier,
            reasoning=reasoning,
            warnings=warnings,
            session_date=today
        )
        
        # Cache result
        self._session_cache[today] = analysis
        logger.info(
            "Market regime classified: %s (confidence: %.1f%%) - %s",
            regime.value, confidence * 100, reasoning
        )
        
        return analysis
    
    def _calculate_metrics(
        self,
        prices: List[float],
        volumes: List[float],
        current_volume: Optional[float]
    ) -> RegimeMetrics:
        """Calculate all metrics needed for regime classification."""
        prices_arr = np.array(prices, dtype=float)
        volumes_arr = np.array(volumes, dtype=float)
        
        # Ensure minimum data
        if len(prices_arr) < 60:
            prices_arr = np.pad(prices_arr, (60 - len(prices_arr), 0), mode='edge')
        if len(volumes_arr) < 20:
            volumes_arr = np.pad(volumes_arr, (20 - len(volumes_arr), 0), mode='edge')
        
        # ASI trend strength using linear regression slope
        x = np.arange(min(20, len(prices_arr)))
        y = prices_arr[-20:] if len(prices_arr) >= 20 else prices_arr
        if len(y) > 1:
            slope = np.polyfit(x[:len(y)], y, 1)[0]
            # Normalize slope to -1 to 1 range based on price level
            avg_price = np.mean(y)
            trend_strength = np.clip(slope / (avg_price * 0.01), -1, 1) if avg_price > 0 else 0
        else:
            trend_strength = 0.0
        
        # ASI vs SMAs
        sma20 = np.mean(prices_arr[-20:])
        sma50 = np.mean(prices_arr[-50:]) if len(prices_arr) >= 50 else sma20
        current_price = prices_arr[-1]
        
        asi_vs_sma20 = ((current_price - sma20) / sma20 * 100) if sma20 > 0 else 0
        asi_vs_sma50 = ((current_price - sma50) / sma50 * 100) if sma50 > 0 else 0
        
        # Volatility (annualized)
        returns = np.diff(prices_arr) / prices_arr[:-1]
        returns = returns[~np.isnan(returns)]
        
        if len(returns) >= 20:
            vol_current = np.std(returns[-20:]) * np.sqrt(252)
        else:
            vol_current = np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0.2
        
        if len(returns) >= 60:
            vol_baseline = np.std(returns[-60:]) * np.sqrt(252)
        else:
            vol_baseline = vol_current
        
        vol_ratio = vol_current / vol_baseline if vol_baseline > 0 else 1.0
        
        # Volume metrics
        vol_baseline_avg = np.mean(volumes_arr[-20:]) if len(volumes_arr) >= 20 else np.mean(volumes_arr)
        vol_current_val = current_volume if current_volume is not None else volumes_arr[-1]
        
        volume_ratio = vol_current_val / vol_baseline_avg if vol_baseline_avg > 0 else 1.0
        
        return RegimeMetrics(
            asi_trend_strength=float(trend_strength),
            asi_vs_sma20=float(asi_vs_sma20),
            asi_vs_sma50=float(asi_vs_sma50),
            volatility_current=float(vol_current),
            volatility_baseline=float(vol_baseline),
            volatility_ratio=float(vol_ratio),
            volume_current=float(vol_current_val),
            volume_baseline=float(vol_baseline_avg),
            volume_ratio=float(volume_ratio),
            volume_spike=volume_ratio > self.VOLUME_SPIKE_THRESHOLD,
            volatility_spike=vol_ratio > self.VOLATILITY_SPIKE_THRESHOLD
        )
    
    def _classify_regime(
        self,
        metrics: RegimeMetrics
    ) -> Tuple[SessionRegime, TrendDirection, float, str]:
        """
        Classify into exactly ONE dominant regime.
        
        Priority order (highest to lowest):
        1. NEWS_DRIVEN (volume + volatility spike)
        2. HIGH_VOLATILITY (volatility spike alone)
        3. LOW_LIQUIDITY (very low volume)
        4. TRENDING (strong directional movement)
        5. MEAN_REVERTING (default/range-bound)
        
        Returns:
            Tuple of (regime, trend_direction, confidence, reasoning)
        """
        # 1. NEWS_DRIVEN: Both volume AND volatility spike
        if metrics.volume_spike and metrics.volatility_ratio > self.NEWS_DRIVEN_VOL_THRESHOLD:
            confidence = min(0.9, 0.6 + (metrics.volume_ratio - 2) * 0.1 + (metrics.volatility_ratio - 1.3) * 0.15)
            return (
                SessionRegime.NEWS_DRIVEN,
                TrendDirection.NONE,
                confidence,
                f"News-driven regime: Volume {metrics.volume_ratio:.1f}x baseline with "
                f"volatility {metrics.volatility_ratio:.1f}x baseline indicates event-driven market"
            )
        
        # 2. HIGH_VOLATILITY: Volatility spike without proportional volume
        if metrics.volatility_spike:
            confidence = min(0.85, 0.5 + (metrics.volatility_ratio - 1.5) * 0.2)
            return (
                SessionRegime.HIGH_VOLATILITY,
                TrendDirection.NONE,
                confidence,
                f"High volatility regime: Volatility at {metrics.volatility_ratio:.1f}x baseline "
                f"({metrics.volatility_current:.1%} annualized)"
            )
        
        # 3. LOW_LIQUIDITY: Very low volume
        if metrics.volume_ratio < self.LOW_VOLUME_THRESHOLD:
            confidence = min(0.8, 0.5 + (self.LOW_VOLUME_THRESHOLD - metrics.volume_ratio) * 0.5)
            return (
                SessionRegime.LOW_LIQUIDITY,
                TrendDirection.NONE,
                confidence,
                f"Low liquidity regime: Volume at {metrics.volume_ratio:.1f}x baseline "
                f"({metrics.volume_current:,.0f} vs {metrics.volume_baseline:,.0f} avg)"
            )
        
        # 4. TRENDING: Strong directional movement
        if abs(metrics.asi_trend_strength) > self.TREND_STRENGTH_THRESHOLD:
            trend_dir = TrendDirection.BULLISH if metrics.asi_trend_strength > 0 else TrendDirection.BEARISH
            confidence = min(0.85, 0.5 + abs(metrics.asi_trend_strength) * 0.4)
            direction_text = "bullish" if trend_dir == TrendDirection.BULLISH else "bearish"
            return (
                SessionRegime.TRENDING,
                trend_dir,
                confidence,
                f"Trending regime ({direction_text}): ASI trend strength {metrics.asi_trend_strength:.2f} "
                f"with price {metrics.asi_vs_sma20:+.1f}% vs 20-day SMA"
            )
        
        # 5. MEAN_REVERTING: Default/range-bound
        confidence = 0.6 + (1 - abs(metrics.asi_trend_strength)) * 0.2
        return (
            SessionRegime.MEAN_REVERTING,
            TrendDirection.NONE,
            confidence,
            f"Mean-reverting regime: No strong trend (strength {metrics.asi_trend_strength:.2f}), "
            f"ASI within {abs(metrics.asi_vs_sma20):.1f}% of 20-day SMA"
        )
    
    def _adjust_trending_compatibility(
        self,
        base_compatibility: BiasCompatibility,
        trend_direction: TrendDirection
    ) -> BiasCompatibility:
        """Adjust compatibility rules based on trend direction."""
        if trend_direction == TrendDirection.BULLISH:
            # In bullish trend: favor bullish, penalize bearish
            return BiasCompatibility(
                bullish_multiplier=1.3,
                bearish_multiplier=0.5,  # Counter-trend bearish penalized
                neutral_multiplier=0.7,
                suppress_bullish=False,
                suppress_bearish=False,  # Don't fully suppress, just reduce
                confidence_penalty=0.0
            )
        elif trend_direction == TrendDirection.BEARISH:
            # In bearish trend: favor bearish, penalize bullish
            return BiasCompatibility(
                bullish_multiplier=0.5,  # Counter-trend bullish penalized
                bearish_multiplier=1.3,
                neutral_multiplier=0.7,
                suppress_bullish=False,
                suppress_bearish=False,
                confidence_penalty=0.0
            )
        return base_compatibility
    
    def _generate_warnings(
        self,
        regime: SessionRegime,
        metrics: RegimeMetrics
    ) -> List[str]:
        """Generate regime-specific warnings."""
        warnings = []
        
        if regime == SessionRegime.NEWS_DRIVEN:
            warnings.append(
                "⚠️ NEWS-DRIVEN MARKET: Elevated uncertainty. "
                "Bias probabilities heavily discounted."
            )
        
        if regime == SessionRegime.HIGH_VOLATILITY:
            warnings.append(
                f"⚠️ HIGH VOLATILITY: {metrics.volatility_current:.1%} annualized. "
                "Consider reduced position sizes."
            )
        
        if regime == SessionRegime.LOW_LIQUIDITY:
            warnings.append(
                "⚠️ LOW LIQUIDITY: Execution risk elevated. "
                "Wider spreads expected."
            )
        
        if metrics.volatility_ratio > 2.0:
            warnings.append(
                f"⚠️ EXTREME VOLATILITY: {metrics.volatility_ratio:.1f}x baseline"
            )
        
        if metrics.volume_ratio > 3.0:
            warnings.append(
                f"⚠️ EXTREME VOLUME: {metrics.volume_ratio:.1f}x baseline - "
                "possible major market event"
            )
        
        return warnings
    
    def adjust_bias_probability(
        self,
        bias_probability: int,
        bias_direction: str,
        regime_analysis: SessionRegimeAnalysis,
        is_suppressed: bool = False
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Adjust bias probability based on regime compatibility.
        
        SUPPRESSED logic remains authoritative - if already suppressed,
        no adjustment is made.
        
        Args:
            bias_probability: Original probability (0-100)
            bias_direction: "bullish", "neutral", or "bearish"
            regime_analysis: Current session's regime analysis
            is_suppressed: Whether signal is already suppressed
        
        Returns:
            Tuple of (adjusted_probability, suppression_reason)
            - If suppressed by regime: (None, reason)
            - If adjusted: (new_probability, None)
        """
        # SUPPRESSED logic is authoritative
        if is_suppressed:
            return None, None  # Already suppressed, don't override
        
        compatibility = regime_analysis.bias_compatibility
        
        # Check for regime-based suppression
        if bias_direction == "bullish" and compatibility.suppress_bullish:
            return None, (
                f"Bullish bias suppressed: {regime_analysis.regime.value} regime "
                f"is incompatible with bullish signals"
            )
        
        if bias_direction == "bearish" and compatibility.suppress_bearish:
            return None, (
                f"Bearish bias suppressed: {regime_analysis.regime.value} regime "
                f"is incompatible with bearish signals"
            )
        
        # Get appropriate multiplier
        if bias_direction == "bullish":
            multiplier = compatibility.bullish_multiplier
        elif bias_direction == "bearish":
            multiplier = compatibility.bearish_multiplier
        else:
            multiplier = compatibility.neutral_multiplier
        
        # Apply multiplier and penalty
        adjusted = bias_probability * multiplier
        adjusted = adjusted * (1 - compatibility.confidence_penalty)
        
        # Apply overall regime confidence multiplier
        adjusted = adjusted * regime_analysis.confidence_multiplier
        
        # Clamp to valid range
        adjusted_int = max(0, min(100, int(round(adjusted))))
        
        return adjusted_int, None
    
    def get_regime_metadata(self) -> Optional[Dict[str, Any]]:
        """
        Get current session's regime metadata for attachment to recommendations.
        
        Returns:
            Dict with regime info or None if not yet classified
        """
        today = date.today()
        if today in self._session_cache:
            analysis = self._session_cache[today]
            return {
                "market_regime": analysis.regime.value,
                "regime_confidence": analysis.confidence,
                "trend_direction": analysis.trend_direction.value,
                "confidence_multiplier": analysis.confidence_multiplier,
                "warnings": analysis.warnings
            }
        return None
    
    def clear_cache(self):
        """Clear the session cache."""
        self._session_cache.clear()
    
    async def classify_from_ngnmarket(self, ngnmarket_data: Dict[str, Any]) -> SessionRegimeAnalysis:
        """
        Classify regime using data from NgnMarketService.
        
        This method uses ASI history, estimated breadth, and volatility data
        from ngnmarket.com to classify the market regime.
        
        Args:
            ngnmarket_data: Dict from NgnMarketService.get_market_data_for_regime()
        
        Returns:
            SessionRegimeAnalysis with regime classification
        """
        today = date.today()
        
        # Check cache
        if today in self._session_cache:
            cached = self._session_cache[today]
            if datetime.now(timezone.utc) - cached.timestamp < self._cache_ttl:
                logger.debug("Returning cached regime analysis for %s", today)
                return cached
        
        # Extract data from ngnmarket response
        snapshot = ngnmarket_data.get('snapshot', {})
        breadth = ngnmarket_data.get('breadth', {})
        asi_trend = ngnmarket_data.get('asi_trend', {})
        asi_volatility = ngnmarket_data.get('asi_volatility', {})
        asi_history = ngnmarket_data.get('asi_history', [])
        
        # Build ASI prices from history
        asi_prices = [point['asi'] for point in reversed(asi_history)] if asi_history else [100000]
        
        # Calculate trend strength from ngnmarket data
        trend_direction_str = asi_trend.get('direction', 'flat')
        trend_strength = asi_trend.get('strength', 0.0)
        change_percent = asi_trend.get('change_percent', 0.0)
        
        # Map trend direction
        if trend_direction_str == 'up':
            trend_strength_signed = abs(trend_strength)
        elif trend_direction_str == 'down':
            trend_strength_signed = -abs(trend_strength)
        else:
            trend_strength_signed = 0.0
        
        # Get volatility level
        volatility_level = asi_volatility.get('level', 'moderate')
        daily_range = asi_volatility.get('daily_range_percent', 1.0)
        
        # Map volatility to ratio (compared to baseline of 1.0)
        volatility_mapping = {'low': 0.7, 'moderate': 1.0, 'high': 1.8}
        vol_ratio = volatility_mapping.get(volatility_level, 1.0)
        
        # Estimate volume ratio from snapshot
        volume = snapshot.get('volume', 0)
        deals = snapshot.get('deals', 0)
        # Use deals as a proxy for volume activity (typical range: 5000-30000)
        volume_ratio = deals / 15000 if deals > 0 else 1.0  # 15000 as baseline
        
        # Build metrics
        current_asi = asi_prices[-1] if asi_prices else 100000
        sma20 = np.mean(asi_prices[-20:]) if len(asi_prices) >= 20 else current_asi
        sma50 = np.mean(asi_prices[-50:]) if len(asi_prices) >= 50 else sma20
        
        metrics = RegimeMetrics(
            asi_trend_strength=float(trend_strength_signed),
            asi_vs_sma20=((current_asi - sma20) / sma20 * 100) if sma20 > 0 else 0,
            asi_vs_sma50=((current_asi - sma50) / sma50 * 100) if sma50 > 0 else 0,
            volatility_current=daily_range / 100,  # Convert percent to decimal
            volatility_baseline=0.01,  # 1% baseline
            volatility_ratio=vol_ratio,
            volume_current=float(volume),
            volume_baseline=float(volume) / volume_ratio if volume_ratio > 0 else float(volume),
            volume_ratio=volume_ratio,
            volume_spike=volume_ratio > self.VOLUME_SPIKE_THRESHOLD,
            volatility_spike=vol_ratio > self.VOLATILITY_SPIKE_THRESHOLD
        )
        
        # Use breadth data to refine classification
        breadth_ratio = breadth.get('ratio', 0.5)
        market_sentiment = breadth.get('sentiment', 'neutral')
        
        # Classify regime
        regime, trend_dir, confidence, reasoning = self._classify_regime(metrics)
        
        # Adjust confidence based on breadth if available
        if breadth:
            breadth_confidence = breadth.get('confidence', 0.5)
            # Weighted average with breadth confidence
            confidence = confidence * 0.7 + breadth_confidence * 0.3
        
        # Get compatibility rules
        bias_compatibility = REGIME_BIAS_COMPATIBILITY[regime]
        confidence_multiplier = REGIME_CONFIDENCE_MULTIPLIERS[regime]
        
        # Adjust for trend direction
        if regime == SessionRegime.TRENDING:
            bias_compatibility = self._adjust_trending_compatibility(bias_compatibility, trend_dir)
        
        # Generate warnings
        warnings = self._generate_warnings(regime, metrics)
        
        # Add ngnmarket-specific warnings
        if breadth.get('confidence', 1.0) < 0.7:
            warnings.append("⚠️ Market breadth is estimated (not direct data)")
        
        analysis = SessionRegimeAnalysis(
            regime=regime,
            trend_direction=trend_dir,
            confidence=confidence,
            metrics=metrics,
            bias_compatibility=bias_compatibility,
            confidence_multiplier=confidence_multiplier,
            reasoning=reasoning,
            warnings=warnings,
            session_date=today
        )
        
        # Cache result
        self._session_cache[today] = analysis
        logger.info(
            "Market regime (ngnmarket): %s (confidence: %.1f%%) - %s",
            regime.value, confidence * 100, reasoning
        )
        
        return analysis


# Singleton instance
_engine_instance: Optional[MarketRegimeEngine] = None


def get_regime_engine() -> MarketRegimeEngine:
    """Get singleton regime engine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = MarketRegimeEngine()
    return _engine_instance
