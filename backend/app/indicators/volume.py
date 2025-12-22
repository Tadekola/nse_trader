"""
Volume indicators for technical analysis.
"""
from typing import Optional
import pandas as pd
from app.indicators.base import (
    BaseIndicator, IndicatorResult, SignalDirection,
    calculate_obv, calculate_sma
)


class OBVIndicator(BaseIndicator):
    """
    On-Balance Volume indicator.
    
    Tracks cumulative buying/selling pressure.
    - Rising OBV with rising price: Bullish confirmation
    - Falling OBV with rising price: Bearish divergence (weakness)
    - Rising OBV with falling price: Bullish divergence (accumulation)
    """
    
    def __init__(self):
        super().__init__("OBV")
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, 20):
            return None
        
        if 'Volume' not in df.columns:
            return None
        
        obv = calculate_obv(df)
        
        current_obv = obv.iloc[-1]
        obv_sma = calculate_sma(obv, 20).iloc[-1]
        
        # Calculate OBV trend
        obv_change_20d = (obv.iloc[-1] - obv.iloc[-20]) / abs(obv.iloc[-20]) * 100 if obv.iloc[-20] != 0 else 0
        
        # Price trend for comparison
        price_change_20d = (df['Close'].iloc[-1] - df['Close'].iloc[-20]) / df['Close'].iloc[-20] * 100
        
        # Detect divergence
        divergence = self._detect_divergence(price_change_20d, obv_change_20d)
        
        signal, strength = self.get_signal((obv_change_20d, price_change_20d, divergence))
        
        return IndicatorResult(
            name=self.name,
            value=current_obv,
            signal=signal,
            strength=strength,
            description=self._get_description(
                current_obv, obv_sma, obv_change_20d, 
                price_change_20d, divergence
            ),
            raw_values={
                "obv": current_obv,
                "obv_sma_20": obv_sma,
                "obv_change_20d_pct": obv_change_20d,
                "price_change_20d_pct": price_change_20d,
                "divergence": divergence,
                "trend": "accumulation" if current_obv > obv_sma else "distribution"
            }
        )
    
    def get_signal(
        self, values: tuple[float, float, str]
    ) -> tuple[SignalDirection, float]:
        obv_change, price_change, divergence = values
        
        if divergence == "bullish_divergence":
            return SignalDirection.BULLISH, 0.7
        elif divergence == "bearish_divergence":
            return SignalDirection.BEARISH, -0.7
        
        # Confirmation signals
        if obv_change > 10 and price_change > 0:
            return SignalDirection.BULLISH, min(obv_change / 30, 1.0)
        elif obv_change < -10 and price_change < 0:
            return SignalDirection.BEARISH, max(obv_change / 30, -1.0)
        
        return SignalDirection.NEUTRAL, 0.0
    
    def _detect_divergence(self, price_change: float, obv_change: float) -> str:
        # Price up, OBV down = bearish divergence
        if price_change > 5 and obv_change < -5:
            return "bearish_divergence"
        # Price down, OBV up = bullish divergence
        elif price_change < -5 and obv_change > 5:
            return "bullish_divergence"
        return "none"
    
    def _get_description(
        self, obv: float, obv_sma: float, obv_change: float,
        price_change: float, divergence: str
    ) -> str:
        if divergence == "bullish_divergence":
            return "OBV bullish divergence: Volume accumulation despite falling price - smart money may be buying"
        elif divergence == "bearish_divergence":
            return "OBV bearish divergence: Volume distribution despite rising price - smart money may be selling"
        
        trend = "accumulation" if obv > obv_sma else "distribution"
        
        if trend == "accumulation":
            return f"OBV shows accumulation (above 20-day average) - buying pressure present"
        else:
            return f"OBV shows distribution (below 20-day average) - selling pressure present"


