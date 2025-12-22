"""
Momentum indicators for technical analysis.
"""
from typing import Optional
import pandas as pd
from app.indicators.base import (
    BaseIndicator, IndicatorResult, SignalDirection,
    calculate_rsi, calculate_stochastic, calculate_adx
)


class RSIIndicator(BaseIndicator):
    """
    Relative Strength Index indicator.
    
    Signals:
    - RSI < 30: Oversold (potential buy)
    - RSI > 70: Overbought (potential sell)
    - RSI 30-70: Neutral zone
    
    Nigerian Market Note:
    In low-liquidity stocks, RSI can remain extreme for extended periods.
    """
    
    def __init__(self, period: int = 14):
        super().__init__(f"RSI_{period}")
        self.period = period
        self.oversold_threshold = 30
        self.overbought_threshold = 70
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, self.period + 1):
            return None
        
        close = self.clean_series(df['Close'])
        rsi = calculate_rsi(close, self.period)
        
        current_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2] if len(rsi) > 1 else current_rsi
        
        signal, strength = self.get_signal(current_rsi)
        
        # Check for divergence
        divergence = self._detect_divergence(close, rsi)
        
        return IndicatorResult(
            name=self.name,
            value=current_rsi,
            signal=signal,
            strength=strength,
            description=self._get_description(current_rsi, prev_rsi, divergence),
            raw_values={
                "rsi": current_rsi,
                "prev_rsi": prev_rsi,
                "divergence": divergence,
                "momentum": "increasing" if current_rsi > prev_rsi else "decreasing"
            }
        )
    
    def get_signal(self, rsi: float) -> tuple[SignalDirection, float]:
        """
        Generate signal based on RSI level.
        
        Oversold = Bullish (potential bounce)
        Overbought = Bearish (potential pullback)
        """
        if rsi <= self.oversold_threshold:
            # Oversold - bullish signal (more oversold = stronger)
            strength = (self.oversold_threshold - rsi) / self.oversold_threshold
            return SignalDirection.BULLISH, min(strength, 1.0)
        elif rsi >= self.overbought_threshold:
            # Overbought - bearish signal
            strength = (rsi - self.overbought_threshold) / (100 - self.overbought_threshold)
            return SignalDirection.BEARISH, -min(strength, 1.0)
        else:
            # Neutral zone - slight bias based on position
            if rsi > 50:
                return SignalDirection.NEUTRAL, (rsi - 50) / 40  # Slight bullish
            else:
                return SignalDirection.NEUTRAL, (rsi - 50) / 40  # Slight bearish
    
    def _detect_divergence(self, price: pd.Series, rsi: pd.Series) -> str:
        """Detect bullish or bearish divergence."""
        if len(price) < 20:
            return "none"
        
        # Look at last 20 periods
        recent_price = price.iloc[-20:]
        recent_rsi = rsi.iloc[-20:]
        
        # Find local lows and highs
        price_making_lower_lows = recent_price.iloc[-1] < recent_price.iloc[-10]
        rsi_making_higher_lows = recent_rsi.iloc[-1] > recent_rsi.iloc[-10]
        
        price_making_higher_highs = recent_price.iloc[-1] > recent_price.iloc[-10]
        rsi_making_lower_highs = recent_rsi.iloc[-1] < recent_rsi.iloc[-10]
        
        if price_making_lower_lows and rsi_making_higher_lows:
            return "bullish_divergence"
        elif price_making_higher_highs and rsi_making_lower_highs:
            return "bearish_divergence"
        
        return "none"
    
    def _get_description(self, rsi: float, prev_rsi: float, divergence: str) -> str:
        momentum = "increasing" if rsi > prev_rsi else "decreasing"
        
        if divergence == "bullish_divergence":
            return f"RSI at {rsi:.1f} with bullish divergence - potential reversal signal"
        elif divergence == "bearish_divergence":
            return f"RSI at {rsi:.1f} with bearish divergence - potential reversal signal"
        
        if rsi <= 20:
            return f"RSI extremely oversold at {rsi:.1f} - strong bounce potential, but verify liquidity"
        elif rsi <= 30:
            return f"RSI oversold at {rsi:.1f} - potential buying opportunity"
        elif rsi >= 80:
            return f"RSI extremely overbought at {rsi:.1f} - pullback likely"
        elif rsi >= 70:
            return f"RSI overbought at {rsi:.1f} - consider taking profits"
        elif rsi > 50:
            return f"RSI at {rsi:.1f}, momentum {momentum} - bullish bias"
        else:
            return f"RSI at {rsi:.1f}, momentum {momentum} - bearish bias"


