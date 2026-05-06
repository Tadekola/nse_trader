"""
Provenance completeness enforcement middleware.

Inspects JSON responses from recommendation endpoints and asserts that every
recommendation item carries the required provenance fields. In development it
fails loudly with a diagnostic 500; in production it rewrites unsafe responses
to a NO_TRADE fail-safe and records an audit event.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

ENFORCED_PATH_PREFIXES = ("/api/v1/recommendations",)

REQUIRED_ITEM_FIELDS: Set[str] = {
    "confidence_score",
    "status",
}

PROVENANCE_DEPTH_FIELDS: Set[str] = {
    "data_confidence",
    "confidence",
    "bias_signal",
}


def _check_item_provenance(item: Dict[str, Any]) -> List[str]:
    """Check a single recommendation/signal dict for provenance completeness."""
    violations: List[str] = []

    for field in REQUIRED_ITEM_FIELDS:
        if field not in item or item[field] is None:
            violations.append(f"missing required field '{field}'")

    if not any(item.get(f) is not None for f in PROVENANCE_DEPTH_FIELDS):
        violations.append(
            f"missing all provenance depth fields ({', '.join(sorted(PROVENANCE_DEPTH_FIELDS))})"
        )

    return violations


def _extract_items(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract recommendation/signal items from supported response shapes:
    {"data": [...]}, {"data": {...}}, and {"recommendations": {horizon: {...}}}.
    """
    items: List[Dict[str, Any]] = []

    data = body.get("data")
    if isinstance(data, list):
        items.extend(d for d in data if isinstance(d, dict))
    elif isinstance(data, dict):
        items.append(data)

    recs = body.get("recommendations")
    if isinstance(recs, dict):
        for value in recs.values():
            if isinstance(value, dict):
                items.append(value)

    return items


def _build_no_trade_response(path: str, violations: List[str]) -> Dict[str, Any]:
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


def _build_audit_event(path: str, violations: List[str], mode: str) -> Dict[str, Any]:
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


class ProvenanceEnforcementMiddleware:
    """
    Pure ASGI middleware for provenance enforcement.

    It buffers only recommendation JSON responses, so it avoids the request-body
    handling issues that can occur with BaseHTTPMiddleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not any(path.startswith(prefix) for prefix in ENFORCED_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return

        if os.environ.get("PROVENANCE_ENFORCEMENT", "on").lower() == "off":
            await self.app(scope, receive, send)
            return

        start_message: Optional[Message] = None
        body_chunks: list[bytes] = []

        async def capture_send(message: Message) -> None:
            nonlocal start_message
            if message["type"] == "http.response.start":
                start_message = message
                return
            if message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk:
                    body_chunks.append(chunk)
                return
            await send(message)

        await self.app(scope, receive, capture_send)

        if start_message is None:
            return

        body_bytes = b"".join(body_chunks)
        status_code = int(start_message.get("status", 500))
        headers = list(start_message.get("headers", []))
        header_map = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in headers
        }

        if status_code != 200 or "application/json" not in header_map.get("content-type", ""):
            await _send_original(send, start_message, body_bytes)
            return

        try:
            parsed_body = json.loads(body_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            await _send_original(send, start_message, body_bytes)
            return

        items = _extract_items(parsed_body)
        if not items:
            await _send_original(send, start_message, body_bytes)
            return

        all_violations: List[str] = []
        for item in items:
            all_violations.extend(_check_item_provenance(item))

        if not all_violations:
            await _send_original(send, start_message, body_bytes)
            return

        mode = os.environ.get("ENV", "development").lower()
        audit_event = _build_audit_event(path, all_violations, mode)

        try:
            await _persist_audit(audit_event)
        except Exception as exc:
            logger.error("Failed to persist provenance audit: %s", exc)

        logger.warning("Provenance violation on %s: %s", path, "; ".join(all_violations))

        if mode == "production":
            response = JSONResponse(
                content=_build_no_trade_response(path, all_violations),
                status_code=200,
            )
        else:
            response = JSONResponse(
                content={
                    "error": "provenance_enforcement_failure",
                    "detail": "Response missing required provenance fields",
                    "violations": all_violations,
                    "path": path,
                },
                status_code=500,
            )
        await response(scope, receive, send)


async def _send_original(send: Send, start_message: Message, body: bytes) -> None:
    """Send a captured response, repairing content-length after buffering."""
    raw_headers = [
        (key, value)
        for key, value in start_message.get("headers", [])
        if key.lower() != b"content-length"
    ]
    raw_headers.append((b"content-length", str(len(body)).encode("latin-1")))
    await send(
        {
            "type": "http.response.start",
            "status": start_message.get("status", 500),
            "headers": raw_headers,
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


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
    except Exception as exc:
        logger.debug("Audit persistence unavailable: %s", exc)
