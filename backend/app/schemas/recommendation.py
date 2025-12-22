"""
Recommendation-related Pydantic schemas for the NSE Trader API.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class RecommendationAction(str, Enum):
    """Recommendation action types."""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"
    AVOID = "AVOID"  # Special case for stocks with serious issues


class TimeHorizon(str, Enum):
    """Investment time horizons."""
    SHORT_TERM = "short_term"    # 1-5 days
    SWING = "swing"              # 1-4 weeks
    LONG_TERM = "long_term"      # 3+ months


class SignalType(str, Enum):
    """Types of trading signals."""
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    LIQUIDITY = "liquidity"
    MARKET_REGIME = "market_regime"
    RISK = "risk"
    COMPOSITE = "composite"


class RiskLevel(str, Enum):
    """Risk level categories."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class Signal(BaseModel):
    """Individual trading signal from an indicator or analysis."""
    name: str = Field(..., description="Signal name (e.g., 'RSI_OVERSOLD')")
    type: SignalType = Field(..., description="Signal category")
    direction: str = Field(..., description="bullish, bearish, or neutral")
    strength: float = Field(..., ge=-1, le=1, description="Signal strength -1 to 1")
    value: Optional[float] = Field(None, description="Raw indicator value")
    threshold: Optional[str] = Field(None, description="Threshold description")
    plain_english: str = Field(..., description="Human-readable explanation")
    confidence: float = Field(..., ge=0, le=1, description="Signal confidence 0-1")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RiskMetrics(BaseModel):
    """Risk metrics for a stock."""
    volatility_20d: float = Field(..., description="20-day annualized volatility")
    volatility_60d: Optional[float] = Field(None, description="60-day annualized volatility")
    max_drawdown_90d: float = Field(..., description="Maximum drawdown in last 90 days")
    beta: Optional[float] = Field(None, description="Beta to ASI index")
    sharpe_ratio: Optional[float] = Field(None, description="Sharpe ratio")
    sortino_ratio: Optional[float] = Field(None, description="Sortino ratio (downside)")
    value_at_risk_95: Optional[float] = Field(None, description="95% VaR daily")
    downside_deviation: Optional[float] = Field(None, description="Downside deviation")
    risk_level: RiskLevel = Field(..., description="Overall risk category")


class EntryExitPoints(BaseModel):
    """Suggested entry and exit points for a trade."""
    entry_price: float = Field(..., description="Suggested entry price")
    entry_zone_low: float = Field(..., description="Lower bound of entry zone")
    entry_zone_high: float = Field(..., description="Upper bound of entry zone")
    stop_loss: float = Field(..., description="Suggested stop loss price")
    stop_loss_percent: float = Field(..., description="Stop loss as percentage")
    target_1: float = Field(..., description="First price target")
    target_2: Optional[float] = Field(None, description="Second price target")
    target_3: Optional[float] = Field(None, description="Third price target")
    risk_reward_ratio: float = Field(..., description="Risk/reward ratio to first target")
    position_size_suggestion: Optional[str] = Field(None, description="Position sizing guidance")


class TechnicalIndicators(BaseModel):
    """Technical indicator values for a stock."""
    # Trend indicators
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    ema_50: Optional[float] = None
    
    # Momentum indicators
    rsi_14: Optional[float] = None
    rsi_signal: Optional[str] = None  # oversold, neutral, overbought
    stochastic_k: Optional[float] = None
    stochastic_d: Optional[float] = None
    
    # MACD
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    macd_trend: Optional[str] = None  # bullish, bearish, neutral
    
    # Volatility
    atr_14: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_middle: Optional[float] = None
    bollinger_lower: Optional[float] = None
    bollinger_bandwidth: Optional[float] = None
    
    # Volume
    obv: Optional[float] = None
    obv_trend: Optional[str] = None
    volume_sma_20: Optional[float] = None
    volume_ratio: Optional[float] = None  # current volume / avg volume
    
    # Trend strength
    adx: Optional[float] = None
    adx_trend: Optional[str] = None  # strong, moderate, weak, no_trend
    
    # Price position
    price_vs_sma_50: Optional[float] = None  # % above/below
    price_vs_sma_200: Optional[float] = None
    distance_from_high: Optional[float] = None  # % from 52-week high
    distance_from_low: Optional[float] = None   # % from 52-week low


class Recommendation(BaseModel):
    """Complete recommendation for a stock."""
    symbol: str
    name: str
    action: RecommendationAction
    horizon: TimeHorizon
    confidence: float = Field(..., ge=0, le=100, description="Confidence percentage 0-100")
    
    # Supporting data
    signals: List[Signal] = Field(default_factory=list)
    risk_metrics: RiskMetrics
    entry_exit: Optional[EntryExitPoints] = None
    technical_indicators: Optional[TechnicalIndicators] = None
    
    # Explanations
    primary_reason: str = Field(..., description="Main reason for recommendation")
    supporting_reasons: List[str] = Field(default_factory=list)
    risk_warnings: List[str] = Field(default_factory=list)
    explanation: str = Field(..., description="Full human-readable explanation")
    
    # Nigerian market specifics
    liquidity_warning: Optional[str] = None
    corporate_action_alert: Optional[str] = None
    sector_context: Optional[str] = None
    
    # Metadata
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    valid_until: Optional[datetime] = None
    historical_accuracy: Optional[float] = Field(None, description="Historical accuracy of similar signals")
    
    class Config:
        from_attributes = True


class RecommendationSummary(BaseModel):
    """Lightweight recommendation for list views."""
    symbol: str
    name: str
    action: RecommendationAction
    horizon: TimeHorizon
    confidence: float
    primary_reason: str
    risk_level: RiskLevel
    liquidity_rating: str
    current_price: float
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None


class RecommendationRequest(BaseModel):
    """Request parameters for generating recommendations."""
    symbol: Optional[str] = Field(None, description="Specific stock symbol")
    horizon: TimeHorizon = Field(default=TimeHorizon.SWING)
    include_all_horizons: bool = Field(default=False)
    min_liquidity: Optional[str] = Field(None, description="Minimum liquidity rating")
    sectors: Optional[List[str]] = Field(None, description="Filter by sectors")
    risk_tolerance: Optional[RiskLevel] = Field(None, description="Max risk level")
    limit: int = Field(default=10, ge=1, le=50)


class BacktestResult(BaseModel):
    """Backtesting results for a recommendation pattern."""
    pattern_name: str
    total_signals: int
    winning_signals: int
    losing_signals: int
    win_rate: float
    avg_profit_percent: float
    avg_loss_percent: float
    max_profit_percent: float
    max_loss_percent: float
    profit_factor: float
    avg_holding_days: float
    sample_period_start: datetime
    sample_period_end: datetime
