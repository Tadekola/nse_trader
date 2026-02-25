"""
UI-Optimized API Endpoints for NSE Trader (Phase UI-2).

These endpoints are designed for frontend consumption with:
- Small, aggregated payloads
- Fast response times
- Progressive data delivery
- SSE streaming support

Endpoints:
- GET /ui/pulse - Trust banner, market snapshot, regime (< 1KB)
- GET /ui/summary - Top movers, ready counts, NO_TRADE counts
- GET /ui/stream - Server-Sent Events for real-time updates
"""
import asyncio
import json
import logging
from typing import Optional, AsyncGenerator
from datetime import datetime, timezone
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.services.trust_status import get_trust_status_service, DataIntegrityLevel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ui", tags=["UI Optimized"])


@router.get("/pulse")
async def get_ui_pulse():
    """
    Get minimal market pulse data for instant first paint.
    
    This endpoint is designed to be:
    - < 1KB response
    - < 100ms latency
    - Cacheable for 10 seconds
    
    Returns only what's needed for the top banner:
    - Trust status (data integrity, readiness)
    - Market direction indicator (from real ASI data)
    - Regime badge
    
    This should be the FIRST API call on page load.
    """
    trust_service = get_trust_status_service()
    
    try:
        trust_status = trust_service.get_trust_status()
        
        # Get real ASI data and regime from ngnmarket
        market_direction = "neutral"
        asi_change = 0.0
        asi_value = 0.0
        regime = "normal"
        regime_confidence = 0.0
        
        try:
            from app.services.ngnmarket_service import get_ngnmarket_service
            from app.services.market_regime_engine import get_regime_engine
            
            ngnmarket = get_ngnmarket_service()
            regime_engine = get_regime_engine()
            
            # Get market data for regime (this includes ASI in nested snapshot)
            market_data = await ngnmarket.get_market_data_for_regime()
            if market_data:
                # Extract ASI from nested snapshot
                snapshot_data = market_data.get('snapshot', {})
                if snapshot_data:
                    asi_value = snapshot_data.get('asi', 0.0)
                    asi_change = snapshot_data.get('asi_change_percent', 0.0)
                
                # Determine direction from ASI change
                if asi_change > 0.1:
                    market_direction = "up"
                elif asi_change < -0.1:
                    market_direction = "down"
                else:
                    market_direction = "neutral"
                
                # Get regime classification
                if regime_engine:
                    analysis = await regime_engine.classify_from_ngnmarket(market_data)
                    regime = analysis.regime.value
                    regime_confidence = round(analysis.confidence, 2)
            
            # Fallback: try snapshot directly if market_data didn't have ASI
            if asi_value == 0 and ngnmarket.is_available():
                snapshot = await ngnmarket.get_market_snapshot()
                if snapshot:
                    asi_change = snapshot.asi_change_percent
                    asi_value = snapshot.asi
        except Exception as e:
            logger.warning(f"Could not fetch market data for pulse: {e}")
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trust": {
                "integrity": trust_status.data_integrity.value,
                "readiness": trust_status.performance_readiness.value,
                "banner": trust_status.get_banner_message(),
                "active_sources": trust_status.active_sources,
                "has_issues": (
                    trust_status.data_integrity != DataIntegrityLevel.HIGH or
                    trust_status.stale_data_present
                ),
            },
            "market": {
                "direction": market_direction,
                "asi": asi_value,
                "asi_change_pct": asi_change,
                "regime": regime,
                "regime_confidence": regime_confidence,
            },
            "counts": {
                "symbols_ready": trust_status.symbols_ready_for_trading,
                "symbols_total": trust_status.symbols_with_history,
            },
            "_meta": {
                "cache_seconds": 10,
                "endpoint": "pulse",
            }
        }
    except Exception as e:
        logger.error("Error in /ui/pulse: %s", e)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trust": {
                "integrity": "DEGRADED",
                "readiness": "NOT_READY",
                "banner": "System initializing...",
                "has_issues": True,
            },
            "market": {
                "direction": "neutral",
                "asi_change_pct": 0.0,
                "regime": "unknown",
                "regime_confidence": 0.0,
            },
            "counts": {
                "symbols_ready": 0,
                "symbols_total": 0,
            },
            "_meta": {
                "cache_seconds": 5,
                "endpoint": "pulse",
                "error": str(e),
            }
        }