class VolumeRatioIndicator(BaseIndicator):
    """
    Volume Ratio indicator.
    
    Compares current volume to historical average.
    
    Critical for Nigerian market:
    - Low volume = poor liquidity, harder to exit
    - High volume on price move = confirmation
    - High volume without price move = possible accumulation/distribution
    """
    
    def __init__(self, period: int = 20):
        super().__init__("Volume_Ratio")
        self.period = period
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, self.period):
            return None
        
        if 'Volume' not in df.columns:
            return None
        
        volume = df['Volume']
        current_volume = volume.iloc[-1]
        avg_volume = volume.iloc[-self.period:].mean()
        
        ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        # Calculate value traded
        current_price = df['Close'].iloc[-1]
        value_traded = current_volume * current_price
        avg_value = (volume.iloc[-self.period:] * df['Close'].iloc[-self.period:]).mean()
        
        signal, strength = self.get_signal(ratio)
        
        return IndicatorResult(
            name=self.name,
            value=ratio,
            signal=signal,
            strength=strength,
            description=self._get_description(
                current_volume, avg_volume, ratio, value_traded
            ),
            raw_values={
                "current_volume": int(current_volume),
                "avg_volume": int(avg_volume),
                "volume_ratio": ratio,
                "value_traded": value_traded,
                "avg_value_traded": avg_value,
                "volume_category": self._categorize_volume(ratio)
            }
        )
    
    def get_signal(self, ratio: float) -> tuple[SignalDirection, float]:
        """
        Volume alone doesn't give directional signal.
        High volume confirms price moves.
        """
        return SignalDirection.NEUTRAL, 0.0
    
    def _categorize_volume(self, ratio: float) -> str:
        if ratio >= 3.0:
            return "extremely_high"
        elif ratio >= 2.0:
            return "very_high"
        elif ratio >= 1.5:
            return "high"
        elif ratio >= 0.75:
            return "normal"
        elif ratio >= 0.5:
            return "low"
        else:
            return "very_low"
    
    def _get_description(
        self, volume: float, avg: float, ratio: float, value: float
    ) -> str:
        category = self._categorize_volume(ratio)
        
        # Format value traded
        if value >= 1_000_000_000:
            value_str = f"₦{value/1_000_000_000:.2f}B"
        elif value >= 1_000_000:
            value_str = f"₦{value/1_000_000:.2f}M"
        else:
            value_str = f"₦{value/1_000:.2f}K"
        
        if category == "extremely_high":
            return f"Volume {ratio:.1f}x average ({value_str} traded) - significant institutional activity"
        elif category == "very_high":
            return f"Volume {ratio:.1f}x average ({value_str} traded) - strong interest"
        elif category == "high":
            return f"Volume {ratio:.1f}x average ({value_str} traded) - above normal activity"
        elif category == "low":
            return f"Volume {ratio:.1f}x average ({value_str} traded) - below normal, check liquidity"
        elif category == "very_low":
            return f"Volume {ratio:.1f}x average ({value_str} traded) - very thin trading, exit may be difficult"
        return f"Volume at {ratio:.1f}x average ({value_str} traded) - normal activity"


