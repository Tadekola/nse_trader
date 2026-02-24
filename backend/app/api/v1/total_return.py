"""
Total Return & Corporate Actions API (Milestone A — PR3).

Endpoints:
  GET /api/v1/tickers/{symbol}/total-return
      — Adjusted close + TRI series with provenance
  GET /api/v1/tickers/{symbol}/corporate-actions
      — Corporate actions for a symbol
  GET /api/v1/tickers/{symbol}/price-discontinuities
      — Detect suspicious price jumps that may indicate unrecorded splits/bonuses

All responses include tri_quality labeling (FULL / PRICE_ONLY) and provenance.
"""

import logging
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_async_session
from app.db.models import AdjustedPrice, AuditEvent, CorporateAction, OHLCVPrice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickers", tags=["Total Return & Corporate Actions"])

# Price discontinuity threshold: >40% single-day move flags for review
DISCONTINUITY_THRESHOLD = 0.40


def _date_to_str(val):
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val


def _row_to_dict(row) -> Dict[str, Any]:
    d = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if isinstance(val, (date, datetime)):
            val = val.isoformat()
        d[col.name] = val
    return d


# ── Total Return Series ──────────────────────────────────────────────


@router.get("/{symbol}/total-return")
async def get_total_return(
    symbol: str,
    session: AsyncSession = Depends(get_async_session),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    """
    Get adjusted close + Total Return Index series for a symbol.

    Returns:
      - close_raw: unadjusted close
      - adj_close: split/bonus adjusted close
      - tri: Total Return Index (base=1000, reinvests dividends)
      - tri_quality: FULL (dividends included) or PRICE_ONLY
      - daily_return_price / daily_return_total
      - provenance metadata
    """
    sym = symbol.upper()
    stmt = select(AdjustedPrice).where(AdjustedPrice.symbol == sym)
    filters = []

    if start_date:
        filters.append(AdjustedPrice.ts >= date.fromisoformat(start_date))
    if end_date:
        filters.append(AdjustedPrice.ts <= date.fromisoformat(end_date))
    if filters:
        stmt = stmt.where(and_(*filters))

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    if total == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No adjusted price data for {sym}. Run compute-tri first.",
        )

    stmt = stmt.order_by(AdjustedPrice.ts.asc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    rows = result.scalars().all()

    # Determine overall quality for the response
    qualities = {r.tri_quality for r in rows}
    overall_quality = "FULL" if "FULL" in qualities else "PRICE_ONLY"

    data = [_row_to_dict(r) for r in rows]

    return {
        "symbol": sym,
        "total": total,
        "limit": limit,
        "offset": offset,
        "tri_quality": overall_quality,
        "data": data,
        "provenance": {
            "source": "adjusted_prices",
            "tri_quality": overall_quality,
            "note": (
                "FULL: dividends reinvested in TRI. "
                "PRICE_ONLY: no dividend data available, TRI tracks price return only."
                if overall_quality == "PRICE_ONLY" else
                "Dividends reinvested at ex-date close. Splits/bonuses reflected in adj_factor."
            ),
        },
    }


# ── Corporate Actions ────────────────────────────────────────────────


@router.get("/{symbol}/corporate-actions")
async def get_corporate_actions(
    symbol: str,
    session: AsyncSession = Depends(get_async_session),
    action_type: Optional[str] = Query(None, description="Filter: CASH_DIVIDEND, STOCK_SPLIT, BONUS_ISSUE"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get corporate actions (dividends, splits, bonuses) for a symbol."""
    sym = symbol.upper()
    stmt = select(CorporateAction).where(CorporateAction.symbol == sym)
    filters = []

    if action_type:
        filters.append(CorporateAction.action_type == action_type.upper())
    if start_date:
        filters.append(CorporateAction.ex_date >= date.fromisoformat(start_date))
    if end_date:
        filters.append(CorporateAction.ex_date <= date.fromisoformat(end_date))
    if filters:
        stmt = stmt.where(and_(*filters))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(CorporateAction.ex_date.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    rows = [_row_to_dict(r) for r in result.scalars().all()]

    return {
        "symbol": sym,
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": rows,
    }


# ── Price Discontinuity Detection ────────────────────────────────────


@router.get("/{symbol}/price-discontinuities")
async def get_price_discontinuities(
    symbol: str,
    session: AsyncSession = Depends(get_async_session),
    threshold: float = Query(DISCONTINUITY_THRESHOLD, ge=0.05, le=1.0,
                             description="Min abs daily return to flag"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """
    Detect suspicious price jumps that may indicate unrecorded splits or bonuses.

    Scans the raw OHLCV close series for single-day moves exceeding the
    threshold (default 40%). Cross-references with corporate_actions to
    distinguish explained vs unexplained jumps.

    Returns flagged dates with:
      - daily_return: the raw price change
      - has_corporate_action: whether a matching action exists
      - status: "EXPLAINED" or "UNEXPLAINED"
    """
    sym = symbol.upper()

    # Fetch raw prices
    price_stmt = select(OHLCVPrice).where(OHLCVPrice.symbol == sym)
    if start_date:
        price_stmt = price_stmt.where(OHLCVPrice.ts >= date.fromisoformat(start_date))
    if end_date:
        price_stmt = price_stmt.where(OHLCVPrice.ts <= date.fromisoformat(end_date))
    price_stmt = price_stmt.order_by(OHLCVPrice.ts.asc())

    price_rows = (await session.execute(price_stmt)).scalars().all()

    if len(price_rows) < 2:
        return {"symbol": sym, "discontinuities": [], "total": 0}

    # Fetch splits/bonuses for cross-reference
    action_stmt = select(CorporateAction).where(
        CorporateAction.symbol == sym,
        CorporateAction.action_type.in_(["STOCK_SPLIT", "BONUS_ISSUE"]),
    )
    action_rows = (await session.execute(action_stmt)).scalars().all()
    action_dates = {a.ex_date for a in action_rows}

    # Scan for discontinuities
    flags: List[Dict[str, Any]] = []
    for i in range(1, len(price_rows)):
        prev_close = price_rows[i - 1].close
        curr_close = price_rows[i].close
        if prev_close == 0:
            continue
        daily_return = (curr_close - prev_close) / prev_close

        if abs(daily_return) >= threshold:
            ts = price_rows[i].ts
            has_action = ts in action_dates
            flags.append({
                "date": _date_to_str(ts),
                "prev_close": prev_close,
                "close": curr_close,
                "daily_return": round(daily_return, 6),
                "has_corporate_action": has_action,
                "status": "EXPLAINED" if has_action else "UNEXPLAINED",
            })

    # Write audit event for unexplained discontinuities (best-effort)
    unexplained = [f for f in flags if f["status"] == "UNEXPLAINED"]
    if unexplained:
        try:
            audit = AuditEvent(
                component="corporate_actions",
                event_type="PRICE_DISCONTINUITY_DETECTED",
                level="WARN",
                message=f"{sym}: {len(unexplained)} unexplained price discontinuities detected (threshold={threshold:.0%})",
                payload={
                    "symbol": sym,
                    "threshold": threshold,
                    "unexplained_count": len(unexplained),
                    "dates": [f["date"] for f in unexplained],
                },
            )
            session.add(audit)
            await session.commit()
        except Exception as e:
            logger.warning("Failed to persist discontinuity audit event: %s", e)
            await session.rollback()

    return {
        "symbol": sym,
        "threshold": threshold,
        "total": len(flags),
        "unexplained_count": len(unexplained),
        "discontinuities": flags,
    }
