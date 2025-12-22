"""
Recommendation API endpoints for NSE Trader.
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from enum import Enum

from app.services.recommendation import RecommendationService
from app.core.recommendation_engine import TimeHorizon
from app.core.explanation_generator import UserLevel

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])

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


class RecommendationResponse(BaseModel):
    """Single recommendation response."""
    success: bool
    data: dict


class RecommendationListResponse(BaseModel):
    """List of recommendations response."""
    success: bool
    count: int
    horizon: str
    data: List[dict]


class MarketRegimeResponse(BaseModel):
    """Market regime response."""
    success: bool
    data: dict


@router.get("/", response_model=RecommendationListResponse)
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
    """
    # Convert horizon
    horizon_map = {
        HorizonParam.short_term: TimeHorizon.SHORT_TERM,
        HorizonParam.swing: TimeHorizon.SWING,
        HorizonParam.long_term: TimeHorizon.LONG_TERM
    }
    
    recommendations = recommendation_service.get_top_recommendations(
        horizon=horizon_map[horizon],
        action_filter=action.upper() if action else None,
        sector_filter=sector,
        min_liquidity=min_liquidity,
        limit=limit
    )
    
    return RecommendationListResponse(
        success=True,
        count=len(recommendations),
        horizon=horizon.value,
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
    sorted by confidence.
    """
    horizon_map = {
        HorizonParam.short_term: TimeHorizon.SHORT_TERM,
        HorizonParam.swing: TimeHorizon.SWING,
        HorizonParam.long_term: TimeHorizon.LONG_TERM
    }
    
    recommendations = recommendation_service.get_buy_recommendations(
        horizon=horizon_map[horizon],
        limit=limit
    )
    
    return RecommendationListResponse(
        success=True,
        count=len(recommendations),
        horizon=horizon.value,
        data=recommendations
    )


@router.get("/sell", response_model=RecommendationListResponse)
async def get_sell_recommendations(
    horizon: HorizonParam = Query(HorizonParam.swing),
    limit: int = Query(5, ge=1, le=20)
):
    """
    Get top SELL recommendations.
    
    Returns stocks with SELL or STRONG_SELL recommendations.
    """
    horizon_map = {
        HorizonParam.short_term: TimeHorizon.SHORT_TERM,
        HorizonParam.swing: TimeHorizon.SWING,
        HorizonParam.long_term: TimeHorizon.LONG_TERM
    }
    
    recommendations = recommendation_service.get_sell_recommendations(
        horizon=horizon_map[horizon],
        limit=limit
    )
    
    return RecommendationListResponse(
        success=True,
        count=len(recommendations),
        horizon=horizon.value,
        data=recommendations
    )


@router.get("/market-regime", response_model=MarketRegimeResponse)
async def get_market_regime():
    """
    Get current market regime analysis.
    
    Returns the overall market condition (bull, bear, range-bound, etc.)
    along with recommended strategies and sector allocations.
    """
    regime = recommendation_service.get_market_regime()
    
    return MarketRegimeResponse(
        success=True,
        data=regime
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
    
    recommendation = recommendation_service.get_recommendation(
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
    level_map = {
        UserLevelParam.beginner: UserLevel.BEGINNER,
        UserLevelParam.intermediate: UserLevel.INTERMEDIATE,
        UserLevelParam.advanced: UserLevel.ADVANCED
    }
    
    recommendations = {}
    for horizon in TimeHorizon:
        rec = recommendation_service.get_recommendation(
            symbol=symbol,
            horizon=horizon,
            user_level=level_map[user_level]
        )
        if rec:
            recommendations[horizon.value] = rec
    
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