@router.get("/summary")
async def get_ui_summary(
    limit: int = Query(default=5, ge=1, le=20, description="Number of movers to return")
):
    """
    Get market summary for the actionable layer.
    
    This endpoint provides:
    - Top gainers (by % change)
    - Top losers (by % change)
    - Ready vs NO_TRADE symbol counts
    - Sector breakdown (simplified)
    
    Designed for Layer 2 rendering after pulse data loads.
    """
    try:
        # Use MarketDataServiceV2 for multi-tier fallback
        from app.services.market_data_v2 import get_market_data_service
        
        service = get_market_data_service()
        
        # Get market data (with fallback)
        try:
            result = await service.get_all_stocks_async()
            stocks = result.data if result.success else []
        except Exception:
            stocks = []
        
        # Calculate movers
        gainers = []
        losers = []
        
        if stocks:
            # Sort by change percent (stocks are dicts from MarketDataServiceV2)
            sorted_stocks = sorted(
                [s for s in stocks if s.get('change_percent') is not None],
                key=lambda x: x.get('change_percent') or 0,
                reverse=True
            )
            
            # Top gainers
            gainers = [
                {
                    "symbol": s.get('symbol'),
                    "name": (s.get('name') or s.get('symbol', ''))[:20],
                    "price": s.get('price'),
                    "change_pct": round(s.get('change_percent') or 0, 2),
                    "volume": s.get('volume') or 0,
                }
                for s in sorted_stocks[:limit]
                if (s.get('change_percent') or 0) > 0
            ]
            
            # Top losers
            losers = [
                {
                    "symbol": s.get('symbol'),
                    "name": (s.get('name') or s.get('symbol', ''))[:20],
                    "price": s.get('price'),
                    "change_pct": round(s.get('change_percent') or 0, 2),
                    "volume": s.get('volume') or 0,
                }
                for s in reversed(sorted_stocks[-limit:])
                if (s.get('change_percent') or 0) < 0
            ]
        
        # Get trust status for counts
        trust_service = get_trust_status_service()
        trust_status = trust_service.get_trust_status()
        
        # Calculate breadth (stocks are dicts)
        advancing = len([s for s in stocks if (s.get('change_percent') or 0) > 0])
        declining = len([s for s in stocks if (s.get('change_percent') or 0) < 0])
        unchanged = len(stocks) - advancing - declining
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "movers": {
                "gainers": gainers,
                "losers": losers,
            },
            "breadth": {
                "advancing": advancing,
                "declining": declining,
                "unchanged": unchanged,
                "total": len(stocks),
                "ratio": round(advancing / declining, 2) if declining > 0 else advancing,
            },
            "readiness": {
                "symbols_ready": trust_status.symbols_ready_for_trading,
                "symbols_with_data": trust_status.symbols_with_history,
                "no_trade_count": max(0, len(stocks) - trust_status.symbols_ready_for_trading),
            },
            "_meta": {
                "cache_seconds": 30,
                "endpoint": "summary",
            }
        }
    except Exception as e:
        logger.error("Error in /ui/summary: %s", e)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "movers": {"gainers": [], "losers": []},
            "breadth": {"advancing": 0, "declining": 0, "unchanged": 0, "total": 0, "ratio": 0},
            "readiness": {"symbols_ready": 0, "symbols_with_data": 0, "no_trade_count": 0},
            "_meta": {"cache_seconds": 10, "endpoint": "summary", "error": str(e)}
        }


@router.get("/stock/{symbol}")
async def get_ui_stock_detail(symbol: str):
    """
    Get detailed stock data for Layer 3 (lazy-loaded detail view).
    
    This endpoint is called when a user clicks on a stock.
    It provides full technical indicators and analysis.
    """
    try:
        from app.services.market_data_v2 import get_market_data_service
        from app.services.historical_coverage import get_historical_coverage_service
        
        service = get_market_data_service()
        coverage_service = get_historical_coverage_service()
        
        # Get stock data (with fallback)
        result = await service.get_stock_async(symbol.upper())
        
        if not result.success or not result.data:
            return {
                "status": "NOT_FOUND",
                "symbol": symbol.upper(),
                "message": f"Stock {symbol} not found",
            }
        
        stock = result.data
        
        # Get historical coverage
        coverage = coverage_service.get_coverage(symbol.upper())
        
        # Determine if indicators are available
        indicators_available = coverage.is_sufficient and not coverage.is_stale
        
        return {
            "symbol": stock.get('symbol'),
            "name": stock.get('name'),
            "price": stock.get('price'),
            "change": stock.get('change'),
            "change_pct": stock.get('change_percent'),
            "volume": stock.get('volume'),
            "high": stock.get('high'),
            "low": stock.get('low'),
            "open": stock.get('open'),
            "source": result.source,  # Include source info
            "coverage": {
                "sessions_available": coverage.sessions_available,
                "is_sufficient": coverage.is_sufficient,
                "is_stale": coverage.is_stale,
                "source": coverage.source,
            },
            "indicators_available": indicators_available,
            "explanation": {
                "what_this_means": (
                    "Full technical analysis available" if indicators_available
                    else "Limited analysis - insufficient historical data"
                ),
            },
            "_meta": {
                "cache_seconds": 60,
                "endpoint": "stock_detail",
            }
        }
    except Exception as e:
        logger.error("Error in /ui/stock/%s: %s", symbol, e)
        return {
            "status": "ERROR",
            "symbol": symbol.upper(),
            "message": str(e),
        }


