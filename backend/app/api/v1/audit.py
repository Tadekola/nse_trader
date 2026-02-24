"""
Signal & Audit Queryability API (P3-2).

Endpoints for querying:
  - GET /audit/signals       — query signal records
  - GET /audit/no-trade      — query NO_TRADE events
  - GET /audit/events        — query audit_events
  - GET /audit/signals/csv   — CSV export of signals
  - GET /audit/no-trade/csv  — CSV export of NO_TRADE events
  - GET /audit/events/csv    — CSV export of audit events

All endpoints support:
  - Filtering by symbol, date range, reason_code, component, source, status
  - Pagination via limit/offset
  - Sorting by timestamp descending (default)
"""

import csv
import io
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_async_session
from app.db.models import AuditEvent, NoTradeEvent, Signal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["Audit & Signals"])

# ── Helpers ──────────────────────────────────────────────────────────

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Convert a SQLAlchemy model instance to a JSON-safe dict."""
    d: Dict[str, Any] = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if isinstance(val, (datetime, date)):
            val = val.isoformat()
        d[col.name] = val
    return d


def _build_csv(rows: List[Dict[str, Any]], fieldnames: List[str]) -> str:
    """Render a list of dicts as a CSV string."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # Flatten any nested dicts/lists to JSON strings for CSV
        flat = {}
        for k in fieldnames:
            v = row.get(k)
            if isinstance(v, (dict, list)):
                import json
                flat[k] = json.dumps(v)
            else:
                flat[k] = v
        writer.writerow(flat)
    return buf.getvalue()


# ── Signals ──────────────────────────────────────────────────────────


