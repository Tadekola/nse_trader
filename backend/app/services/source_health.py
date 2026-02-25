"""
Source Health Service (P1-3).

Tracks per-source health metrics and exposes them for the health dashboard.
Integrates with CircuitBreakerRegistry for live breaker state.

Usage::

    svc = SourceHealthService()
    svc.record_success("ngx_official")
    svc.record_failure("ngx_official", "timeout after 10s")
    svc.record_stale("ngnmarket")

    status = svc.get_all_sources()
    # [{"name": "ngx_official", "circuit_state": "CLOSED", ...}, ...]
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.data.circuit_breaker import (
    CircuitBreakerRegistry,
    CircuitState,
    get_breaker_registry,
)

logger = logging.getLogger(__name__)


class SourceHealthService:
    """
    In-memory source health tracker with circuit breaker integration.

    State is also persisted to the source_health DB table when a DB
    session is available, but the in-memory view is always authoritative
    for the current process.
    """

    def __init__(self, registry: Optional[CircuitBreakerRegistry] = None):
        self._registry = registry or get_breaker_registry()
        self._health: Dict[str, Dict[str, Any]] = {}

    def record_success(self, source: str) -> None:
        """Record a successful call to a source."""
        self._ensure(source)
        h = self._health[source]
        h["last_success"] = datetime.now(timezone.utc)
        h["consecutive_failures"] = 0
        h["total_calls"] += 1
        h["updated_at"] = datetime.now(timezone.utc)
        self._update_error_rate(source)

        breaker = self._registry.get(source)
        breaker.record_success()

    def record_failure(self, source: str, error: Optional[str] = None) -> None:
        """Record a failed call to a source."""
        self._ensure(source)
        h = self._health[source]
        h["last_error"] = datetime.now(timezone.utc)
        h["last_error_message"] = error
        h["consecutive_failures"] += 1
        h["total_calls"] += 1
        h["total_failures"] += 1
        h["updated_at"] = datetime.now(timezone.utc)
        self._update_error_rate(source)

        breaker = self._registry.get(source)
        breaker.record_failure()

    def record_stale(self, source: str) -> None:
        """Record a stale data detection for a source."""
        self._ensure(source)
        self._health[source]["stale_count"] += 1
        self._health[source]["updated_at"] = datetime.now(timezone.utc)

    def get_source(self, source: str) -> Dict[str, Any]:
        """Get health info for a single source."""
        self._ensure(source)
        h = dict(self._health[source])
        breaker = self._registry.get(source)
        h["circuit_state"] = breaker.state.value
        h["never_called"] = h["total_calls"] == 0
        return h

    def get_all_sources(self) -> List[Dict[str, Any]]:
        """Get health info for all tracked sources + registry-only sources."""
        # Merge health-tracked and registry-registered sources
        all_sources = set(self._health.keys())
        for snap in self._registry.all_snapshots():
            all_sources.add(snap.source)

        results = []
        for source in sorted(all_sources):
            results.append(self.get_source(source))
        return results

    def overall_status(self) -> str:
        """
        Compute overall system status.

        Uses the union of health-tracked sources AND registry-registered
        breakers.  Never-called sources count as CLOSED (not UNKNOWN)
        for the status computation — their ``never_called`` flag in the
        per-source output is the place to surface that distinction.

        Returns:
          "OK"         — all sources CLOSED, no staleness
          "RECOVERING" — no sources OPEN, but ≥1 HALF_OPEN (probe in progress)
          "DEGRADED"   — any source OPEN or HALF_OPEN, or stale_count > 0
          "SAFE_MODE"  — ALL known sources OPEN / unavailable
        """
        # Merge keys from health tracking and breaker registry
        all_sources = set(self._health.keys())
        for snap in self._registry.all_snapshots():
            all_sources.add(snap.source)

        if not all_sources:
            return "OK"

        states = []
        for source in all_sources:
            breaker = self._registry.get(source)
            states.append(breaker.state)

        any_stale = any(
            self._health.get(s, {}).get("stale_count", 0) > 0
            for s in all_sources
        )

        # SAFE_MODE: every source is OPEN
        if all(s == CircuitState.OPEN for s in states):
            return "SAFE_MODE"

        # DEGRADED: any OPEN, or any stale data
        if any(s == CircuitState.OPEN for s in states) or any_stale:
            return "DEGRADED"

        # RECOVERING: no OPEN, but at least one HALF_OPEN
        if any(s == CircuitState.HALF_OPEN for s in states):
            return "RECOVERING"

        return "OK"

    def to_response(self) -> Dict[str, Any]:
        """Build the full API response payload."""
        return {
            "overall_status": self.overall_status(),
            "sources": self.get_all_sources(),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── internal ─────────────────────────────────────────────────────

    def _ensure(self, source: str) -> None:
        if source not in self._health:
            self._health[source] = {
                "name": source,
                "last_success": None,
                "last_error": None,
                "last_error_message": None,
                "consecutive_failures": 0,
                "total_calls": 0,
                "total_failures": 0,
                "error_rate": 0.0,
                "stale_count": 0,
                "circuit_state": "CLOSED",
                "updated_at": datetime.now(timezone.utc),
            }

    def _update_error_rate(self, source: str) -> None:
        h = self._health[source]
        if h["total_calls"] > 0:
            h["error_rate"] = round(
                h["total_failures"] / h["total_calls"], 4
            )
        else:
            h["error_rate"] = 0.0


# Singleton
_instance: Optional[SourceHealthService] = None


def get_source_health_service() -> SourceHealthService:
    global _instance
    if _instance is None:
        _instance = SourceHealthService()
    return _instance
