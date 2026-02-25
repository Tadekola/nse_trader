"""
Provenance Completeness Enforcement Middleware (P3-3).

Inspects JSON responses from recommendation/signal endpoints and asserts
that all required provenance fields are present.

Required provenance fields on any recommendation/signal data item:
  - confidence_score   (float, 0-1)
  - status             ("ACTIVE" / "SUPPRESSED" / "NO_TRADE")
  - data_confidence    (dict with sub-scores) OR confidence (float)

When a response fails the provenance check:
  - DEV mode (ENV != "production"): returns HTTP 500 with diagnostic detail
  - PROD mode: rewrites the response to a NO_TRADE fail-safe and writes
    an audit_event

An audit_event is always written on provenance failure regardless of mode.

Configuration:
  PROVENANCE_ENFORCEMENT = "on" | "off"   (default: "on")
  ENV = "production" | "development"      (default: "development")

The middleware only applies to paths under /api/v1/recommendations.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Paths that require provenance enforcement
ENFORCED_PATH_PREFIXES = (
    "/api/v1/recommendations",
)

# Required fields at the item level (each recommendation dict)
REQUIRED_ITEM_FIELDS: Set[str] = {
    "confidence_score",
    "status",
}

# At least one of these must be present for provenance depth
PROVENANCE_DEPTH_FIELDS: Set[str] = {
    "data_confidence",
    "confidence",
    "bias_signal",
}


def _check_item_provenance(item: Dict[str, Any]) -> List[str]:
    """
    Check a single recommendation/signal dict for provenance completeness.

    Returns a list of violation descriptions (empty = pass).
    """
    violations: List[str] = []

    for field in REQUIRED_ITEM_FIELDS:
        if field not in item or item[field] is None:
            violations.append(f"missing required field '{field}'")

    # At least one depth field must be present
    if not any(item.get(f) is not None for f in PROVENANCE_DEPTH_FIELDS):
        violations.append(
            f"missing all provenance depth fields ({', '.join(sorted(PROVENANCE_DEPTH_FIELDS))})"
        )

    return violations


def _extract_items(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract recommendation/signal items from a response body.

    Handles:
      - {"data": [...]}          (list response)
      - {"data": {<single>}}     (single response)
      - {"recommendations": {horizon: {...}}}  (all-horizons)
    """
    items: List[Dict[str, Any]] = []

    data = body.get("data")
    if isinstance(data, list):
        items.extend(d for d in data if isinstance(d, dict))
    elif isinstance(data, dict):
        items.append(data)

    recs = body.get("recommendations")
    if isinstance(recs, dict):
        for v in recs.values():
            if isinstance(v, dict):
                items.append(v)

    return items


def _build_no_trade_response(
    path: str, violations: List[str]
) -> Dict[str, Any]:
    """Build a NO_TRADE fail-safe response body."""
    return {
        "success": True,
        "data": {
            "status": "NO_TRADE",
            "action": "HOLD",
            "confidence_score": 0.0,
            "confidence": 0.0,
            "bias_direction": "neutral",
            "bias_probability": None,
            "bias_label": "Neutral Bias",
            "suppression_reason": "Provenance enforcement: " + "; ".join(violations),
            "data_confidence": None,
        },
        "_provenance_enforcement": {
            "enforced": True,
            "violations": violations,
            "path": path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


def _build_audit_event(
    path: str, violations: List[str], mode: str
) -> Dict[str, Any]:
    """Build an audit event dict for provenance failure."""
    return {
        "component": "provenance_enforcement",
        "event_type": "PROVENANCE_VIOLATION",
        "level": "ERROR",
        "message": f"Provenance check failed on {path}: {'; '.join(violations)}",
        "payload": {
            "path": path,
            "violations": violations,
            "mode": mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


class ProvenanceEnforcementMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces provenance completeness on recommendation responses.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Only enforce on recommendation paths
        if not any(path.startswith(p) for p in ENFORCED_PATH_PREFIXES):
            return await call_next(request)

        # Skip if enforcement is disabled
        enforcement = os.environ.get("PROVENANCE_ENFORCEMENT", "on").lower()
        if enforcement == "off":
            return await call_next(request)

        response = await call_next(request)

        # Only check JSON 200 responses
        if response.status_code != 200:
            return response

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # Read the response body
        body_bytes = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, bytes):
                body_bytes += chunk
            else:
                body_bytes += chunk.encode("utf-8")

        try:
            body = json.loads(body_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

        # Extract and check items
        items = _extract_items(body)

        # Skip check if no items found (e.g., market-regime endpoint)
        if not items:
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type="application/json",
            )

        all_violations: List[str] = []
        for item in items:
            violations = _check_item_provenance(item)
            all_violations.extend(violations)

        if not all_violations:
            # Pass — return original response
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type="application/json",
            )

        # ── Provenance violation detected ──

        mode = os.environ.get("ENV", "development").lower()
        audit_event = _build_audit_event(path, all_violations, mode)

        # Persist audit event (best-effort, non-blocking)
        try:
            await _persist_audit(audit_event)
        except Exception as e:
            logger.error("Failed to persist provenance audit: %s", e)

        logger.warning(
            "Provenance violation on %s: %s", path, "; ".join(all_violations)
        )

        if mode == "production":
            # PROD: NO_TRADE fail-safe
            no_trade = _build_no_trade_response(path, all_violations)
            return JSONResponse(content=no_trade, status_code=200)
        else:
            # DEV: 500 with diagnostic
            return JSONResponse(
                content={
                    "error": "provenance_enforcement_failure",
                    "detail": "Response missing required provenance fields",
                    "violations": all_violations,
                    "path": path,
                },
                status_code=500,
            )


async def _persist_audit(event: Dict[str, Any]) -> None:
    """Best-effort persist audit event."""
    try:
        from app.db.engine import get_session_factory
        from app.db.models import AuditEvent

        factory = get_session_factory()
        async with factory() as session:
            ae = AuditEvent(
                component=event["component"],
                event_type=event["event_type"],
                level=event["level"],
                message=event["message"],
                payload=event.get("payload"),
            )
            session.add(ae)
            await session.commit()
    except Exception as e:
        logger.debug("Audit persistence unavailable: %s", e)