@router.get("/signals")
async def query_signals(
    session: AsyncSession = Depends(get_async_session),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    status: Optional[str] = Query(None, description="Filter by status (ACTIVE/SUPPRESSED/NO_TRADE)"),
    direction: Optional[str] = Query(None, description="Filter by direction (bullish/neutral/bearish)"),
    strategy: Optional[str] = Query(None, description="Filter by strategy"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    """Query signal records with filtering and pagination."""
    stmt = select(Signal)
    filters = []

    if symbol:
        filters.append(Signal.symbol == symbol.upper())
    if status:
        filters.append(Signal.status == status.upper())
    if direction:
        filters.append(Signal.direction == direction.lower())
    if strategy:
        filters.append(Signal.strategy == strategy)
    if start_date:
        filters.append(Signal.as_of >= datetime.fromisoformat(start_date))
    if end_date:
        filters.append(Signal.as_of <= datetime.fromisoformat(end_date + "T23:59:59"))

    if filters:
        stmt = stmt.where(and_(*filters))

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    # Fetch page
    stmt = stmt.order_by(Signal.as_of.desc()).limit(_clamp_limit(limit)).offset(offset)
    result = await session.execute(stmt)
    rows = [_row_to_dict(r) for r in result.scalars().all()]

    return {
        "total": total,
        "limit": _clamp_limit(limit),
        "offset": offset,
        "data": rows,
    }


@router.get("/signals/csv")
async def export_signals_csv(
    session: AsyncSession = Depends(get_async_session),
    symbol: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(MAX_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    """Export signal records as CSV."""
    stmt = select(Signal)
    filters = []
    if symbol:
        filters.append(Signal.symbol == symbol.upper())
    if status:
        filters.append(Signal.status == status.upper())
    if start_date:
        filters.append(Signal.as_of >= datetime.fromisoformat(start_date))
    if end_date:
        filters.append(Signal.as_of <= datetime.fromisoformat(end_date + "T23:59:59"))
    if filters:
        stmt = stmt.where(and_(*filters))

    stmt = stmt.order_by(Signal.as_of.desc()).limit(_clamp_limit(limit)).offset(offset)
    result = await session.execute(stmt)
    rows = [_row_to_dict(r) for r in result.scalars().all()]

    fields = [
        "id", "signal_id", "symbol", "as_of", "strategy", "horizon",
        "direction", "confidence", "bias_probability", "status",
        "params", "provenance", "created_at", "expires_at",
    ]
    content = _build_csv(rows, fields)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=signals.csv"},
    )


# ── No-Trade Events ─────────────────────────────────────────────────


@router.get("/no-trade")
async def query_no_trade(
    session: AsyncSession = Depends(get_async_session),
    symbol: Optional[str] = Query(None),
    reason_code: Optional[str] = Query(None, description="Filter by reason_code"),
    scope: Optional[str] = Query(None, description="Filter by scope (symbol/market/system)"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    """Query NO_TRADE events with filtering and pagination."""
    stmt = select(NoTradeEvent)
    filters = []

    if symbol:
        filters.append(NoTradeEvent.symbol == symbol.upper())
    if reason_code:
        filters.append(NoTradeEvent.reason_code == reason_code.upper())
    if scope:
        filters.append(NoTradeEvent.scope == scope.lower())
    if start_date:
        filters.append(NoTradeEvent.ts >= datetime.fromisoformat(start_date))
    if end_date:
        filters.append(NoTradeEvent.ts <= datetime.fromisoformat(end_date + "T23:59:59"))

    if filters:
        stmt = stmt.where(and_(*filters))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(NoTradeEvent.ts.desc()).limit(_clamp_limit(limit)).offset(offset)
    result = await session.execute(stmt)
    rows = [_row_to_dict(r) for r in result.scalars().all()]

    return {
        "total": total,
        "limit": _clamp_limit(limit),
        "offset": offset,
        "data": rows,
    }


@router.get("/no-trade/csv")
async def export_no_trade_csv(
    session: AsyncSession = Depends(get_async_session),
    symbol: Optional[str] = Query(None),
    reason_code: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(MAX_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    """Export NO_TRADE events as CSV."""
    stmt = select(NoTradeEvent)
    filters = []
    if symbol:
        filters.append(NoTradeEvent.symbol == symbol.upper())
    if reason_code:
        filters.append(NoTradeEvent.reason_code == reason_code.upper())
    if start_date:
        filters.append(NoTradeEvent.ts >= datetime.fromisoformat(start_date))
    if end_date:
        filters.append(NoTradeEvent.ts <= datetime.fromisoformat(end_date + "T23:59:59"))
    if filters:
        stmt = stmt.where(and_(*filters))

    stmt = stmt.order_by(NoTradeEvent.ts.desc()).limit(_clamp_limit(limit)).offset(offset)
    result = await session.execute(stmt)
    rows = [_row_to_dict(r) for r in result.scalars().all()]

    fields = ["id", "ts", "scope", "symbol", "reason_code", "detail", "confidence", "provenance"]
    content = _build_csv(rows, fields)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=no_trade_events.csv"},
    )


# ── Audit Events ─────────────────────────────────────────────────────


@router.get("/events")
async def query_audit_events(
    session: AsyncSession = Depends(get_async_session),
    component: Optional[str] = Query(None, description="Filter by component"),
    event_type: Optional[str] = Query(None, description="Filter by event_type"),
    level: Optional[str] = Query(None, description="Filter by level (INFO/WARN/ERROR)"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    """Query audit events with filtering and pagination."""
    stmt = select(AuditEvent)
    filters = []

    if component:
        filters.append(AuditEvent.component == component)
    if event_type:
        filters.append(AuditEvent.event_type == event_type.upper())
    if level:
        filters.append(AuditEvent.level == level.upper())
    if start_date:
        filters.append(AuditEvent.ts >= datetime.fromisoformat(start_date))
    if end_date:
        filters.append(AuditEvent.ts <= datetime.fromisoformat(end_date + "T23:59:59"))

    if filters:
        stmt = stmt.where(and_(*filters))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(AuditEvent.ts.desc()).limit(_clamp_limit(limit)).offset(offset)
    result = await session.execute(stmt)
    rows = [_row_to_dict(r) for r in result.scalars().all()]

    return {
        "total": total,
        "limit": _clamp_limit(limit),
        "offset": offset,
        "data": rows,
    }


@router.get("/events/csv")
async def export_audit_events_csv(
    session: AsyncSession = Depends(get_async_session),
    component: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(MAX_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    """Export audit events as CSV."""
    stmt = select(AuditEvent)
    filters = []
    if component:
        filters.append(AuditEvent.component == component)
    if event_type:
        filters.append(AuditEvent.event_type == event_type.upper())
    if level:
        filters.append(AuditEvent.level == level.upper())
    if start_date:
        filters.append(AuditEvent.ts >= datetime.fromisoformat(start_date))
    if end_date:
        filters.append(AuditEvent.ts <= datetime.fromisoformat(end_date + "T23:59:59"))
    if filters:
        stmt = stmt.where(and_(*filters))

    stmt = stmt.order_by(AuditEvent.ts.desc()).limit(_clamp_limit(limit)).offset(offset)
    result = await session.execute(stmt)
    rows = [_row_to_dict(r) for r in result.scalars().all()]

    fields = ["id", "ts", "component", "level", "event_type", "message", "payload"]
    content = _build_csv(rows, fields)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_events.csv"},
    )
