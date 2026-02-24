"""
Portfolio API (Milestone B — PR4).

Endpoints:
  POST /api/v1/portfolios                           — Create portfolio
  GET  /api/v1/portfolios                           — List portfolios
  GET  /api/v1/portfolios/{id}                      — Get portfolio detail
  POST /api/v1/portfolios/{id}/transactions         — Add transactions (bulk)
  GET  /api/v1/portfolios/{id}/transactions         — List transactions
  GET  /api/v1/portfolios/{id}/holdings             — Holdings as-of date
  GET  /api/v1/portfolios/{id}/performance          — Performance with reporting mode
  GET  /api/v1/portfolios/{id}/decomposition        — Return decomposition (equity/FX/inflation)
  GET  /api/v1/portfolios/{id}/summary               — Dashboard-ready portfolio snapshot
  GET  /api/v1/portfolios/{id}/timeseries             — Chart-ready daily series

Every performance response includes quality flags + provenance.
Missing FX → DEGRADED. Missing CPI → DEGRADED. Never silent.
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_async_session
from app.db.models import (
    AdjustedPrice, AuditEvent, FxRate, MacroSeries, OHLCVPrice,
    Portfolio, PortfolioTransaction,
)
from app.services.portfolio import PortfolioService
from app.services.performance import PerformanceEngine
from app.services.decomposition import DecompositionEngine
from app.services.summary import SummaryService, DataFreshness
from app.services.timeseries import TimeseriesService
from app.data.macro.fx_provider import FxRateService
from app.data.macro.cpi_provider import CpiService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolios", tags=["Portfolios"])
portfolio_svc = PortfolioService()
perf_engine = PerformanceEngine()
decomp_engine = DecompositionEngine()
summary_svc = SummaryService()
timeseries_svc = TimeseriesService()

VALID_REPORTING_MODES = {"NGN", "USD", "REAL_NGN"}


# ── Pydantic Schemas ─────────────────────────────────────────────────

class PortfolioCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    base_currency: str = Field(default="NGN", max_length=5)

class TransactionCreate(BaseModel):
    ts: str = Field(..., description="Date YYYY-MM-DD")
    tx_type: str
    symbol: Optional[str] = None
    quantity: Optional[float] = None
    price_ngn: Optional[float] = None
    amount_ngn: float
    fees_ngn: float = 0.0
    notes: Optional[str] = None

class TransactionBulk(BaseModel):
    transactions: List[TransactionCreate]


# ── Helper: row to dict ──────────────────────────────────────────────

def _row_to_dict(row) -> Dict[str, Any]:
    d = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if isinstance(val, (date, datetime)):
            val = val.isoformat()
        d[col.name] = val
    return d


# ── POST /portfolios ─────────────────────────────────────────────────

@router.post("")
async def create_portfolio(
    body: PortfolioCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new portfolio."""
    p = Portfolio(
        name=body.name,
        description=body.description,
        base_currency=body.base_currency.upper(),
    )
    session.add(p)
    await session.commit()

    # Re-query to get the auto-generated ID (avoids RETURNING limitation on SQLite)
    stmt = select(Portfolio).where(
        Portfolio.name == body.name
    ).order_by(Portfolio.created_at.desc()).limit(1)
    row = (await session.execute(stmt)).scalar_one()
    return _row_to_dict(row)


# ── GET /portfolios ──────────────────────────────────────────────────

