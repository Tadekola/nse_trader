"""
Stock API endpoints for NSE Trader.

Uses multi-tier data sourcing:
- Tier 0: ngnmarket.com (primary - live data)
- Tier 1: NGX Official (backup)
- Tier 3: Simulated (last resort - clearly flagged)

Note: Apt Securities (Tier 2) has been disabled due to persistent 404 errors.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.market_data_v2 import get_market_data_service

router = APIRouter(prefix="/stocks", tags=["Stocks"])


class SourceBreakdownModel(BaseModel):
    """Source breakdown for transparency."""
    ngx_official: int = 0
    apt_securities: int = 0
    kwayisi: int = 0
    simulated: int = 0
    total: int = 0


class DataMetaModel(BaseModel):
    """Metadata about data sources and freshness."""
    source_breakdown: SourceBreakdownModel
    is_simulated: bool
    simulated_count: int
    simulated_symbols: List[str]
    last_updated: str
    fetch_time_ms: float


class StockResponse(BaseModel):
    """Stock data response."""
    symbol: str
    name: str
    price: float
    change: Optional[float] = None
    change_percent: Optional[float] = None
    volume: Optional[int] = None
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    liquidity_tier: Optional[str] = None
    source: str
    timestamp: str


class StockListResponse(BaseModel):
    """List of stocks response with source metadata and simulation disclosure."""
    success: bool
    count: int
    data: List[dict]
    source: str
    # Top-level simulation disclosure (for easy frontend consumption)
    contains_simulated: bool = False
    simulated_symbols: List[str] = []
    # Detailed metadata
    meta: Optional[Dict[str, Any]] = None


class MarketSummaryResponse(BaseModel):
    """Market summary response."""
    success: bool
    data: dict
    source: str
    meta: Optional[Dict[str, Any]] = None


@router.get("/", response_model=StockListResponse)
async def get_all_stocks(
    sector: Optional[str] = Query(None, description="Filter by sector"),
    liquidity: Optional[str] = Query(None, description="Filter by liquidity tier: high, medium, low")
):
    """
    Get all stocks or filter by sector/liquidity.
    
    Returns source metadata including:
    - source_breakdown: Count of stocks from each data source
    - is_simulated: True if ANY data is simulated (requires warning banner)
    - simulated_symbols: List of symbols using simulated data
    """
    service = get_market_data_service()
    
    if sector:
        result = await service.get_stocks_by_sector_async(sector)
    elif liquidity == "high":
        result = await service.get_high_liquidity_stocks_async()
    else:
        result = await service.get_all_stocks_async()
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    # Extract simulation info from meta for top-level disclosure
    meta = result.meta or {}
    contains_simulated = meta.get('is_simulated', False)
    simulated_symbols = meta.get('simulated_symbols', [])
    
    return StockListResponse(
        success=True,
        count=len(result.data),
        data=result.data,
        source=result.source,
        contains_simulated=contains_simulated,
        simulated_symbols=simulated_symbols,
        meta=result.meta
    )


@router.get("/search")
async def search_stocks(
    q: str = Query(..., min_length=1, description="Search query")
):
    """
    Search stocks by symbol or name.
    """
    service = get_market_data_service()
    result = service.search_stocks(q)
    return {
        "success": True,
        "query": q,
        "count": len(result.data),
        "data": result.data
    }


@router.get("/sectors")
async def get_sectors():
    """
    Get list of all sectors.
    """
    service = get_market_data_service()
    result = service.get_sectors()
    return {
        "success": True,
        "sectors": result.data
    }


@router.get("/providers")
async def get_provider_status():
    """
    Get status of all data providers.
    """
    service = get_market_data_service()
    return {
        "success": True,
        "providers": service.get_provider_status()
    }


@router.get("/market-summary", response_model=MarketSummaryResponse)
async def get_market_summary():
    """
    Get overall market summary including ASI and breadth.
    """
    service = get_market_data_service()
    result = await service.get_market_summary_async()
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return MarketSummaryResponse(
        success=True,
        data=result.data,
        source=result.source,
        meta=result.meta
    )


@router.get("/{symbol}")
async def get_stock(symbol: str):
    """
    Get detailed data for a specific stock.
    """
    service = get_market_data_service()
    result = await service.get_stock_async(symbol)
    
    if not result.success:
        raise HTTPException(status_code=404, detail=result.error)
    
    return {
        "success": True,
        "data": result.data,
        "source": result.source,
        "cached": result.cached,
        "meta": result.meta
    }


@router.get("/{symbol}/indicators")
async def get_stock_indicators(symbol: str):
    """
    Get technical indicators for a specific stock.
    """
    service = get_market_data_service()
    result = await service.get_technical_indicators_async(symbol)
    
    if not result.success:
        raise HTTPException(status_code=404, detail=result.error)
    
    return {
        "success": True,
        "symbol": symbol.upper(),
        "indicators": result.data,
        "source": result.source,
        "meta": result.meta
    }