class LiquidityScoreIndicator(BaseIndicator):
    """
    Liquidity Score indicator - specific to Nigerian market.
    
    Combines:
    - Average daily volume
    - Average daily value traded
    - Days since last trade
    - Bid-ask spread (if available)
    
    Returns a 0-1 score where:
    - 1.0 = Highly liquid (easy to trade)
    - 0.0 = Illiquid (hard to trade)
    """
    
    def __init__(self):
        super().__init__("Liquidity_Score")
        
        # Thresholds for Nigerian market (in Naira)
        self.high_value_threshold = 100_000_000  # ₦100M daily
        self.medium_value_threshold = 10_000_000  # ₦10M daily
        self.low_value_threshold = 1_000_000     # ₦1M daily
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, 20):
            return None
        
        if 'Volume' not in df.columns:
            return None
        
        close = df['Close']
        volume = df['Volume']
        
        # Average daily value over 20 days
        daily_value = close * volume
        avg_daily_value = daily_value.iloc[-20:].mean()
        
        # Days since last trade (non-zero volume)
        last_trade_idx = volume[volume > 0].last_valid_index()
        if last_trade_idx is not None:
            days_since_trade = (df.index[-1] - last_trade_idx).days if hasattr(df.index[-1], 'days') else 0
        else:
            days_since_trade = 999  # No trades found
        
        # Calculate liquidity score
        liquidity_score = self._calculate_score(avg_daily_value, days_since_trade)
        
        # Determine rating
        rating = self._get_rating(liquidity_score)
        
        signal, strength = self.get_signal(liquidity_score)
        
        return IndicatorResult(
            name=self.name,
            value=liquidity_score,
            signal=signal,
            strength=strength,
            description=self._get_description(avg_daily_value, days_since_trade, rating),
            raw_values={
                "liquidity_score": liquidity_score,
                "avg_daily_value": avg_daily_value,
                "days_since_last_trade": days_since_trade,
                "rating": rating,
                "estimated_days_to_exit_1m": self._estimate_exit_time(avg_daily_value, 1_000_000)
            }
        )
    
    def _calculate_score(self, avg_value: float, days_since_trade: int) -> float:
        """Calculate liquidity score 0-1."""
        # Value component (0-0.7)
        if avg_value >= self.high_value_threshold:
            value_score = 0.7
        elif avg_value >= self.medium_value_threshold:
            value_score = 0.5 + 0.2 * (avg_value - self.medium_value_threshold) / (self.high_value_threshold - self.medium_value_threshold)
        elif avg_value >= self.low_value_threshold:
            value_score = 0.2 + 0.3 * (avg_value - self.low_value_threshold) / (self.medium_value_threshold - self.low_value_threshold)
        else:
            value_score = 0.2 * (avg_value / self.low_value_threshold)
        
        # Recency component (0-0.3)
        if days_since_trade == 0:
            recency_score = 0.3
        elif days_since_trade <= 2:
            recency_score = 0.2
        elif days_since_trade <= 5:
            recency_score = 0.1
        else:
            recency_score = 0.0
        
        return min(value_score + recency_score, 1.0)
    
    def _get_rating(self, score: float) -> str:
        if score >= 0.8:
            return "high"
        elif score >= 0.5:
            return "medium"
        elif score >= 0.3:
            return "low"
        else:
            return "very_low"
    
    def _estimate_exit_time(self, avg_value: float, position_size: float) -> float:
        """Estimate days to exit a position without excessive impact."""
        if avg_value <= 0:
            return 999
        # Assume we can trade 20% of daily value without major impact
        daily_exit_capacity = avg_value * 0.2
        return position_size / daily_exit_capacity if daily_exit_capacity > 0 else 999
    
    def get_signal(self, score: float) -> tuple[SignalDirection, float]:
        # Liquidity is not directional, but low liquidity is a warning
        return SignalDirection.NEUTRAL, 0.0
    
    def _get_description(self, avg_value: float, days_since: int, rating: str) -> str:
        # Format value
        if avg_value >= 1_000_000_000:
            value_str = f"₦{avg_value/1_000_000_000:.2f}B"
        elif avg_value >= 1_000_000:
            value_str = f"₦{avg_value/1_000_000:.2f}M"
        else:
            value_str = f"₦{avg_value/1_000:.2f}K"
        
        if rating == "high":
            return f"High liquidity ({value_str}/day avg) - easy to enter/exit positions"
        elif rating == "medium":
            return f"Medium liquidity ({value_str}/day avg) - moderate position sizes recommended"
        elif rating == "low":
            return f"Low liquidity ({value_str}/day avg) - small positions only, exit may take multiple days"
        else:
            if days_since > 5:
                return f"Very low liquidity ({value_str}/day avg, no trades in {days_since} days) - avoid or use extreme caution"
            return f"Very low liquidity ({value_str}/day avg) - significant execution risk"