@router.get("")
async def list_portfolios(
    session: AsyncSession = Depends(get_async_session),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List all portfolios."""
    count_stmt = select(func.count()).select_from(Portfolio)
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = select(Portfolio).order_by(Portfolio.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [_row_to_dict(r) for r in rows],
    }


# ── GET /portfolios/{id} ─────────────────────────────────────────────

@router.get("/{portfolio_id}")
async def get_portfolio(
    portfolio_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Get portfolio details."""
    row = (await session.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, f"Portfolio {portfolio_id} not found")
    return _row_to_dict(row)


# ── POST /portfolios/{id}/transactions ────────────────────────────────

@router.post("/{portfolio_id}/transactions")
async def add_transactions(
    portfolio_id: int,
    body: TransactionBulk,
    session: AsyncSession = Depends(get_async_session),
):
    """Add one or more transactions to a portfolio."""
    # Verify portfolio exists
    p = (await session.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id)
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404, f"Portfolio {portfolio_id} not found")

    added = []
    errors = []
    for i, tx in enumerate(body.transactions):
        tx_dict = tx.model_dump()
        tx_dict["ts"] = date.fromisoformat(tx.ts)
        tx_dict["tx_type"] = tx.tx_type.upper()
        if tx.symbol:
            tx_dict["symbol"] = tx.symbol.upper()

        # Validate
        val_errors = portfolio_svc.validate_transaction(tx_dict)
        if val_errors:
            errors.append({
                "index": i,
                "errors": [e.to_dict() for e in val_errors],
            })
            continue

        ptx = PortfolioTransaction(
            portfolio_id=portfolio_id,
            ts=tx_dict["ts"],
            symbol=tx_dict.get("symbol"),
            tx_type=tx_dict["tx_type"],
            quantity=tx_dict.get("quantity"),
            price_ngn=tx_dict.get("price_ngn"),
            amount_ngn=tx_dict["amount_ngn"],
            fees_ngn=tx_dict.get("fees_ngn", 0.0),
            notes=tx_dict.get("notes"),
        )
        session.add(ptx)
        added.append(i)

    if errors and not added:
        raise HTTPException(422, detail={"message": "All transactions invalid", "errors": errors})

    await session.commit()
    return {
        "added": len(added),
        "rejected": len(errors),
        "errors": errors,
    }


# ── GET /portfolios/{id}/transactions ─────────────────────────────────