class StochasticIndicator(BaseIndicator):
    """
    Stochastic Oscillator indicator.
    
    Measures price position relative to high-low range.
    """
    
    def __init__(self, k_period: int = 14, d_period: int = 3):
        super().__init__("Stochastic")
        self.k_period = k_period
        self.d_period = d_period
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, self.k_period + self.d_period):
            return None
        
        if 'High' not in df.columns or 'Low' not in df.columns:
            return None
        
        k, d = calculate_stochastic(df, self.k_period, self.d_period)
        
        current_k = k.iloc[-1]
        current_d = d.iloc[-1]
        prev_k = k.iloc[-2] if len(k) > 1 else current_k
        prev_d = d.iloc[-2] if len(d) > 1 else current_d
        
        signal, strength = self.get_signal((current_k, current_d))
        
        # Detect crossover
        crossover = self._detect_crossover(k, d)
        
        return IndicatorResult(
            name=self.name,
            value=current_k,
            signal=signal,
            strength=strength,
            description=self._get_description(current_k, current_d, crossover),
            raw_values={
                "k": current_k,
                "d": current_d,
                "crossover": crossover
            }
        )
    
    def get_signal(self, values: tuple[float, float]) -> tuple[SignalDirection, float]:
        k, d = values
        
        if k < 20 and d < 20:
            strength = (20 - k) / 20
            return SignalDirection.BULLISH, min(strength, 1.0)
        elif k > 80 and d > 80:
            strength = (k - 80) / 20
            return SignalDirection.BEARISH, -min(strength, 1.0)
        else:
            # Neutral with slight bias
            bias = (k - 50) / 100
            return SignalDirection.NEUTRAL, bias
    
    def _detect_crossover(self, k: pd.Series, d: pd.Series) -> str:
        if len(k) < 3:
            return "none"
        
        for i in range(-3, 0):
            prev_diff = k.iloc[i-1] - d.iloc[i-1]
            curr_diff = k.iloc[i] - d.iloc[i]
            
            if prev_diff < 0 and curr_diff > 0 and k.iloc[i] < 30:
                return "bullish_crossover"
            elif prev_diff > 0 and curr_diff < 0 and k.iloc[i] > 70:
                return "bearish_crossover"
        
        return "none"
    
    def _get_description(self, k: float, d: float, crossover: str) -> str:
        if crossover == "bullish_crossover":
            return f"Stochastic bullish crossover in oversold zone (%K={k:.1f}) - buy signal"
        elif crossover == "bearish_crossover":
            return f"Stochastic bearish crossover in overbought zone (%K={k:.1f}) - sell signal"
        
        if k < 20:
            return f"Stochastic oversold (%K={k:.1f}, %D={d:.1f}) - potential reversal"
        elif k > 80:
            return f"Stochastic overbought (%K={k:.1f}, %D={d:.1f}) - potential pullback"
        return f"Stochastic neutral (%K={k:.1f}, %D={d:.1f})"


class ADXIndicator(BaseIndicator):
    """
    Average Directional Index indicator.
    
    Measures trend strength (not direction).
    - ADX > 25: Strong trend
    - ADX < 20: Weak/no trend (range-bound)
    """
    
    def __init__(self, period: int = 14):
        super().__init__(f"ADX_{period}")
        self.period = period
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, self.period * 2):
            return None
        
        if 'High' not in df.columns or 'Low' not in df.columns:
            return None
        
        adx, plus_di, minus_di = calculate_adx(df, self.period)
        
        current_adx = adx.iloc[-1]
        current_plus_di = plus_di.iloc[-1]
        current_minus_di = minus_di.iloc[-1]
        
        signal, strength = self.get_signal((current_adx, current_plus_di, current_minus_di))
        
        return IndicatorResult(
            name=self.name,
            value=current_adx,
            signal=signal,
            strength=strength,
            description=self._get_description(current_adx, current_plus_di, current_minus_di),
            raw_values={
                "adx": current_adx,
                "plus_di": current_plus_di,
                "minus_di": current_minus_di,
                "trend_strength": self._get_trend_strength(current_adx)
            }
        )
    
    def get_signal(
        self, values: tuple[float, float, float]
    ) -> tuple[SignalDirection, float]:
        adx, plus_di, minus_di = values
        
        # ADX indicates strength, DI indicates direction
        if adx < 20:
            # Weak trend - neutral regardless of DI
            return SignalDirection.NEUTRAL, 0.0
        
        strength = min((adx - 20) / 30, 1.0)  # Normalize 20-50 to 0-1
        
        if plus_di > minus_di:
            return SignalDirection.BULLISH, strength
        elif minus_di > plus_di:
            return SignalDirection.BEARISH, -strength
        
        return SignalDirection.NEUTRAL, 0.0
    
    def _get_trend_strength(self, adx: float) -> str:
        if adx >= 50:
            return "very_strong"
        elif adx >= 25:
            return "strong"
        elif adx >= 20:
            return "moderate"
        else:
            return "weak"
    
    def _get_description(self, adx: float, plus_di: float, minus_di: float) -> str:
        strength = self._get_trend_strength(adx)
        
        if strength == "weak":
            return f"ADX at {adx:.1f} indicates no clear trend - range-bound market"
        
        direction = "bullish" if plus_di > minus_di else "bearish"
        
        if strength == "very_strong":
            return f"ADX at {adx:.1f} shows very strong {direction} trend - trend following favored"
        elif strength == "strong":
            return f"ADX at {adx:.1f} shows strong {direction} trend"
        else:
            return f"ADX at {adx:.1f} shows moderate {direction} trend"
