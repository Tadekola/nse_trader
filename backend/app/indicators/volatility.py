"""
Volatility indicators for technical analysis.
"""
from typing import Optional
import pandas as pd
import numpy as np
from app.indicators.base import (
    BaseIndicator, IndicatorResult, SignalDirection,
    calculate_atr, calculate_bollinger_bands
)


class ATRIndicator(BaseIndicator):
    """
    Average True Range indicator.
    
    Measures volatility - used for:
    - Stop-loss placement
    - Position sizing
    - Volatility assessment
    """
    
    def __init__(self, period: int = 14):
        super().__init__(f"ATR_{period}")
        self.period = period
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, self.period + 1):
            return None
        
        if 'High' not in df.columns or 'Low' not in df.columns:
            return None
        
        atr = calculate_atr(df, self.period)
        current_atr = atr.iloc[-1]
        current_price = df['Close'].iloc[-1]
        
        # ATR as percentage of price
        atr_percent = (current_atr / current_price) * 100
        
        # Compare to historical ATR
        avg_atr = atr.iloc[-60:].mean() if len(atr) >= 60 else atr.mean()
        atr_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0
        
        signal, strength = self.get_signal(atr_ratio)
        
        return IndicatorResult(
            name=self.name,
            value=current_atr,
            signal=signal,
            strength=strength,
            description=self._get_description(current_atr, atr_percent, atr_ratio),
            raw_values={
                "atr": current_atr,
                "atr_percent": atr_percent,
                "atr_ratio": atr_ratio,
                "suggested_stop_1atr": current_price - current_atr,
                "suggested_stop_2atr": current_price - (2 * current_atr)
            }
        )
    
    def get_signal(self, atr_ratio: float) -> tuple[SignalDirection, float]:
        """
        ATR doesn't give directional signals.
        High volatility can precede breakouts (neutral but notable).
        """
        if atr_ratio > 1.5:
            # High volatility - caution
            return SignalDirection.NEUTRAL, 0.0
        elif atr_ratio < 0.7:
            # Low volatility - potential for breakout
            return SignalDirection.NEUTRAL, 0.0
        return SignalDirection.NEUTRAL, 0.0
    
    def _get_description(self, atr: float, atr_pct: float, ratio: float) -> str:
        if ratio > 2:
            return f"ATR at ₦{atr:.2f} ({atr_pct:.1f}% of price) - extremely high volatility, use wide stops"
        elif ratio > 1.5:
            return f"ATR at ₦{atr:.2f} ({atr_pct:.1f}% of price) - elevated volatility"
        elif ratio < 0.5:
            return f"ATR at ₦{atr:.2f} ({atr_pct:.1f}% of price) - very low volatility, potential breakout setup"
        elif ratio < 0.7:
            return f"ATR at ₦{atr:.2f} ({atr_pct:.1f}% of price) - below-average volatility"
        return f"ATR at ₦{atr:.2f} ({atr_pct:.1f}% of price) - normal volatility"