async def generate_sse_events() -> AsyncGenerator[str, None]:
    """Generate Server-Sent Events for real-time updates."""
    
    # Send initial connection event
    yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
    
    last_pulse = None
    
    while True:
        try:
            # Get current pulse data
            trust_service = get_trust_status_service()
            trust_status = trust_service.get_trust_status()
            
            pulse_data = {
                "type": "pulse",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trust": {
                    "integrity": trust_status.data_integrity.value,
                    "readiness": trust_status.performance_readiness.value,
                    "has_issues": (
                        trust_status.data_integrity != DataIntegrityLevel.HIGH or
                        trust_status.stale_data_present
                    ),
                },
                "counts": {
                    "symbols_ready": trust_status.symbols_ready_for_trading,
                    "symbols_total": trust_status.symbols_with_history,
                },
            }
            
            # Only send if changed
            pulse_json = json.dumps(pulse_data)
            if pulse_json != last_pulse:
                yield f"event: pulse\ndata: {pulse_json}\n\n"
                last_pulse = pulse_json
            
            # Send heartbeat every 30 seconds
            yield f"event: heartbeat\ndata: {json.dumps({'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
            
            # Wait before next update
            await asyncio.sleep(10)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("SSE error: %s", e)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            await asyncio.sleep(5)


@router.get("/stream")
async def stream_updates():
    """
    Server-Sent Events stream for real-time UI updates.
    
    Events:
    - connected: Initial connection confirmation
    - pulse: Trust/readiness status updates
    - heartbeat: Keep-alive (every 30s)
    - error: Error notifications
    
    Usage:
    ```javascript
    const events = new EventSource('/api/v1/ui/stream');
    events.addEventListener('pulse', (e) => {
      const data = JSON.parse(e.data);
      updateTrustBanner(data.trust);
    });
    ```
    """
    return StreamingResponse(
        generate_sse_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.get("/explain/{status_code}")
async def explain_status_for_ui(status_code: str):
    """
    Get user-friendly explanation for a status code.
    
    Designed for tooltip/popover display in the UI.
    Returns short, non-technical explanations.
    """
    from app.services.trust_status import get_educational_message
    
    message = get_educational_message(status_code.upper())
    
    return {
        "status_code": status_code.upper(),
        "title": _get_status_title(status_code.upper()),
        "explanation": message.get("what_this_means", ""),
        "action": message.get("user_action", ""),
        "severity": _get_status_severity(status_code.upper()),
    }


def _get_status_title(status_code: str) -> str:
    """Get human-readable title for status code."""
    titles = {
        "NO_TRADE": "No Trade Signal",
        "INSUFFICIENT_HISTORY": "Limited Data",
        "INSUFFICIENT_SAMPLE": "Building Statistics",
        "PARTIALLY_READY": "Partial Coverage",
        "NOT_READY": "Setup Required",
        "STALE_DATA": "Data Refresh Needed",
        "READY": "Fully Operational",
        "HIGH": "High Integrity",
        "MEDIUM": "Some Limitations",
        "DEGRADED": "Limited Service",
    }
    return titles.get(status_code, status_code)


def _get_status_severity(status_code: str) -> str:
    """Get severity level for UI styling."""
    severities = {
        "NO_TRADE": "info",      # Blue - informational
        "INSUFFICIENT_HISTORY": "info",
        "INSUFFICIENT_SAMPLE": "info",
        "PARTIALLY_READY": "warning",  # Amber
        "NOT_READY": "warning",
        "STALE_DATA": "warning",
        "READY": "success",      # Green
        "HIGH": "success",
        "MEDIUM": "warning",
        "DEGRADED": "error",     # Red
    }
    return severities.get(status_code, "info")
