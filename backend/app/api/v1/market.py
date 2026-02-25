"""
Market Data API Endpoints

Provides real-time market data from ngnmarket.com including:
- Market snapshot (ASI, volume, market cap)
- Top gainers and losers
- Market regime information
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from app.services.ngnmarket_service import get_ngnmarket_service, NgnMarketService
from app.services.market_regime_engine import get_regime_engine

router = APIRouter(prefix="/market", tags=["Market Data"])


class MarketSnapshotResponse(BaseModel):
    """Market snapshot response."""
    success: bool
    data: Dict[str, Any]
    source: str = "ngnmarket.com"
    timestamp: str


class TrendingStockItem(BaseModel):
    """Individual trending stock."""
    symbol: str
    company_name: str
    sector: str
    last_close: float
    todays_close: float
    change: float
    change_percent: float
    rank: int


class TrendingResponse(BaseModel):
    """Trending stocks response."""
    success: bool
    date: str
    top_gainers: List[TrendingStockItem]
    top_losers: List[TrendingStockItem]
    biggest_gainer: Optional[Dict[str, Any]] = None
    biggest_loser: Optional[Dict[str, Any]] = None
    source: str = "ngnmarket.com"


class MarketBreadthResponse(BaseModel):
    """Estimated market breadth response with disclosure."""
    success: bool
    data: Dict[str, Any]
    is_estimated: bool = True
    methodology: str = "Heuristic estimation based on ASI direction, magnitude, and top gainer/loser performance asymmetry"
    warning: str = "This breadth data is NOT exchange-reported. It is estimated from available market indicators and should be used for directional guidance only."
    source: str = "ngnmarket.com (derived)"


class MarketRegimeResponse(BaseModel):
    """Market regime response with disclosure for estimated inputs."""
    success: bool
    regime: str
    confidence: float  # Rounded to 2 decimals
    trend_direction: str
    reasoning: str
    warnings: List[str]
    source: str = "ngnmarket.com + ASI analysis"
    uses_estimated_inputs: bool = True
    confidence_note: str = "Confidence is model-derived and incorporates uncertainty from estimated market breadth data."


@router.get("/snapshot", response_model=MarketSnapshotResponse)
async def get_market_snapshot():
    """
    Get current market snapshot.
    
    Returns real-time market data including:
    - All Share Index (ASI) and change
    - Total trading volume and value
    - Market capitalization
    - Number of deals
    """
    service = get_ngnmarket_service()
    
    if not service.is_available():
        raise HTTPException(status_code=503, detail="Market data service unavailable")
    
    snapshot = await service.get_market_snapshot()
    
    if not snapshot:
        raise HTTPException(status_code=502, detail="Failed to fetch market snapshot")
    
    return MarketSnapshotResponse(
        success=True,
        data=snapshot.to_dict(),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.get("/trending", response_model=TrendingResponse)
async def get_trending_stocks():
    """
    Get top gainers and losers.
    
    Returns the top 5 gaining and top 5 losing stocks
    with real-time price data from ngnmarket.com.
    """
    service = get_ngnmarket_service()
    
    if not service.is_available():
        raise HTTPException(status_code=503, detail="Market data service unavailable")
    
    trending = await service.get_trending_stocks()
    
    if not trending:
        raise HTTPException(status_code=502, detail="Failed to fetch trending stocks")
    
    return TrendingResponse(
        success=True,
        date=trending.date,
        top_gainers=[
            TrendingStockItem(
                symbol=g.symbol,
                company_name=g.company_name,
                sector=g.sector,
                last_close=g.last_close,
                todays_close=g.todays_close,
                change=g.change,
                change_percent=g.change_percent,
                rank=g.rank
            ) for g in trending.top_gainers
        ],
        top_losers=[
            TrendingStockItem(
                symbol=l.symbol,
                company_name=l.company_name,
                sector=l.sector,
                last_close=l.last_close,
                todays_close=l.todays_close,
                change=l.change,
                change_percent=l.change_percent,
                rank=l.rank
            ) for l in trending.top_losers
        ],
        biggest_gainer=trending.biggest_gainer,
        biggest_loser=trending.biggest_loser
    )


@router.get("/breadth", response_model=MarketBreadthResponse)
async def get_market_breadth():
    """
    Get market breadth data.
    
    Returns advancers/decliners calculated from actual stock data when available,
    otherwise falls back to estimation based on ASI movement.
    """
    # Try to get accurate breadth from real stock data first
    try:
        from app.services.market_data_v2 import get_market_data_service
        market_service = get_market_data_service()
        summary_result = await market_service.get_market_summary_async()
        
        if summary_result.success and summary_result.data:
            breadth_data = summary_result.data.get('breadth', {})
            advancing = breadth_data.get('advancing', 0)
            declining = breadth_data.get('declining', 0)
            unchanged = breadth_data.get('unchanged', 0)
            total = advancing + declining + unchanged
            
            if total > 0:
                # Real data available - use it
                ratio = breadth_data.get('ratio', 0.5)
                sentiment = 'bullish' if ratio > 0.6 else ('bearish' if ratio < 0.4 else 'neutral')
                
                return MarketBreadthResponse(
                    success=True,
                    data={
                        'advancing': advancing,
                        'declining': declining,
                        'unchanged': unchanged,
                        'ratio': round(ratio, 4),
                        'sentiment': sentiment,
                        'confidence': 0.95,  # High confidence for real data
                        'is_estimated': False,
                        'methodology': 'Calculated from actual stock price changes',
                        'warning': None,
                    },
                    is_estimated=False,
                    methodology="Calculated from actual stock price changes across the market",
                    warning=""
                )
    except Exception as e:
        logger.warning(f"Could not get real breadth data, falling back to estimate: {e}")
    
    # Fallback to estimation
    service = get_ngnmarket_service()
    
    if not service.is_available():
        raise HTTPException(status_code=503, detail="Market data service unavailable")
    
    breadth = await service.estimate_market_breadth()
    
    if not breadth:
        raise HTTPException(status_code=502, detail="Failed to estimate market breadth")
    
    return MarketBreadthResponse(
        success=True,
        data=breadth.to_dict()
    )


@router.get("/regime", response_model=MarketRegimeResponse)
async def get_market_regime():
    """
    Get current market regime classification.
    
    Classifies the market into one of:
    - TRENDING: Strong directional movement
    - MEAN_REVERTING: Range-bound market
    - HIGH_VOLATILITY: Elevated volatility
    - LOW_LIQUIDITY: Below-average volume
    - NEWS_DRIVEN: Event-driven market
    
    Uses real-time data from ngnmarket.com for classification.
    """
    service = get_ngnmarket_service()
    regime_engine = get_regime_engine()
    
    if not service.is_available():
        raise HTTPException(status_code=503, detail="Market data service unavailable")
    
    # Get market data for regime classification
    market_data = await service.get_market_data_for_regime()
    
    if not market_data:
        raise HTTPException(status_code=502, detail="Failed to fetch market data for regime")
    
    # Classify regime using ngnmarket data
    analysis = await regime_engine.classify_from_ngnmarket(market_data)
    
    return MarketRegimeResponse(
        success=True,
        regime=analysis.regime.value,
        confidence=round(analysis.confidence, 2),  # Limit to 2 decimal precision
        trend_direction=analysis.trend_direction.value,
        reasoning=analysis.reasoning,
        warnings=analysis.warnings
    )


@router.get("/summary")
async def get_market_summary():
    """
    Get comprehensive market summary.
    
    Returns all market data in one call:
    - Market snapshot
    - Trending stocks
    - Estimated breadth
    - Current regime
    """
    service = get_ngnmarket_service()
    regime_engine = get_regime_engine()
    
    if not service.is_available():
        raise HTTPException(status_code=503, detail="Market data service unavailable")
    
    # Fetch all data
    snapshot = await service.get_market_snapshot()
    trending = await service.get_trending_stocks()
    breadth = await service.estimate_market_breadth()
    market_data = await service.get_market_data_for_regime()
    
    # Get regime if we have market data
    regime_info = None
    if market_data:
        analysis = await regime_engine.classify_from_ngnmarket(market_data)
        regime_info = {
            "regime": analysis.regime.value,
            "confidence": round(analysis.confidence, 2),  # Limit to 2 decimals
            "trend_direction": analysis.trend_direction.value,
            "reasoning": analysis.reasoning,
            "warnings": analysis.warnings,
            "uses_estimated_inputs": True,
            "confidence_note": "Confidence is model-derived and incorporates uncertainty from estimated market breadth data."
        }
    
    # Build breadth response with disclosure
    breadth_data = None
    if breadth:
        breadth_data = {
            **breadth.to_dict(),
            "is_estimated": True,
            "methodology": "Heuristic estimation based on ASI direction, magnitude, and top gainer/loser performance asymmetry",
            "warning": "This breadth data is NOT exchange-reported. It is estimated from available market indicators."
        }
    
    return {
        "success": True,
        "snapshot": snapshot.to_dict() if snapshot else None,
        "trending": trending.to_dict() if trending else None,
        "breadth": breadth_data,
        "regime": regime_info,
        "source": "ngnmarket.com",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
