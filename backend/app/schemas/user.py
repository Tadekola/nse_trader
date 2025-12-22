"""
User-related Pydantic schemas for the NSE Trader API.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr
from enum import Enum


class UserType(str, Enum):
    """User experience level."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    PROFESSIONAL = "professional"


class RiskTolerance(str, Enum):
    """User's risk tolerance level."""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class InvestmentHorizon(str, Enum):
    """User's typical investment horizon."""
    DAY_TRADING = "day_trading"
    SWING_TRADING = "swing_trading"
    POSITION_TRADING = "position_trading"
    LONG_TERM = "long_term"


class UserPreferences(BaseModel):
    """User preferences for personalized experience."""
    user_type: UserType = Field(default=UserType.BEGINNER)
    risk_tolerance: RiskTolerance = Field(default=RiskTolerance.MODERATE)
    investment_horizon: InvestmentHorizon = Field(default=InvestmentHorizon.SWING_TRADING)
    
    # Display preferences
    show_advanced_indicators: bool = Field(default=False)
    default_chart_type: str = Field(default="candlestick")
    show_educational_tips: bool = Field(default=True)
    email_alerts: bool = Field(default=False)
    
    # Sector preferences
    preferred_sectors: List[str] = Field(default_factory=list)
    excluded_sectors: List[str] = Field(default_factory=list)
    
    # Risk guardrails
    max_position_percent: float = Field(default=10.0, description="Max % of portfolio per stock")
    min_liquidity_rating: str = Field(default="medium")
    
    # Portfolio size for position sizing
    stated_portfolio_size: Optional[float] = Field(None, description="Stated portfolio in Naira")


class WatchlistItem(BaseModel):
    """Stock in a user's watchlist."""
    symbol: str
    name: str
    added_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None
    target_price: Optional[float] = None
    alert_price_above: Optional[float] = None
    alert_price_below: Optional[float] = None


class Watchlist(BaseModel):
    """User's watchlist."""
    id: str
    name: str
    description: Optional[str] = None
    items: List[WatchlistItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PortfolioHolding(BaseModel):
    """Individual holding in a portfolio."""
    symbol: str
    name: str
    quantity: int
    avg_cost: float
    current_price: float
    market_value: float
    gain_loss: float
    gain_loss_percent: float
    weight: float = Field(..., description="% of portfolio")
    sector: str


class Portfolio(BaseModel):
    """User's portfolio."""
    id: str
    name: str
    holdings: List[PortfolioHolding] = Field(default_factory=list)
    total_value: float
    total_cost: float
    total_gain_loss: float
    total_gain_loss_percent: float
    cash_balance: float = Field(default=0)
    
    # Diversification metrics
    sector_allocation: dict = Field(default_factory=dict)
    top_holdings_concentration: float = Field(..., description="% in top 5 holdings")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class LearningProgress(BaseModel):
    """User's learning progress in the education system."""
    completed_lessons: List[str] = Field(default_factory=list)
    current_path: Optional[str] = None
    current_lesson: Optional[str] = None
    quiz_scores: dict = Field(default_factory=dict)
    badges_earned: List[str] = Field(default_factory=list)
    total_time_spent_minutes: int = Field(default=0)
    last_activity: Optional[datetime] = None


class UserProfile(BaseModel):
    """Complete user profile."""
    id: str
    email: Optional[EmailStr] = None
    display_name: Optional[str] = None
    
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    watchlists: List[Watchlist] = Field(default_factory=list)
    portfolios: List[Portfolio] = Field(default_factory=list)
    learning_progress: LearningProgress = Field(default_factory=LearningProgress)
    
    # Account info
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    is_verified: bool = Field(default=False)
    
    class Config:
        from_attributes = True


class AlertSettings(BaseModel):
    """User alert configuration."""
    price_alerts: bool = Field(default=True)
    recommendation_alerts: bool = Field(default=True)
    corporate_action_alerts: bool = Field(default=True)
    market_regime_alerts: bool = Field(default=False)
    daily_summary: bool = Field(default=False)
    
    # Delivery preferences
    email_enabled: bool = Field(default=False)
    push_enabled: bool = Field(default=True)
    
    # Quiet hours (WAT)
    quiet_start_hour: Optional[int] = None
    quiet_end_hour: Optional[int] = None
