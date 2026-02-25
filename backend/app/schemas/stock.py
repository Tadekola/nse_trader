"""
Stock-related Pydantic schemas for the NSE Trader API.
"""
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class Sector(str, Enum):
    """Nigerian Stock Exchange sectors."""
    FINANCIAL_SERVICES = "Financial Services"
    CONSUMER_GOODS = "Consumer Goods"
    INDUSTRIAL_GOODS = "Industrial Goods"
    OIL_AND_GAS = "Oil & Gas"
    ICT = "ICT"
    HEALTHCARE = "Healthcare"
    AGRICULTURE = "Agriculture"
    CONGLOMERATES = "Conglomerates"
    CONSTRUCTION = "Construction"
    SERVICES = "Services"
    NATURAL_RESOURCES = "Natural Resources"
    UNKNOWN = "Unknown"


class LiquidityRating(str, Enum):
    """Liquidity rating categories."""
    HIGH = "high"          # >₦100M daily avg volume
    MEDIUM = "medium"      # ₦10M - ₦100M daily avg volume
    LOW = "low"            # ₦1M - ₦10M daily avg volume
    VERY_LOW = "very_low"  # <₦1M daily avg volume
    FROZEN = "frozen"      # No trades in 5+ days


class DataSource(str, Enum):
    """Data sources for stock information."""
    NGX = "NGX"
    TRADINGVIEW = "TradingView"
    BOTH = "Both"
    CACHED = "Cached"


class StockBase(BaseModel):
    """Base stock information."""
    symbol: str = Field(..., description="Stock ticker symbol")
    name: str = Field(..., description="Company name")
    sector: Sector = Field(default=Sector.UNKNOWN, description="Market sector")


class StockPrice(BaseModel):
    """Current price information for a stock."""
    price: float = Field(..., description="Current price in Naira")
    open: float = Field(..., description="Opening price")
    high: float = Field(..., description="Day high")
    low: float = Field(..., description="Day low")
    close: float = Field(..., description="Previous close")
    change: float = Field(..., description="Price change")
    change_percent: float = Field(..., description="Percentage change")
    volume: int = Field(..., description="Trading volume")
    value: float = Field(..., description="Trading value in Naira")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StockFundamentals(BaseModel):
    """Fundamental data for a stock."""
    market_cap: float = Field(..., description="Market capitalization in Naira")
    pe_ratio: Optional[float] = Field(None, description="Price to Earnings ratio")
    eps: Optional[float] = Field(None, description="Earnings per Share")
    dividend_yield: Optional[float] = Field(None, description="Dividend yield percentage")
    payout_ratio: Optional[float] = Field(None, description="Dividend payout ratio")
    book_value: Optional[float] = Field(None, description="Book value per share")
    pb_ratio: Optional[float] = Field(None, description="Price to Book ratio")
    roe: Optional[float] = Field(None, description="Return on Equity")
    revenue_growth: Optional[float] = Field(None, description="Revenue growth YoY")
    debt_to_equity: Optional[float] = Field(None, description="Debt to Equity ratio")
    year_high: Optional[float] = Field(None, description="52-week high")
    year_low: Optional[float] = Field(None, description="52-week low")


class LiquidityMetrics(BaseModel):
    """Liquidity metrics for trading feasibility assessment."""
    avg_daily_volume_20d: int = Field(..., description="20-day average daily volume")
    avg_daily_value_20d: float = Field(..., description="20-day average daily value in Naira")
    days_since_last_trade: int = Field(default=0, description="Days since last trade")
    bid_ask_spread: Optional[float] = Field(None, description="Bid-ask spread percentage")
    liquidity_score: float = Field(..., ge=0, le=1, description="Liquidity score 0-1")
    liquidity_rating: LiquidityRating = Field(..., description="Liquidity category")
    estimated_impact_cost: Optional[float] = Field(None, description="Estimated price impact for ₦1M order")
    days_to_liquidate_1m: Optional[float] = Field(None, description="Estimated days to liquidate ₦1M position")


class StockValidation(BaseModel):
    """Data validation information."""
    source: DataSource = Field(..., description="Primary data source")
    sources_available: List[DataSource] = Field(default_factory=list)
    accuracy: float = Field(..., ge=0, le=1, description="Data accuracy score")
    last_validated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_stale: bool = Field(default=False, description="True if data is potentially outdated")
    warnings: List[str] = Field(default_factory=list)


class Stock(StockBase):
    """Complete stock information combining all data."""
    price_data: StockPrice
    fundamentals: Optional[StockFundamentals] = None
    liquidity: LiquidityMetrics
    validation: StockValidation
    
    class Config:
        from_attributes = True


class StockListItem(StockBase):
    """Lightweight stock item for list views."""
    price: float
    change_percent: float
    volume: int
    market_cap: float
    liquidity_rating: LiquidityRating
    sector: Sector
    
    class Config:
        from_attributes = True


class HistoricalPrice(BaseModel):
    """Historical OHLCV data point."""
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: Optional[float] = None


class HistoricalData(BaseModel):
    """Historical price data for a stock."""
    symbol: str
    data: List[HistoricalPrice]
    start_date: datetime
    end_date: datetime
    adjusted_for_splits: bool = False
    adjusted_for_dividends: bool = False
