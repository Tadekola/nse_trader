"""
Recommendation API endpoints for NSE Trader.

Provides probabilistic directional bias signals instead of deterministic recommendations.
- Bias directions: Bullish Bias, Neutral Bias, Bearish Bias
- Bias probability: 0-100 (only for ACTIVE signals)
- SUPPRESSED signals have no probability
- NO_TRADE is a first-class state for explicit non-recommendation

Signal States:
- ACTIVE: Valid signal within TTL, actionable
- SUPPRESSED: Data quality issues prevent confident signal
- INVALID: Signal has expired (past TTL) or invalidated
- NO_TRADE: Explicit decision not to trade

Includes data confidence scoring - signals may be suppressed
when data quality is insufficient (confidence < 0.75).
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from enum import Enum

from app.services.recommendation import RecommendationService
from app.core.recommendation_engine import TimeHorizon
from app.core.explanation_generator import UserLevel

router = APIRouter(prefix="/recommendations", tags=["Recommendations"], redirect_slashes=False)

# Initialize service
recommendation_service = RecommendationService()


class HorizonParam(str, Enum):
    """Time horizon query parameter."""
    short_term = "short_term"
    swing = "swing"
    long_term = "long_term"


class UserLevelParam(str, Enum):
    """User level parameter."""
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class DataConfidenceMetrics(BaseModel):
    """Metrics for data confidence scoring."""
    price_variance_percent: float = Field(description="Price variance between sources (%)")
    volume_variance_percent: float = Field(description="Volume variance between sources (%)")
    data_age_seconds: float = Field(description="Age of the oldest data point (seconds)")
    sources_used: List[str] = Field(description="List of data sources used")


class DataConfidenceDetails(BaseModel):
    """Detailed breakdown of data confidence scoring."""
    symbol: str
    confidence_score: float = Field(ge=0.0, le=1.0, description="Overall confidence score (0.0-1.0)")
    status: str = Field(description="ACTIVE or SUPPRESSED")
    suppression_reason: Optional[str] = Field(description="Human-readable suppression reason if suppressed")
    component_scores: Dict[str, float] = Field(description="Individual component scores")
    metrics: DataConfidenceMetrics
    timestamp: str


class BiasDirection(str, Enum):
    """Probabilistic bias direction."""
    bullish = "bullish"
    neutral = "neutral"
    bearish = "bearish"


class SignalStateEnum(str, Enum):
    """
    Signal lifecycle state.
    
    ACTIVE: Valid signal within TTL, actionable
    SUPPRESSED: Data quality issues prevent confident signal
    INVALID: Signal has expired (past TTL) or invalidated
    NO_TRADE: Explicit decision not to trade (first-class state)
    """
    active = "active"
    suppressed = "suppressed"
    invalid = "invalid"
    no_trade = "no_trade"


class NoTradeDecisionResponse(BaseModel):
    """NO_TRADE decision details."""
    symbol: str
    timestamp: str
    state: str = Field(default="no_trade")
    reasons: List[str] = Field(description="List of reasons for NO_TRADE decision")
    primary_reason: str = Field(description="Primary reason for NO_TRADE")
    human_readable: str = Field(description="Human-readable explanation")
    context: Dict[str, Any] = Field(description="Context at decision time")
    thresholds_breached: Dict[str, Any] = Field(description="Thresholds that triggered NO_TRADE")


class BiasSignalResponse(BaseModel):
    """Probabilistic bias signal data."""
    bias_direction: str = Field(description="bullish | neutral | bearish")
    bias_probability: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Probability strength 0-100. NULL when suppressed."
    )
    indicator_agreement: float = Field(ge=0.0, le=1.0, description="Proportion of indicators agreeing")
    signal_magnitude: float = Field(ge=0.0, le=1.0, description="Average magnitude of aligned signals")
    data_confidence_factor: float = Field(ge=0.0, le=1.0, description="Confidence adjustment factor")
    reasoning: str = Field(description="Uncertainty-aware explanation")
    is_suppressed: bool = Field(default=False)
    suppression_reason: Optional[str] = Field(default=None)


class RecommendationData(BaseModel):
    """
    Recommendation data with probabilistic bias signals.
    
    External-facing labels use probabilistic language:
    - bias_label: "Bullish Bias", "Neutral Bias", "Bearish Bias"
    - bias_probability: 0-100 (only when status=ACTIVE)
    
    Internal 'action' field is preserved for backward compatibility
    but should not be displayed to end users.
    """
    symbol: str
    name: str
    # Internal action (preserved for backward compatibility at service layer)
    action: str = Field(description="Internal action code (not for display)")
    horizon: str
    confidence: float = Field(description="Recommendation confidence (0.0-1.0)")
    current_price: float
    primary_reason: str
    supporting_reasons: List[str]
    risk_warnings: List[str]
    explanation: str
    # Data confidence fields
    status: str = Field(default="ACTIVE", description="ACTIVE or SUPPRESSED")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Data confidence score (0.0-1.0)")
    suppression_reason: Optional[str] = Field(default=None, description="Reason for suppression if applicable")
    data_confidence: Optional[DataConfidenceDetails] = Field(default=None, description="Detailed confidence breakdown")
    # Probabilistic bias fields (external-facing)
    bias_direction: str = Field(default="neutral", description="bullish | neutral | bearish")
    bias_probability: Optional[int] = Field(
        default=None,
        description="Probability 0-100. NULL when SUPPRESSED."
    )
    bias_label: str = Field(
        default="Neutral Bias",
        description="Human-readable label: Bullish Bias, Neutral Bias, Bearish Bias"
    )
    bias_signal: Optional[BiasSignalResponse] = Field(default=None, description="Detailed bias signal")
    probabilistic_reasoning: Optional[str] = Field(default=None, description="Uncertainty-aware reasoning text")
    
    class Config:
        extra = "allow"  # Allow additional fields from the recommendation engine


class RecommendationResponse(BaseModel):
    """Single recommendation response with confidence scoring."""
    success: bool
    data: Dict[str, Any] = Field(description="Recommendation data including confidence_score and suppression_reason")


class RecommendationListResponse(BaseModel):
    """List of recommendations response with confidence scoring."""
    success: bool
    count: int
    horizon: str
    suppressed_count: int = Field(default=0, description="Number of recommendations suppressed due to low confidence")
    data: List[Dict[str, Any]] = Field(description="List of recommendations, each with confidence_score and suppression_reason")


class MarketRegimeResponse(BaseModel):
    """Market regime response."""
    success: bool
    data: dict


@router.get("", response_model=RecommendationListResponse)
async def get_top_recommendations(
    horizon: HorizonParam = Query(HorizonParam.swing, description="Investment time horizon"),
    action: Optional[str] = Query(None, description="Filter by action: BUY, SELL, HOLD"),
    sector: Optional[str] = Query(None, description="Filter by sector"),
    min_liquidity: str = Query("medium", description="Minimum liquidity: high, medium, low"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results")
):
    """
    Get top stock recommendations.
    
    Returns recommendations sorted by confidence, optionally filtered by
    action type, sector, and liquidity.
    
    Each recommendation includes:
    - confidence_score: Data quality score (0.0-1.0)
    - status: "ACTIVE" or "SUPPRESSED"
    - suppression_reason: Human-readable reason if suppressed (nullable)
    """
    # Convert horizon
    horizon_map = {
        HorizonParam.short_term: TimeHorizon.SHORT_TERM,
        HorizonParam.swing: TimeHorizon.SWING,
        HorizonParam.long_term: TimeHorizon.LONG_TERM
    }
    
    recommendations = await recommendation_service.get_top_recommendations(
        horizon=horizon_map[horizon],
        action_filter=action.upper() if action else None,
        sector_filter=sector,
        min_liquidity=min_liquidity,
        limit=limit
    )
    
    # Count suppressed recommendations
    suppressed_count = sum(1 for r in recommendations if r.get('status') == 'SUPPRESSED')
    
    return RecommendationListResponse(
        success=True,
        count=len(recommendations),
        horizon=horizon.value,
        suppressed_count=suppressed_count,
        data=recommendations
    )


@router.get("/buy", response_model=RecommendationListResponse)
async def get_buy_recommendations(
    horizon: HorizonParam = Query(HorizonParam.swing),
    limit: int = Query(5, ge=1, le=20)
):
    """
    Get top BUY recommendations.
    
    Returns stocks with BUY or STRONG_BUY recommendations,
    sorted by confidence. Suppressed recommendations are excluded.
    
    Each recommendation includes confidence_score and suppression_reason fields.
    """
    horizon_map = {
        HorizonParam.short_term: TimeHorizon.SHORT_TERM,
        HorizonParam.swing: TimeHorizon.SWING,
        HorizonParam.long_term: TimeHorizon.LONG_TERM
    }
    
    recommendations = await recommendation_service.get_buy_recommendations(
        horizon=horizon_map[horizon],
        limit=limit
    )
    
    # Filter out suppressed recommendations for buy signals
    active_recs = [r for r in recommendations if r.get('status') != 'SUPPRESSED']
    suppressed_count = len(recommendations) - len(active_recs)
    
    return RecommendationListResponse(
        success=True,
        count=len(active_recs),
        horizon=horizon.value,
        suppressed_count=suppressed_count,
        data=active_recs
    )


@router.get("/sell", response_model=RecommendationListResponse)
async def get_sell_recommendations(
    horizon: HorizonParam = Query(HorizonParam.swing),
    limit: int = Query(5, ge=1, le=20)
):
    """
    Get top SELL recommendations.
    
    Returns stocks with SELL or STRONG_SELL recommendations.
    Suppressed recommendations are excluded.
    
    Each recommendation includes confidence_score and suppression_reason fields.
    """
    horizon_map = {
        HorizonParam.short_term: TimeHorizon.SHORT_TERM,
        HorizonParam.swing: TimeHorizon.SWING,
        HorizonParam.long_term: TimeHorizon.LONG_TERM
    }
    
    recommendations = await recommendation_service.get_sell_recommendations(
        horizon=horizon_map[horizon],
        limit=limit
    )
    
    # Filter out suppressed recommendations for sell signals
    active_recs = [r for r in recommendations if r.get('status') != 'SUPPRESSED']
    suppressed_count = len(recommendations) - len(active_recs)
    
    return RecommendationListResponse(
        success=True,
        count=len(active_recs),
        horizon=horizon.value,
        suppressed_count=suppressed_count,
        data=active_recs
    )


@router.get("/market-regime", response_model=MarketRegimeResponse)
async def get_market_regime():
    """
    Get current market regime analysis.
    
    Returns the overall market condition (bull, bear, range-bound, etc.)
    along with recommended strategies and sector allocations.
    """
    try:
        regime = recommendation_service.get_market_regime()
        
        return MarketRegimeResponse(
            success=True,
            data=regime
        )
    except Exception as e:
        # Return a fallback regime when data is unavailable
        return MarketRegimeResponse(
            success=True,
            data={
                'regime': 'mean_reverting',
                'trend': 'neutral',
                'confidence': 0.5,
                'duration_days': 0,
                'recommended_strategy': 'Wait for clearer signals',
                'position_size_modifier': 0.5,
                'risk_adjustment': 1.0,
                'sectors_to_favor': [],
                'sectors_to_avoid': [],
                'warnings': [f'Data temporarily unavailable: {str(e)}'],
                'metrics': {}
            }
        )


@router.get("/{symbol}", response_model=RecommendationResponse)
async def get_stock_recommendation(
    symbol: str,
    horizon: HorizonParam = Query(HorizonParam.swing),
    user_level: UserLevelParam = Query(UserLevelParam.beginner)
):
    """
    Get recommendation for a specific stock.
    
    Returns a detailed recommendation including:
    - Action (BUY, HOLD, SELL, etc.)
    - Confidence level
    - Entry/exit points
    - Risk metrics
    - Explanation tailored to user level
    - confidence_score: Data quality score (0.0-1.0)
    - status: "ACTIVE" or "SUPPRESSED"
    - suppression_reason: Human-readable reason if suppressed (nullable)
    
    Note: If data quality is insufficient (confidence < 0.75), the recommendation
    will have status="SUPPRESSED" and action="HOLD" with explanation.
    """
    horizon_map = {
        HorizonParam.short_term: TimeHorizon.SHORT_TERM,
        HorizonParam.swing: TimeHorizon.SWING,
        HorizonParam.long_term: TimeHorizon.LONG_TERM
    }
    
    level_map = {
        UserLevelParam.beginner: UserLevel.BEGINNER,
        UserLevelParam.intermediate: UserLevel.INTERMEDIATE,
        UserLevelParam.advanced: UserLevel.ADVANCED
    }
    
    recommendation = await recommendation_service.get_recommendation(
        symbol=symbol,
        horizon=horizon_map[horizon],
        user_level=level_map[user_level]
    )
    
    if recommendation is None:
        raise HTTPException(
            status_code=404,
            detail=f"Could not generate recommendation for {symbol.upper()}"
        )
    
    return RecommendationResponse(
        success=True,
        data=recommendation
    )


@router.get("/{symbol}/all-horizons")
async def get_stock_all_horizons(
    symbol: str,
    user_level: UserLevelParam = Query(UserLevelParam.beginner)
):
    """
    Get recommendations for a stock across all time horizons.
    
    Useful for seeing how the recommendation differs based on
    investment timeframe.
    """
    import asyncio
    
    level_map = {
        UserLevelParam.beginner: UserLevel.BEGINNER,
        UserLevelParam.intermediate: UserLevel.INTERMEDIATE,
        UserLevelParam.advanced: UserLevel.ADVANCED
    }
    
    # Run all horizons concurrently
    tasks = []
    horizons = []
    
    for horizon in TimeHorizon:
        horizons.append(horizon.value)
        tasks.append(recommendation_service.get_recommendation(
            symbol=symbol,
            horizon=horizon,
            user_level=level_map[user_level]
        ))
        
    results = await asyncio.gather(*tasks)
    
    recommendations = {}
    for h_value, rec in zip(horizons, results):
        if rec:
            recommendations[h_value] = rec
    
    if not recommendations:
        raise HTTPException(
            status_code=404,
            detail=f"Could not generate recommendations for {symbol.upper()}"
        )
    
    return {
        "success": True,
        "symbol": symbol.upper(),
        "recommendations": recommendations
    }
