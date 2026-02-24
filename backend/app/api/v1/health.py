"""
Health and Trust Status API endpoints for NSE Trader (Phase 5).

Provides centralized system health, data integrity, and trust indicators.
These endpoints are designed for:
- Programmatic health checks
- UI status banners
- Audit and compliance verification

All responses are designed to be transparent about system limitations
and current operational status.
"""
from fastapi import APIRouter

from app.services.trust_status import (
    get_trust_status_service,
    get_educational_message,
    DataIntegrityLevel,
)
from app.services.source_health import get_source_health_service

router = APIRouter(prefix="/health", tags=["Health & Trust"])


@router.get("/trust")
async def get_trust_status():
    """
    Get comprehensive system trust and health status.
    
    This endpoint aggregates status from all subsystems to provide
    a single source of truth for system trustworthiness.
    
    Returns:
    - data_integrity: HIGH | MEDIUM | DEGRADED
    - performance_readiness: READY | PARTIALLY_READY | NOT_READY
    - simulation_rate: 0.0 (no simulation) to 1.0 (all simulated)
    - stale_data_present: Whether any historical data is outdated
    - coverage: Symbol and session counts
    - notes: Human-readable status notes for UI display
    
    Use this endpoint to:
    - Power status banners in UI
    - Determine if performance metrics are available
    - Audit data integrity
    - Monitor system health
    """
    service = get_trust_status_service()
    status = service.get_trust_status()
    
    response = status.to_dict()
    
    # Add user-facing banner message
    response["banner_message"] = status.get_banner_message()
    response["integrity_explanation"] = status.get_integrity_explanation()
    
    return response


@router.get("/trust/banner")
async def get_trust_banner():
    """
    Get a simplified trust status for UI banner display.
    
    Returns only the essential fields needed for a status banner,
    optimized for frontend consumption.
    """
    service = get_trust_status_service()
    status = service.get_trust_status()
    
    return {
        "banner_message": status.get_banner_message(),
        "data_integrity": status.data_integrity.value,
        "performance_readiness": status.performance_readiness.value,
        "has_issues": (
            status.data_integrity != DataIntegrityLevel.HIGH or
            status.stale_data_present
        ),
        "notes": status.notes[:3],  # Top 3 notes for banner
    }


@router.get("/explain/{status_code}")
async def explain_status(status_code: str):
    """
    Get educational explanation for a status code.
    
    Helps users understand what system statuses mean and what
    actions (if any) they should take.
    
    Supported status codes:
    - NO_TRADE
    - INSUFFICIENT_HISTORY
    - INSUFFICIENT_SAMPLE
    - PARTIALLY_READY
    - NOT_READY
    - STALE_DATA
    """
    message = get_educational_message(status_code.upper())
    
    return {
        "status_code": status_code.upper(),
        **message,
    }


@router.get("/ping")
async def ping():
    """
    Simple health check endpoint.
    
    Returns 200 if the API is responsive.
    Does not check subsystem health - use /trust for that.
    """
    return {"status": "ok", "service": "nse_trader"}


@router.get("/subsystems")
async def get_subsystem_status():
    """
    Get detailed status of all subsystems.
    
    Useful for debugging and operations monitoring.
    """
    service = get_trust_status_service()
    status = service.get_trust_status()
    
    return {
        "subsystems": status.subsystem_status,
        "overall_integrity": status.data_integrity.value,
        "computed_at": status.status_computed_at.isoformat(),
    }


@router.get("/sources")
async def get_source_health():
    """
    Get per-source health status and circuit breaker state (P1-3).

    Returns:
    - overall_status: OK | DEGRADED | SAFE_MODE
    - sources: list of per-source health records with:
        name, last_success, last_error, error_rate,
        circuit_state, consecutive_failures, stale_count
    - checked_at: ISO timestamp

    Use this endpoint to:
    - Monitor data source availability
    - Detect degraded or tripped circuit breakers
    - Confirm Safe Mode activation/deactivation
    """
    svc = get_source_health_service()
    return svc.to_response()