@router.get("/{portfolio_id}/transactions")
async def list_transactions(
    portfolio_id: int,
    session: AsyncSession = Depends(get_async_session),
    symbol: Optional[str] = Query(None),
    tx_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List transactions for a portfolio with optional filters."""
    stmt = select(PortfolioTransaction).where(
        PortfolioTransaction.portfolio_id == portfolio_id
    )
    filters = []
    if symbol:
        filters.append(PortfolioTransaction.symbol == symbol.upper())
    if tx_type:
        filters.append(PortfolioTransaction.tx_type == tx_type.upper())
    if start_date:
        filters.append(PortfolioTransaction.ts >= date.fromisoformat(start_date))
    if end_date:
        filters.append(PortfolioTransaction.ts <= date.fromisoformat(end_date))
    if filters:
        stmt = stmt.where(and_(*filters))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(PortfolioTransaction.ts.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [_row_to_dict(r) for r in rows],
    }


# ── GET /portfolios/{id}/holdings ─────────────────────────────────────

@router.get("/{portfolio_id}/holdings")
async def get_holdings(
    portfolio_id: int,
    session: AsyncSession = Depends(get_async_session),
    as_of: Optional[str] = Query(None, description="As-of date (YYYY-MM-DD)"),
):
    """Get current holdings for a portfolio, optionally as-of a date."""
    # Fetch transactions
    stmt = select(PortfolioTransaction).where(
        PortfolioTransaction.portfolio_id == portfolio_id
    ).order_by(PortfolioTransaction.ts.asc())
    rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        raise HTTPException(404, f"No transactions for portfolio {portfolio_id}")

    txs = [
        {
            "ts": r.ts, "tx_type": r.tx_type, "symbol": r.symbol,
            "quantity": r.quantity, "price_ngn": r.price_ngn,
            "amount_ngn": r.amount_ngn, "fees_ngn": r.fees_ngn,
        }
        for r in rows
    ]

    as_of_date = date.fromisoformat(as_of) if as_of else None
    snapshot = portfolio_svc.compute_holdings(txs, as_of=as_of_date)

    # Fetch current prices for valuation
    prices = {}
    for sym in snapshot.holdings:
        price_stmt = select(AdjustedPrice).where(
            AdjustedPrice.symbol == sym
        ).order_by(AdjustedPrice.ts.desc()).limit(1)
        adj = (await session.execute(price_stmt)).scalar_one_or_none()
        if adj:
            prices[sym] = adj.adj_close
        else:
            # Fallback to raw OHLCV
            ohlcv_stmt = select(OHLCVPrice).where(
                OHLCVPrice.symbol == sym
            ).order_by(OHLCVPrice.ts.desc()).limit(1)
            ohlcv = (await session.execute(ohlcv_stmt)).scalar_one_or_none()
            if ohlcv:
                prices[sym] = ohlcv.close

    valuation = portfolio_svc.compute_valuation(snapshot, prices)
    return {
        **snapshot.to_dict(),
        "valuation": valuation.to_dict(),
    }


# ── GET /portfolios/{id}/performance ──────────────────────────────────

@router.get("/{portfolio_id}/performance")
async def get_performance(
    portfolio_id: int,
    session: AsyncSession = Depends(get_async_session),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    reporting: str = Query("NGN", description="NGN, USD, or REAL_NGN"),
):
    """
    Compute portfolio performance with multi-currency reporting.

    Quality flags in every response:
      data_mode:      TRI_FULL / PRICE_ONLY
      fx_mode:        FX_FULL / FX_MISSING / FX_NOT_REQUESTED
      inflation_mode: CPI_FULL / CPI_MISSING / CPI_NOT_REQUESTED
      overall_quality: FULL / DEGRADED
    """
    reporting = reporting.upper()
    if reporting not in VALID_REPORTING_MODES:
        raise HTTPException(400, f"Invalid reporting mode: {reporting}. Use NGN, USD, or REAL_NGN")

    # Fetch transactions
    tx_stmt = select(PortfolioTransaction).where(
        PortfolioTransaction.portfolio_id == portfolio_id
    ).order_by(PortfolioTransaction.ts.asc())
    tx_rows = (await session.execute(tx_stmt)).scalars().all()

    if not tx_rows:
        raise HTTPException(404, f"No transactions for portfolio {portfolio_id}")

    txs = [
        {
            "ts": r.ts, "tx_type": r.tx_type, "symbol": r.symbol,
            "quantity": r.quantity, "price_ngn": r.price_ngn,
            "amount_ngn": r.amount_ngn, "fees_ngn": r.fees_ngn,
        }
        for r in tx_rows
    ]

    # Determine date range
    sd = date.fromisoformat(start_date) if start_date else tx_rows[0].ts
    ed = date.fromisoformat(end_date) if end_date else date.today()

    # Fetch all symbols in portfolio
    symbols = list({r.symbol for r in tx_rows if r.symbol})

    # Build price series from AdjustedPrice (preferred) or OHLCV
    price_series: Dict[str, Dict[date, float]] = {}
    for sym in symbols:
        adj_stmt = select(AdjustedPrice).where(
            AdjustedPrice.symbol == sym,
            AdjustedPrice.ts >= sd,
            AdjustedPrice.ts <= ed,
        ).order_by(AdjustedPrice.ts.asc())
        adj_rows = (await session.execute(adj_stmt)).scalars().all()

        if adj_rows:
            price_series[sym] = {r.ts: r.adj_close for r in adj_rows}
        else:
            ohlcv_stmt = select(OHLCVPrice).where(
                OHLCVPrice.symbol == sym,
                OHLCVPrice.ts >= sd,
                OHLCVPrice.ts <= ed,
            ).order_by(OHLCVPrice.ts.asc())
            ohlcv_rows = (await session.execute(ohlcv_stmt)).scalars().all()
            if ohlcv_rows:
                price_series[sym] = {r.ts: r.close for r in ohlcv_rows}

    # Compute daily values
    daily_values = portfolio_svc.compute_daily_values(txs, price_series, sd, ed)

    if not daily_values:
        raise HTTPException(404, "No price data available for the requested date range")

    # Build cash flows for XIRR
    cash_flows = []
    for tx in txs:
        if tx["tx_type"] in ("CASH_IN", "CASH_OUT"):
            amount = tx["amount_ngn"]
            if tx["tx_type"] == "CASH_IN":
                amount = -amount  # XIRR convention: investment = negative
            else:
                amount = amount   # withdrawal = positive
            cash_flows.append({"date": tx["ts"], "amount": amount})

    # Load FX/CPI services if needed
    fx_service = None
    cpi_service = None

    if reporting == "USD":
        fx_stmt = select(FxRate).where(
            FxRate.pair == "USDNGN"
        ).order_by(FxRate.ts.asc())
        fx_rows = (await session.execute(fx_stmt)).scalars().all()
        if fx_rows:
            fx_service = FxRateService([
                {"pair": r.pair, "ts": r.ts, "rate": r.rate} for r in fx_rows
            ])

    if reporting == "REAL_NGN":
        cpi_stmt = select(MacroSeries).where(
            MacroSeries.series_name == "CPI_NGN"
        ).order_by(MacroSeries.ts.asc())
        cpi_rows = (await session.execute(cpi_stmt)).scalars().all()
        if cpi_rows:
            cpi_service = CpiService([
                {"series_name": r.series_name, "ts": r.ts, "value": r.value}
                for r in cpi_rows
            ])

    # Compute performance
    result = perf_engine.compute(
        daily_values=daily_values,
        cash_flows=cash_flows,
        reporting=reporting,
        fx_service=fx_service,
        cpi_service=cpi_service,
    )

    # Write audit event if degraded
    if result.quality.overall_quality == "DEGRADED":
        try:
            audit = AuditEvent(
                component="portfolio",
                event_type="DEGRADED_PERFORMANCE_REPORT",
                level="WARN",
                message=f"Portfolio {portfolio_id} performance reported as DEGRADED ({reporting})",
                payload={
                    "portfolio_id": portfolio_id,
                    "reporting_mode": reporting,
                    "quality": result.quality.to_dict(),
                },
            )
            session.add(audit)
            await session.commit()
        except Exception as e:
            logger.warning("Failed to persist degraded audit event: %s", e)
            await session.rollback()

    return result.to_dict()


# ── GET /portfolios/{id}/decomposition ────────────────────────────────

@router.get("/{portfolio_id}/decomposition")
async def get_decomposition(
    portfolio_id: int,
    session: AsyncSession = Depends(get_async_session),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    reporting: str = Query("USD", description="USD, REAL_NGN, or NGN"),
):
    """
    Decompose portfolio returns into equity, FX, and inflation components.

    Uses multiplicative return identity:
      USD:     (1+r_usd) = (1+r_equity_ngn) * (1+r_fx)
      REAL_NGN: (1+r_real) = (1+r_nominal) / (1+r_inflation)

    Quality flags in every response. Missing FX/CPI → DEGRADED (never silent).
    """
    reporting = reporting.upper()
    if reporting not in VALID_REPORTING_MODES:
        raise HTTPException(400, f"Invalid reporting mode: {reporting}. Use NGN, USD, or REAL_NGN")

    # Fetch transactions
    tx_stmt = select(PortfolioTransaction).where(
        PortfolioTransaction.portfolio_id == portfolio_id
    ).order_by(PortfolioTransaction.ts.asc())
    tx_rows = (await session.execute(tx_stmt)).scalars().all()

    if not tx_rows:
        raise HTTPException(404, f"No transactions for portfolio {portfolio_id}")

    txs = [
        {
            "ts": r.ts, "tx_type": r.tx_type, "symbol": r.symbol,
            "quantity": r.quantity, "price_ngn": r.price_ngn,
            "amount_ngn": r.amount_ngn, "fees_ngn": r.fees_ngn,
        }
        for r in tx_rows
    ]

    sd = date.fromisoformat(start_date) if start_date else tx_rows[0].ts
    ed = date.fromisoformat(end_date) if end_date else date.today()

    symbols = list({r.symbol for r in tx_rows if r.symbol})

    # Build price series
    price_series: Dict[str, Dict[date, float]] = {}
    for sym in symbols:
        adj_stmt = select(AdjustedPrice).where(
            AdjustedPrice.symbol == sym,
            AdjustedPrice.ts >= sd,
            AdjustedPrice.ts <= ed,
        ).order_by(AdjustedPrice.ts.asc())
        adj_rows = (await session.execute(adj_stmt)).scalars().all()

        if adj_rows:
            price_series[sym] = {r.ts: r.adj_close for r in adj_rows}
        else:
            ohlcv_stmt = select(OHLCVPrice).where(
                OHLCVPrice.symbol == sym,
                OHLCVPrice.ts >= sd,
                OHLCVPrice.ts <= ed,
            ).order_by(OHLCVPrice.ts.asc())
            ohlcv_rows = (await session.execute(ohlcv_stmt)).scalars().all()
            if ohlcv_rows:
                price_series[sym] = {r.ts: r.close for r in ohlcv_rows}

    daily_values = portfolio_svc.compute_daily_values(txs, price_series, sd, ed)

    if not daily_values:
        raise HTTPException(404, "No price data available for the requested date range")

    dates = [dv["date"] for dv in daily_values]
    ngn_values = [dv["value_ngn"] for dv in daily_values]
    data_quality = "FULL" if all(dv.get("data_quality") == "FULL" for dv in daily_values) else "PARTIAL"

    # Load FX/CPI if needed
    fx_service = None
    cpi_service = None

    if reporting == "USD":
        fx_stmt = select(FxRate).where(
            FxRate.pair == "USDNGN"
        ).order_by(FxRate.ts.asc())
        fx_rows = (await session.execute(fx_stmt)).scalars().all()
        if fx_rows:
            fx_service = FxRateService([
                {"pair": r.pair, "ts": r.ts, "rate": r.rate} for r in fx_rows
            ])

    if reporting == "REAL_NGN":
        cpi_stmt = select(MacroSeries).where(
            MacroSeries.series_name == "CPI_NGN"
        ).order_by(MacroSeries.ts.asc())
        cpi_rows = (await session.execute(cpi_stmt)).scalars().all()
        if cpi_rows:
            cpi_service = CpiService([
                {"series_name": r.series_name, "ts": r.ts, "value": r.value}
                for r in cpi_rows
            ])

    result = decomp_engine.compute(
        portfolio_id=portfolio_id,
        dates=dates,
        ngn_values=ngn_values,
        reporting=reporting,
        fx_service=fx_service,
        cpi_service=cpi_service,
        data_quality=data_quality,
    )

    # Write audit event if degraded
    if result.quality.overall_quality == "DEGRADED":
        try:
            audit = AuditEvent(
                component="portfolio",
                event_type="DECOMPOSITION_DEGRADED",
                level="WARN",
                message=f"Portfolio {portfolio_id} decomposition DEGRADED ({reporting})",
                payload={
                    "portfolio_id": portfolio_id,
                    "reporting_mode": reporting,
                    "quality": result.quality.to_dict(),
                    "missing": result.provenance.get("missing"),
                },
            )
            session.add(audit)
            await session.commit()
        except Exception as e:
            logger.warning("Failed to persist decomposition audit event: %s", e)
            await session.rollback()

    return result.to_dict()


# ── GET /portfolios/{id}/summary ─────────────────────────────────────

@router.get("/{portfolio_id}/summary")
async def get_summary(
    portfolio_id: int,
    session: AsyncSession = Depends(get_async_session),
    as_of: Optional[str] = Query(None, description="Snapshot date (YYYY-MM-DD)"),
    reporting: str = Query("NGN", description="NGN, USD, or REAL_NGN"),
):
    """
    Dashboard-ready portfolio snapshot.

    Returns current valuation, return windows (YTD/1Y/3Y/inception),
    drawdown, top holdings, concentration metrics, data freshness,
    and quality flags — all in a single call.
    """
    reporting = reporting.upper()
    if reporting not in VALID_REPORTING_MODES:
        raise HTTPException(400, f"Invalid reporting mode: {reporting}. Use NGN, USD, or REAL_NGN")

    as_of_date = date.fromisoformat(as_of) if as_of else date.today()

    # Fetch transactions
    tx_stmt = select(PortfolioTransaction).where(
        PortfolioTransaction.portfolio_id == portfolio_id
    ).order_by(PortfolioTransaction.ts.asc())
    tx_rows = (await session.execute(tx_stmt)).scalars().all()

    if not tx_rows:
        raise HTTPException(404, f"No transactions for portfolio {portfolio_id}")

    txs = [
        {
            "ts": r.ts, "tx_type": r.tx_type, "symbol": r.symbol,
            "quantity": r.quantity, "price_ngn": r.price_ngn,
            "amount_ngn": r.amount_ngn, "fees_ngn": r.fees_ngn,
        }
        for r in tx_rows
    ]

    symbols = list({r.symbol for r in tx_rows if r.symbol})
    inception = tx_rows[0].ts

    # Build price series (full history from inception to as_of)
    price_series: Dict[str, Dict[date, float]] = {}
    latest_prices: Dict[str, float] = {}
    tri_quality_map: Dict[str, str] = {}
    last_price_date = None

    for sym in symbols:
        adj_stmt = select(AdjustedPrice).where(
            AdjustedPrice.symbol == sym,
            AdjustedPrice.ts >= inception,
            AdjustedPrice.ts <= as_of_date,
        ).order_by(AdjustedPrice.ts.asc())
        adj_rows = (await session.execute(adj_stmt)).scalars().all()

        if adj_rows:
            price_series[sym] = {r.ts: r.adj_close for r in adj_rows}
            latest_prices[sym] = adj_rows[-1].adj_close
            tri_quality_map[sym] = adj_rows[-1].tri_quality or "UNKNOWN"
            if last_price_date is None or adj_rows[-1].ts > last_price_date:
                last_price_date = adj_rows[-1].ts
        else:
            ohlcv_stmt = select(OHLCVPrice).where(
                OHLCVPrice.symbol == sym,
                OHLCVPrice.ts >= inception,
                OHLCVPrice.ts <= as_of_date,
            ).order_by(OHLCVPrice.ts.asc())
            ohlcv_rows = (await session.execute(ohlcv_stmt)).scalars().all()
            if ohlcv_rows:
                price_series[sym] = {r.ts: r.close for r in ohlcv_rows}
                latest_prices[sym] = ohlcv_rows[-1].close
                tri_quality_map[sym] = "PRICE_ONLY"
                if last_price_date is None or ohlcv_rows[-1].ts > last_price_date:
                    last_price_date = ohlcv_rows[-1].ts

    # Load FX/CPI if needed
    fx_service = None
    cpi_service = None
    last_fx_date = None
    last_cpi_date = None

    if reporting == "USD":
        fx_stmt = select(FxRate).where(
            FxRate.pair == "USDNGN"
        ).order_by(FxRate.ts.asc())
        fx_rows = (await session.execute(fx_stmt)).scalars().all()
        if fx_rows:
            fx_service = FxRateService([
                {"pair": r.pair, "ts": r.ts, "rate": r.rate} for r in fx_rows
            ])
            last_fx_date = fx_rows[-1].ts

    if reporting == "REAL_NGN":
        cpi_stmt = select(MacroSeries).where(
            MacroSeries.series_name == "CPI_NGN"
        ).order_by(MacroSeries.ts.asc())
        cpi_rows = (await session.execute(cpi_stmt)).scalars().all()
        if cpi_rows:
            cpi_service = CpiService([
                {"series_name": r.series_name, "ts": r.ts, "value": r.value}
                for r in cpi_rows
            ])
            last_cpi_date = cpi_rows[-1].ts

    # Data freshness
    freshness = DataFreshness(
        last_price_date=last_price_date,
        last_fx_date=last_fx_date,
        last_cpi_date=last_cpi_date,
    )

    result = summary_svc.compute(
        portfolio_id=portfolio_id,
        as_of=as_of_date,
        reporting=reporting,
        transactions=txs,
        price_series=price_series,
        latest_prices=latest_prices,
        fx_service=fx_service,
        cpi_service=cpi_service,
        tri_quality_map=tri_quality_map,
        freshness=freshness,
    )

    # Write audit event if degraded
    if result.quality.overall_quality == "DEGRADED":
        try:
            audit = AuditEvent(
                component="portfolio",
                event_type="SUMMARY_DEGRADED",
                level="WARN",
                message=f"Portfolio {portfolio_id} summary DEGRADED ({reporting})",
                payload={
                    "portfolio_id": portfolio_id,
                    "reporting_mode": reporting,
                    "quality": result.quality.to_dict(),
                    "missing": result.provenance.get("missing"),
                },
            )
            session.add(audit)
            await session.commit()
        except Exception as e:
            logger.warning("Failed to persist summary audit event: %s", e)
            await session.rollback()

    return result.to_dict()


# ── GET /portfolios/{id}/timeseries ──────────────────────────────────

@router.get("/{portfolio_id}/timeseries")
async def get_timeseries(
    portfolio_id: int,
    session: AsyncSession = Depends(get_async_session),
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    reporting: str = Query("NGN", description="NGN, USD, or REAL_NGN"),
):
    """
    Chart-ready daily portfolio timeseries.

    Returns date, value, cumulative_return, drawdown, and optional
    rolling_vol_30d for each trading day in the range.
    """
    reporting = reporting.upper()
    if reporting not in VALID_REPORTING_MODES:
        raise HTTPException(400, f"Invalid reporting mode: {reporting}. Use NGN, USD, or REAL_NGN")

    # Fetch transactions
    tx_stmt = select(PortfolioTransaction).where(
        PortfolioTransaction.portfolio_id == portfolio_id
    ).order_by(PortfolioTransaction.ts.asc())
    tx_rows = (await session.execute(tx_stmt)).scalars().all()

    if not tx_rows:
        raise HTTPException(404, f"No transactions for portfolio {portfolio_id}")

    txs = [
        {
            "ts": r.ts, "tx_type": r.tx_type, "symbol": r.symbol,
            "quantity": r.quantity, "price_ngn": r.price_ngn,
            "amount_ngn": r.amount_ngn, "fees_ngn": r.fees_ngn,
        }
        for r in tx_rows
    ]

    inception = tx_rows[0].ts
    start_date = date.fromisoformat(start) if start else inception
    end_date = date.fromisoformat(end) if end else date.today()

    symbols = list({r.symbol for r in tx_rows if r.symbol})

    # Build price series
    price_series: Dict[str, Dict[date, float]] = {}
    for sym in symbols:
        adj_stmt = select(AdjustedPrice).where(
            AdjustedPrice.symbol == sym,
            AdjustedPrice.ts >= start_date,
            AdjustedPrice.ts <= end_date,
        ).order_by(AdjustedPrice.ts.asc())
        adj_rows = (await session.execute(adj_stmt)).scalars().all()

        if adj_rows:
            price_series[sym] = {r.ts: r.adj_close for r in adj_rows}
        else:
            ohlcv_stmt = select(OHLCVPrice).where(
                OHLCVPrice.symbol == sym,
                OHLCVPrice.ts >= start_date,
                OHLCVPrice.ts <= end_date,
            ).order_by(OHLCVPrice.ts.asc())
            ohlcv_rows = (await session.execute(ohlcv_stmt)).scalars().all()
            if ohlcv_rows:
                price_series[sym] = {r.ts: r.close for r in ohlcv_rows}

    # Load FX/CPI if needed
    fx_service = None
    cpi_service = None

    if reporting == "USD":
        fx_stmt = select(FxRate).where(
            FxRate.pair == "USDNGN"
        ).order_by(FxRate.ts.asc())
        fx_rows = (await session.execute(fx_stmt)).scalars().all()
        if fx_rows:
            fx_service = FxRateService([
                {"pair": r.pair, "ts": r.ts, "rate": r.rate} for r in fx_rows
            ])

    if reporting == "REAL_NGN":
        cpi_stmt = select(MacroSeries).where(
            MacroSeries.series_name == "CPI_NGN"
        ).order_by(MacroSeries.ts.asc())
        cpi_rows = (await session.execute(cpi_stmt)).scalars().all()
        if cpi_rows:
            cpi_service = CpiService([
                {"series_name": r.series_name, "ts": r.ts, "value": r.value}
                for r in cpi_rows
            ])

    result = timeseries_svc.compute(
        transactions=txs,
        price_series=price_series,
        start_date=start_date,
        end_date=end_date,
        reporting=reporting,
        fx_service=fx_service,
        cpi_service=cpi_service,
    )

    return result.to_dict()
