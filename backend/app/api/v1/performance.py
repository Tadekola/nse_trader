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


# === Paper Trading Endpoints ===

@router.get("/paper-trading")
async def get_paper_trading_status():
    """
    Get paper trading dashboard: tracked signals, evaluation status, and performance.
    """
    from app.services.signal_history import get_signal_history_store

    store = get_signal_history_store()
    all_signals = store.get_all_signals()
    counts = store.count_signals()

    evaluated = [s for s in all_signals if s.status.value == "evaluated"]

    # Compute hit rates from evaluated signals
    hit_1d = [s.hit_1d for s in evaluated if s.hit_1d is not None]
    hit_5d = [s.hit_5d for s in evaluated if s.hit_5d is not None]
    hit_20d = [s.hit_20d for s in evaluated if s.hit_20d is not None]

    ret_1d = [s.return_1d for s in evaluated if s.return_1d is not None]
    ret_5d = [s.return_5d for s in evaluated if s.return_5d is not None]
    ret_20d = [s.return_20d for s in evaluated if s.return_20d is not None]

    return {
        "signal_counts": counts,
        "hit_rates": {
            "1d": round(sum(hit_1d) / len(hit_1d), 4) if hit_1d else None,
            "5d": round(sum(hit_5d) / len(hit_5d), 4) if hit_5d else None,
            "20d": round(sum(hit_20d) / len(hit_20d), 4) if hit_20d else None,
        },
        "avg_returns": {
            "1d": round(sum(ret_1d) / len(ret_1d), 4) if ret_1d else None,
            "5d": round(sum(ret_5d) / len(ret_5d), 4) if ret_5d else None,
            "20d": round(sum(ret_20d) / len(ret_20d), 4) if ret_20d else None,
        },
        "sample_sizes": {
            "1d": len(hit_1d),
            "5d": len(hit_5d),
            "20d": len(hit_20d),
        },
        "recent_signals": [
            s.to_dict() for s in sorted(
                all_signals, key=lambda x: x.generated_at, reverse=True
            )[:10]
        ],
    }


@router.post("/paper-trading/evaluate")
async def trigger_signal_evaluation():
    """
    Manually trigger evaluation of matured pending signals.

    Normally runs hourly as a background task, but can be triggered on demand.
    """
    from app.services.signal_evaluator_job import evaluate_pending_signals
    import asyncio

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, evaluate_pending_signals)
    return result
