"""
Performance Analytics API endpoints for NSE Trader.

Phase 3 Re-enablement: These endpoints now use REAL stored historical OHLCV data.
No simulated backfills. No misleading metrics.

Endpoints:
- GET /performance/status - Check readiness and system status
- GET /performance/summary - Overall performance metrics
- GET /performance/by-direction - Hit rates by bias direction
- GET /performance/by-regime - Hit rates by market regime
- GET /performance/calibration - Calibration analysis
- GET /performance/symbol/{symbol} - Per-symbol performance
- GET /performance/signals - List tracked signals
- GET /performance/hit-rates - Simple hit rate summary

All responses include transparency fields:
- evaluated_signal_count
- unevaluated_signal_count
- unevaluated_reasons
- stale_symbols_excluded_count
"""
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse

from app.services.performance_service import (
    get_performance_service,
    PerformanceReadiness,
)

router = APIRouter(prefix="/performance", tags=["Performance Analytics"])


def _check_readiness():
    """Check if performance tracking is ready."""
    service = get_performance_service()
    status = service.get_readiness_status()
    return status.get("status") in [
        PerformanceReadiness.READY.value,
        PerformanceReadiness.PARTIALLY_READY.value
    ]


# === Status Endpoint (Always Available) ===

@router.get("/status")
async def get_performance_status():
    """
    Get the status of the performance tracking system.
    
    Returns:
    - READY: At least one symbol has sufficient non-stale history
    - PARTIALLY_READY: Some symbols ready, others not
    - NOT_READY: No symbols with sufficient history
    
    Also returns counts of ready/stale symbols and reasons if not ready.
    """
    service = get_performance_service()
    return service.get_readiness_status()


# === Performance Endpoints (Require Historical Data) ===

@router.get("/summary")
async def get_performance_summary(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get overall performance summary.
    
    Returns hit rates and average returns across all evaluated signals.
    Includes transparency about what couldn't be evaluated and why.
    """
    service = get_performance_service()
    response = service.get_performance_summary(days)
    return response.to_dict()


@router.get("/by-direction")
async def get_performance_by_direction(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get hit rates broken down by bias direction (bullish/bearish/neutral).
    
    Includes transparency about unevaluated signals.
    """
    service = get_performance_service()
    response = service.get_by_direction(days)
    return response.to_dict()


@router.get("/by-regime")
async def get_performance_by_regime(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get hit rates broken down by market regime.
    
    Includes transparency about unevaluated signals.
    """
    service = get_performance_service()
    response = service.get_by_regime(days)
    return response.to_dict()


@router.get("/calibration")
async def get_calibration_analysis(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get calibration analysis.
    
    Returns INSUFFICIENT_SAMPLE if not enough signals have been evaluated.
    Calibration measures how well predicted probabilities match actual hit rates.
    """
    service = get_performance_service()
    response = service.get_calibration_metrics(days)
    return response.to_dict()


@router.get("/symbol/{symbol}")
async def get_symbol_performance(symbol: str):
    """
    Get performance metrics for a specific stock symbol.
    
    Returns NO_SIGNALS if no signals have been tracked for this symbol.
    """
    service = get_performance_service()
    response = service.get_symbol_performance(symbol.upper())
    return response.to_dict()


@router.get("/signals")
async def list_tracked_signals(
    status: Optional[str] = Query(default=None, description="Filter by status (pending, evaluated, expired, invalidated)"),
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    direction: Optional[str] = Query(default=None, description="Filter by direction (bullish, bearish, neutral)"),
    limit: int = Query(default=50, ge=1, le=500, description="Maximum signals to return")
):
    """
    List tracked signals with optional filters.
    
    Signals are only tracked when:
    - Signal state is ACTIVE
    - Historical coverage is sufficient (>= 50 sessions)
    - Historical data is not stale
    """
    service = get_performance_service()
    response = service.list_signals(
        status=status,
        symbol=symbol,
        direction=direction,
        limit=limit
    )
    return response.to_dict()


@router.get("/signals/counts")
async def get_signal_counts():
    """
    Get counts of tracked signals by status.
    """
    service = get_performance_service()
    store = service.signal_store
    return store.count_signals()


@router.get("/signal/{signal_id}")
async def get_signal_details(signal_id: str):
    """
    Get detailed information for a specific signal.
    """
    service = get_performance_service()
    signal = service.signal_store.get_signal(signal_id)
    
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    
    # Evaluate the signal to get latest performance data
    result = service.evaluate_signal_from_storage(signal)
    
    return {
        "signal": signal.to_dict(),
        "evaluation": result.to_dict(),
    }


@router.get("/hit-rates")
async def get_hit_rate_summary(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze")
):
    """
    Get simple hit rate summary across all horizons (1d, 5d, 20d).
    
    This is a simplified view of /summary focused on hit rates.
    """
    service = get_performance_service()
    response = service.get_hit_rates(days)
    return response.to_dict()


# === Backtest Endpoint ===

@router.get("/backtest")
async def run_walk_forward_backtest(
    horizon: str = Query(default="long_term", description="Investment horizon: short_term, swing, long_term"),
    holding: int = Query(default=20, ge=1, le=60, description="Holding period in trading days"),
    top_n: int = Query(default=5, ge=1, le=20, description="Number of top picks per rebalance"),
    rebalance: int = Query(default=5, ge=1, le=20, description="Rebalance every N trading days"),
):
    """
    Run a walk-forward backtest of the recommendation engine.

    Compares engine picks against ASI (market) and equal-weight basket benchmarks.
    Returns alpha, Sharpe ratio, hit rate, max drawdown, and equity curves.
    """
    from app.services.backtester import run_backtest, BacktestConfig
    from app.core.recommendation_engine import TimeHorizon

    try:
        hz = TimeHorizon(horizon)
    except ValueError:
        raise HTTPException(400, f"Invalid horizon: {horizon}")

    config = BacktestConfig(
        warmup_sessions=60,
        rebalance_every=rebalance,
        holding_period=holding,
        top_n=top_n,
        horizon=hz,
    )

    results = run_backtest(config)
    return results.to_dict()
