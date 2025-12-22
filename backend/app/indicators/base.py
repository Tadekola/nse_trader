"""
Base indicator class and utilities for technical analysis.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Union
import numpy as np
import pandas as pd
from dataclasses import dataclass
from enum import Enum


class SignalDirection(str, Enum):
    """Signal direction from an indicator."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class IndicatorResult:
    """Result from an indicator calculation."""
    name: str
    value: float
    signal: SignalDirection
    strength: float  # -1 to 1
    description: str
    raw_values: Optional[Dict[str, float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "signal": self.signal.value,
            "strength": self.strength,
            "description": self.description,
            "raw_values": self.raw_values
        }


class BaseIndicator(ABC):
    """
    Abstract base class for all technical indicators.
    
    All indicators should:
    1. Accept OHLCV data
    2. Return an IndicatorResult with signal and strength
    3. Handle edge cases (insufficient data, NaN values)
    """
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> Optional[IndicatorResult]:
        """
        Calculate the indicator value.
        
        Args:
            df: DataFrame with columns ['Open', 'High', 'Low', 'Close', 'Volume']
                 Index should be datetime
        
        Returns:
            IndicatorResult or None if calculation fails
        """
        pass
    
    @abstractmethod
    def get_signal(self, value: float) -> tuple[SignalDirection, float]:
        """
        Interpret the indicator value and return signal direction and strength.
        
        Returns:
            tuple of (SignalDirection, strength from -1 to 1)
        """
        pass
    
    def validate_data(self, df: pd.DataFrame, min_periods: int) -> bool:
        """Validate that DataFrame has sufficient data."""
        if df is None or df.empty:
            return False
        if len(df) < min_periods:
            return False
        required_columns = ['Close']
        if not all(col in df.columns for col in required_columns):
            return False
        return True
    
    def clean_series(self, series: pd.Series) -> pd.Series:
        """Clean a series by forward/backward filling NaN values."""
        return series.ffill().bfill()


def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    """Calculate Simple Moving Average."""
    return series.rolling(window=period, min_periods=1).mean()


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return series.ewm(span=period, adjust=False, min_periods=1).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index.
    
    Uses the smoothed RSI method (Wilder's smoothing).
    """
    delta = series.diff()
    
    gain = delta.copy()
    loss = delta.copy()
    
    gain[gain < 0] = 0
    loss[loss > 0] = 0
    loss = abs(loss)
    
    # Use Wilder's smoothing (same as EMA with alpha = 1/period)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range.
    """
    high = df['High']
    low = df['Low']
    close = df['Close'].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close)
    tr3 = abs(low - close)
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    return atr


def calculate_bollinger_bands(
    series: pd.Series, 
    period: int = 20, 
    num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Bollinger Bands.
    
    Returns:
        tuple of (upper_band, middle_band, lower_band)
    """
    middle = series.rolling(window=period, min_periods=1).mean()
    std = series.rolling(window=period, min_periods=1).std()
    
    upper = middle + (std * num_std)
    lower = middle - (std * num_std)
    
    return upper, middle, lower


def calculate_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate MACD (Moving Average Convergence Divergence).
    
    Returns:
        tuple of (macd_line, signal_line, histogram)
    """
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)
    
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


def calculate_stochastic(
    df: pd.DataFrame,
    k_period: int = 14,
    d_period: int = 3
) -> tuple[pd.Series, pd.Series]:
    """
    Calculate Stochastic Oscillator.
    
    Returns:
        tuple of (%K, %D)
    """
    low_min = df['Low'].rolling(window=k_period, min_periods=1).min()
    high_max = df['High'].rolling(window=k_period, min_periods=1).max()
    
    k = 100 * (df['Close'] - low_min) / (high_max - low_min)
    d = k.rolling(window=d_period, min_periods=1).mean()
    
    return k, d


def calculate_adx(df: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Average Directional Index (ADX).
    
    Returns:
        tuple of (ADX, +DI, -DI)
    """
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    # Calculate True Range
    tr = calculate_atr(df, 1)  # TR is ATR with period 1
    
    # Calculate +DM and -DM
    up_move = high.diff()
    down_move = -low.diff()
    
    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)
    
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move
    
    # Smooth with Wilder's method
    atr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/period, min_periods=period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, min_periods=period, adjust=False).mean() / atr
    
    # Calculate DX and ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    return adx, plus_di, minus_di


def calculate_obv(df: pd.DataFrame) -> pd.Series:
    """Calculate On-Balance Volume."""
    close = df['Close']
    volume = df['Volume']
    
    obv = pd.Series(index=df.index, dtype=float)
    obv.iloc[0] = volume.iloc[0]
    
    for i in range(1, len(df)):
        if close.iloc[i] > close.iloc[i-1]:
            obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
        elif close.iloc[i] < close.iloc[i-1]:
            obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i-1]
    
    return obv