class BollingerBandsIndicator(BaseIndicator):
    """
    Bollinger Bands indicator.
    
    Signals:
    - Price at lower band: Potential oversold
    - Price at upper band: Potential overbought
    - Bandwidth squeeze: Potential breakout coming
    - Bandwidth expansion: Trend in progress
    """
    
    def __init__(self, period: int = 20, num_std: float = 2.0):
        super().__init__("Bollinger_Bands")
        self.period = period
        self.num_std = num_std
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, self.period):
            return None
        
        close = self.clean_series(df['Close'])
        upper, middle, lower = calculate_bollinger_bands(
            close, self.period, self.num_std
        )
        
        current_price = close.iloc[-1]
        current_upper = upper.iloc[-1]
        current_middle = middle.iloc[-1]
        current_lower = lower.iloc[-1]
        
        # Calculate %B (position within bands)
        bandwidth = current_upper - current_lower
        percent_b = (current_price - current_lower) / bandwidth if bandwidth > 0 else 0.5
        
        # Calculate bandwidth percentage
        bandwidth_pct = (bandwidth / current_middle) * 100
        
        # Historical bandwidth for squeeze detection
        historical_bw = ((upper - lower) / middle * 100)
        avg_bandwidth = historical_bw.iloc[-60:].mean() if len(historical_bw) >= 60 else historical_bw.mean()
        squeeze = bandwidth_pct < avg_bandwidth * 0.75
        
        signal, strength = self.get_signal(percent_b)
        
        return IndicatorResult(
            name=self.name,
            value=percent_b * 100,  # As percentage
            signal=signal,
            strength=strength,
            description=self._get_description(
                current_price, current_upper, current_middle, 
                current_lower, percent_b, squeeze
            ),
            raw_values={
                "upper": current_upper,
                "middle": current_middle,
                "lower": current_lower,
                "percent_b": percent_b,
                "bandwidth_pct": bandwidth_pct,
                "squeeze": squeeze
            }
        )
    
    def get_signal(self, percent_b: float) -> tuple[SignalDirection, float]:
        """
        Signal based on %B (position within bands).
        
        %B < 0: Below lower band (oversold)
        %B > 1: Above upper band (overbought)
        """
        if percent_b <= 0:
            # At or below lower band - bullish
            strength = min(abs(percent_b) + 0.5, 1.0)
            return SignalDirection.BULLISH, strength
        elif percent_b >= 1:
            # At or above upper band - bearish
            strength = min(percent_b - 0.5, 1.0)
            return SignalDirection.BEARISH, -strength
        elif percent_b < 0.2:
            # Near lower band - slight bullish
            return SignalDirection.BULLISH, 0.3
        elif percent_b > 0.8:
            # Near upper band - slight bearish
            return SignalDirection.BEARISH, -0.3
        return SignalDirection.NEUTRAL, 0.0
    
    def _get_description(
        self, price: float, upper: float, middle: float, 
        lower: float, percent_b: float, squeeze: bool
    ) -> str:
        if squeeze:
            return f"Bollinger Band squeeze detected - potential breakout coming. Price at {percent_b*100:.0f}% of bands"
        
        if percent_b <= 0:
            return f"Price at ₦{price:.2f} below lower Bollinger Band (₦{lower:.2f}) - oversold, potential bounce"
        elif percent_b >= 1:
            return f"Price at ₦{price:.2f} above upper Bollinger Band (₦{upper:.2f}) - overbought, potential pullback"
        elif percent_b < 0.2:
            return f"Price near lower Bollinger Band - testing support at ₦{lower:.2f}"
        elif percent_b > 0.8:
            return f"Price near upper Bollinger Band - testing resistance at ₦{upper:.2f}"
        return f"Price at ₦{price:.2f} within Bollinger Bands (middle: ₦{middle:.2f})"


class VolatilityPercentileIndicator(BaseIndicator):
    """
    Calculates where current volatility ranks historically.
    
    Useful for:
    - Identifying low-volatility environments (potential breakouts)
    - Identifying high-volatility environments (caution/smaller positions)
    """
    
    def __init__(self, lookback: int = 252):
        super().__init__("Volatility_Percentile")
        self.lookback = lookback
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, 30):
            return None
        
        close = self.clean_series(df['Close'])
        
        # Calculate 20-day realized volatility
        returns = close.pct_change()
        vol_20d = returns.rolling(20).std() * np.sqrt(252) * 100  # Annualized %
        
        current_vol = vol_20d.iloc[-1]
        
        # Calculate percentile
        lookback_data = vol_20d.iloc[-self.lookback:] if len(vol_20d) >= self.lookback else vol_20d
        percentile = (lookback_data < current_vol).sum() / len(lookback_data) * 100
        
        signal, strength = self.get_signal(percentile)
        
        return IndicatorResult(
            name=self.name,
            value=percentile,
            signal=signal,
            strength=strength,
            description=self._get_description(current_vol, percentile),
            raw_values={
                "current_volatility": current_vol,
                "percentile": percentile,
                "volatility_regime": self._get_regime(percentile)
            }
        )
    
    def get_signal(self, percentile: float) -> tuple[SignalDirection, float]:
        # Volatility doesn't give directional signals
        return SignalDirection.NEUTRAL, 0.0
    
    def _get_regime(self, percentile: float) -> str:
        if percentile >= 80:
            return "high_volatility"
        elif percentile >= 60:
            return "elevated"
        elif percentile <= 20:
            return "low_volatility"
        elif percentile <= 40:
            return "subdued"
        return "normal"
    
    def _get_description(self, vol: float, percentile: float) -> str:
        regime = self._get_regime(percentile)
        
        if regime == "high_volatility":
            return f"Volatility at {vol:.1f}% (top {100-percentile:.0f}% historically) - consider smaller positions"
        elif regime == "low_volatility":
            return f"Volatility at {vol:.1f}% (bottom {percentile:.0f}% historically) - potential breakout setup"
        return f"Volatility at {vol:.1f}% ({percentile:.0f}th percentile) - normal conditions"
