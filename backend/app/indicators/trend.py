"""
Trend indicators for technical analysis.
"""
from typing import Optional
import pandas as pd
from app.indicators.base import (
    BaseIndicator, IndicatorResult, SignalDirection,
    calculate_sma, calculate_ema, calculate_macd
)


class SMAIndicator(BaseIndicator):
    """Simple Moving Average indicator."""
    
    def __init__(self, period: int = 50):
        super().__init__(f"SMA_{period}")
        self.period = period
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, self.period):
            return None
        
        close = self.clean_series(df['Close'])
        sma = calculate_sma(close, self.period)
        
        current_price = close.iloc[-1]
        current_sma = sma.iloc[-1]
        
        # Calculate distance from SMA
        distance_percent = ((current_price - current_sma) / current_sma) * 100
        
        signal, strength = self.get_signal(distance_percent)
        
        return IndicatorResult(
            name=self.name,
            value=current_sma,
            signal=signal,
            strength=strength,
            description=self._get_description(current_price, current_sma, distance_percent),
            raw_values={
                "sma": current_sma,
                "price": current_price,
                "distance_percent": distance_percent
            }
        )
    
    def get_signal(self, distance_percent: float) -> tuple[SignalDirection, float]:
        """
        Signal based on price position relative to SMA.
        
        - Above SMA = bullish
        - Below SMA = bearish
        - Strength based on distance
        """
        if distance_percent > 0:
            strength = min(distance_percent / 10, 1.0)  # Cap at 1.0
            return SignalDirection.BULLISH, strength
        elif distance_percent < 0:
            strength = max(distance_percent / 10, -1.0)  # Cap at -1.0
            return SignalDirection.BEARISH, strength
        return SignalDirection.NEUTRAL, 0.0
    
    def _get_description(self, price: float, sma: float, distance: float) -> str:
        if distance > 5:
            return f"Price is {distance:.1f}% above {self.name}, showing strong bullish momentum"
        elif distance > 0:
            return f"Price is {distance:.1f}% above {self.name}, moderately bullish"
        elif distance < -5:
            return f"Price is {abs(distance):.1f}% below {self.name}, showing bearish pressure"
        elif distance < 0:
            return f"Price is {abs(distance):.1f}% below {self.name}, moderately bearish"
        return f"Price is at {self.name}, neutral"


class EMAIndicator(BaseIndicator):
    """Exponential Moving Average indicator."""
    
    def __init__(self, period: int = 50):
        super().__init__(f"EMA_{period}")
        self.period = period
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, self.period):
            return None
        
        close = self.clean_series(df['Close'])
        ema = calculate_ema(close, self.period)
        
        current_price = close.iloc[-1]
        current_ema = ema.iloc[-1]
        
        distance_percent = ((current_price - current_ema) / current_ema) * 100
        
        signal, strength = self.get_signal(distance_percent)
        
        return IndicatorResult(
            name=self.name,
            value=current_ema,
            signal=signal,
            strength=strength,
            description=self._get_description(current_price, current_ema, distance_percent),
            raw_values={
                "ema": current_ema,
                "price": current_price,
                "distance_percent": distance_percent
            }
        )
    
    def get_signal(self, distance_percent: float) -> tuple[SignalDirection, float]:
        if distance_percent > 0:
            strength = min(distance_percent / 10, 1.0)
            return SignalDirection.BULLISH, strength
        elif distance_percent < 0:
            strength = max(distance_percent / 10, -1.0)
            return SignalDirection.BEARISH, strength
        return SignalDirection.NEUTRAL, 0.0
    
    def _get_description(self, price: float, ema: float, distance: float) -> str:
        if distance > 5:
            return f"Price is {distance:.1f}% above {self.name}, bullish trend"
        elif distance > 0:
            return f"Price is slightly above {self.name}"
        elif distance < -5:
            return f"Price is {abs(distance):.1f}% below {self.name}, bearish trend"
        elif distance < 0:
            return f"Price is slightly below {self.name}"
        return f"Price is at {self.name}"


