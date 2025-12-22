"""
Market-related Pydantic schemas for the NSE Trader API.
"""
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from enum import Enum


class MarketRegime(str, Enum):
    """Market regime classification."""
    BULL = "bull"                    # Strong uptrend
    BEAR = "bear"                    # Strong downtrend
    RANGE_BOUND = "range_bound"      # Sideways market
    HIGH_VOLATILITY = "high_volatility"  # Volatile with no clear direction
    LOW_LIQUIDITY = "low_liquidity"  # Thin trading
    CRISIS = "crisis"                # Market stress/panic


class MarketTrend(str, Enum):
    """Overall market trend direction."""
    STRONGLY_BULLISH = "strongly_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONGLY_BEARISH = "strongly_bearish"


class MarketSession(str, Enum):
    """NGX trading session status."""
    PRE_MARKET = "pre_market"        # Before 10:00 AM WAT
    OPEN = "open"                    # 10:00 AM - 2:30 PM WAT
    CLOSING_AUCTION = "closing_auction"  # 2:30 PM - 2:45 PM WAT
    CLOSED = "closed"                # After market hours
    HOLIDAY = "holiday"              # Market holiday


class SectorPerformance(BaseModel):
    """Performance metrics for a market sector."""
    sector: str
    change_percent: float
    volume: int
    value: float
    advancing: int
    declining: int
    unchanged: int
    leading_stock: Optional[str] = None
    lagging_stock: Optional[str] = None
    relative_strength: float = Field(..., description="Performance vs ASI")


class MarketBreadth(BaseModel):
    """Market breadth indicators."""
    advancing: int = Field(..., description="Number of advancing stocks")
    declining: int = Field(..., description="Number of declining stocks")
    unchanged: int = Field(..., description="Number of unchanged stocks")
    new_highs: int = Field(default=0, description="Stocks at 52-week high")
    new_lows: int = Field(default=0, description="Stocks at 52-week low")
    advance_decline_ratio: float = Field(..., description="Advance/decline ratio")
    advance_decline_line: Optional[float] = None
    breadth_thrust: Optional[float] = None
    mcclellan_oscillator: Optional[float] = None


class MarketVolume(BaseModel):
    """Market-wide volume metrics."""
    total_volume: int = Field(..., description="Total shares traded")
    total_value: float = Field(..., description="Total value traded in Naira")
    deals: int = Field(..., description="Number of deals")
    volume_vs_avg: float = Field(..., description="Volume relative to 20-day average")
    up_volume: int = Field(default=0, description="Volume in advancing stocks")
    down_volume: int = Field(default=0, description="Volume in declining stocks")
    up_down_volume_ratio: Optional[float] = None


class ASIData(BaseModel):
    """All-Share Index data."""
    value: float = Field(..., description="Current ASI value")
    change: float = Field(..., description="Point change")
    change_percent: float = Field(..., description="Percentage change")
    open: float
    high: float
    low: float
    previous_close: float
    ytd_change_percent: Optional[float] = None
    year_high: Optional[float] = None
    year_low: Optional[float] = None


class MarketRegimeAnalysis(BaseModel):
    """Detailed market regime analysis."""
    current_regime: MarketRegime
    regime_confidence: float = Field(..., ge=0, le=1)
    regime_duration_days: int
    trend: MarketTrend
    trend_strength: float = Field(..., ge=0, le=1)
    
    # Regime-specific guidance
    recommended_strategy: str
    position_sizing_modifier: float = Field(..., description="Suggested adjustment to position sizes")
    risk_adjustment: str
    sectors_to_favor: List[str] = Field(default_factory=list)
    sectors_to_avoid: List[str] = Field(default_factory=list)
    
    # Supporting data
    asi_vs_sma_50: float
    asi_vs_sma_200: float
    volatility_percentile: float
    breadth_signal: str


class MarketSummary(BaseModel):
    """Complete market summary."""
    session: MarketSession
    timestamp: datetime
    last_update: datetime
    
    # ASI Data
    asi: ASIData
    market_cap: float = Field(..., description="Total market cap in Naira")
    market_cap_change: float
    
    # Breadth & Volume
    breadth: MarketBreadth
    volume: MarketVolume
    
    # Regime Analysis
    regime: MarketRegimeAnalysis
    
    # Sector Performance
    sectors: List[SectorPerformance] = Field(default_factory=list)
    
    # Top Movers
    top_gainers: List[str] = Field(default_factory=list)
    top_losers: List[str] = Field(default_factory=list)
    most_active: List[str] = Field(default_factory=list)
    
    # Market Mood
    mood_description: str = Field(..., description="Human-readable market mood")
    sentiment_score: float = Field(..., ge=-1, le=1, description="Market sentiment -1 to 1")
    
    class Config:
        from_attributes = True


class MarketCalendarEvent(BaseModel):
    """Market calendar event (holidays, earnings, etc.)."""
    date: datetime
    event_type: str  # holiday, earnings, dividend, agm, etc.
    title: str
    description: Optional[str] = None
    affected_symbols: List[str] = Field(default_factory=list)
    market_impact: Optional[str] = None  # high, medium, low


class CorporateAction(BaseModel):
    """Corporate action affecting a stock."""
    symbol: str
    action_type: str  # dividend, bonus, rights, split, agm
    announcement_date: datetime
    effective_date: Optional[datetime] = None
    qualification_date: Optional[datetime] = None
    payment_date: Optional[datetime] = None
    
    # For dividends
    dividend_amount: Optional[float] = None
    dividend_type: Optional[str] = None  # interim, final, special
    
    # For rights/bonus
    ratio: Optional[str] = None  # e.g., "1:5" meaning 1 new share for every 5 held
    price: Optional[float] = None  # For rights issues
    
    description: str
    is_upcoming: bool = True