class MACDIndicator(BaseIndicator):
    """
    MACD (Moving Average Convergence Divergence) indicator.
    
    Signals:
    - MACD above signal line = bullish
    - MACD below signal line = bearish
    - Histogram expansion = trend strengthening
    - Histogram contraction = trend weakening
    """
    
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        super().__init__("MACD")
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, self.slow + self.signal_period):
            return None
        
        close = self.clean_series(df['Close'])
        macd_line, signal_line, histogram = calculate_macd(
            close, self.fast, self.slow, self.signal_period
        )
        
        current_macd = macd_line.iloc[-1]
        current_signal = signal_line.iloc[-1]
        current_histogram = histogram.iloc[-1]
        prev_histogram = histogram.iloc[-2] if len(histogram) > 1 else 0
        
        signal, strength = self.get_signal(current_histogram)
        
        # Check for crossovers
        crossover = self._detect_crossover(macd_line, signal_line)
        
        return IndicatorResult(
            name=self.name,
            value=current_macd,
            signal=signal,
            strength=strength,
            description=self._get_description(
                current_macd, current_signal, current_histogram, 
                prev_histogram, crossover
            ),
            raw_values={
                "macd_line": current_macd,
                "signal_line": current_signal,
                "histogram": current_histogram,
                "crossover": crossover
            }
        )
    
    def get_signal(self, histogram: float) -> tuple[SignalDirection, float]:
        """Signal based on histogram (MACD - Signal)."""
        if histogram > 0:
            strength = min(histogram / 5, 1.0)  # Normalize
            return SignalDirection.BULLISH, strength
        elif histogram < 0:
            strength = max(histogram / 5, -1.0)
            return SignalDirection.BEARISH, strength
        return SignalDirection.NEUTRAL, 0.0
    
    def _detect_crossover(self, macd: pd.Series, signal: pd.Series) -> str:
        """Detect if a crossover occurred in the last 3 periods."""
        if len(macd) < 3:
            return "none"
        
        # Check last 3 periods for crossover
        for i in range(-3, 0):
            prev_diff = macd.iloc[i-1] - signal.iloc[i-1]
            curr_diff = macd.iloc[i] - signal.iloc[i]
            
            if prev_diff < 0 and curr_diff > 0:
                return "bullish_crossover"
            elif prev_diff > 0 and curr_diff < 0:
                return "bearish_crossover"
        
        return "none"
    
    def _get_description(
        self, macd: float, signal: float, hist: float, 
        prev_hist: float, crossover: str
    ) -> str:
        if crossover == "bullish_crossover":
            return "MACD bullish crossover detected - potential buy signal"
        elif crossover == "bearish_crossover":
            return "MACD bearish crossover detected - potential sell signal"
        
        momentum_change = "strengthening" if abs(hist) > abs(prev_hist) else "weakening"
        
        if hist > 0:
            return f"MACD is bullish, momentum is {momentum_change}"
        elif hist < 0:
            return f"MACD is bearish, momentum is {momentum_change}"
        return "MACD is neutral"


class GoldenDeathCrossIndicator(BaseIndicator):
    """
    Golden Cross / Death Cross indicator.
    
    - Golden Cross: 50 SMA crosses above 200 SMA (bullish)
    - Death Cross: 50 SMA crosses below 200 SMA (bearish)
    """
    
    def __init__(self, short_period: int = 50, long_period: int = 200):
        super().__init__("Golden_Death_Cross")
        self.short_period = short_period
        self.long_period = long_period
    
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        if not self.validate_data(df, self.long_period + 5):
            return None
        
        close = self.clean_series(df['Close'])
        sma_short = calculate_sma(close, self.short_period)
        sma_long = calculate_sma(close, self.long_period)
        
        current_short = sma_short.iloc[-1]
        current_long = sma_long.iloc[-1]
        
        # Check for crossover in last 5 days
        crossover = self._detect_crossover(sma_short, sma_long)
        
        # Calculate position
        position = "above" if current_short > current_long else "below"
        distance_percent = ((current_short - current_long) / current_long) * 100
        
        signal, strength = self.get_signal(distance_percent)
        
        return IndicatorResult(
            name=self.name,
            value=distance_percent,
            signal=signal,
            strength=strength,
            description=self._get_description(crossover, position, distance_percent),
            raw_values={
                f"sma_{self.short_period}": current_short,
                f"sma_{self.long_period}": current_long,
                "crossover": crossover,
                "distance_percent": distance_percent
            }
        )
    
    def get_signal(self, distance_percent: float) -> tuple[SignalDirection, float]:
        if distance_percent > 0:
            strength = min(distance_percent / 5, 1.0)
            return SignalDirection.BULLISH, strength
        elif distance_percent < 0:
            strength = max(distance_percent / 5, -1.0)
            return SignalDirection.BEARISH, strength
        return SignalDirection.NEUTRAL, 0.0
    
    def _detect_crossover(self, short: pd.Series, long: pd.Series) -> str:
        for i in range(-5, 0):
            if i-1 < -len(short):
                continue
            prev_diff = short.iloc[i-1] - long.iloc[i-1]
            curr_diff = short.iloc[i] - long.iloc[i]
            
            if prev_diff < 0 and curr_diff > 0:
                return "golden_cross"
            elif prev_diff > 0 and curr_diff < 0:
                return "death_cross"
        return "none"
    
    def _get_description(self, crossover: str, position: str, distance: float) -> str:
        if crossover == "golden_cross":
            return f"Golden Cross detected! {self.short_period} SMA crossed above {self.long_period} SMA - strong bullish signal"
        elif crossover == "death_cross":
            return f"Death Cross detected! {self.short_period} SMA crossed below {self.long_period} SMA - strong bearish signal"
        
        if position == "above":
            return f"{self.short_period} SMA is {abs(distance):.1f}% above {self.long_period} SMA - bullish trend intact"
        else:
            return f"{self.short_period} SMA is {abs(distance):.1f}% below {self.long_period} SMA - bearish trend intact"
