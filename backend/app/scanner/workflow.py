"""
Scanner Workflow — Orchestrates universe build → derived metrics → quality scoring → persistence.

Pure orchestration layer. Each step uses existing engines:
  1. UniverseBuilder.build()          → universe members
  2. Fetch FundamentalsPeriodic       → raw financials
  3. compute_derived_metrics()        → ratios + red flags
  4. score_universe()                 → quality scores + ranking
  5. Compute trailing TRI returns     → NGN/USD/REAL_NGN performance
  6. Persist ScanRun + ScanResult     → durable storage
  7. Write AuditEvent                 → provenance trail

CLI:
  python -m app.cli.scanner run --universe top_liquid_50 --as-of 2025-06-15
"""

import hashlib
import json
import logging
from datetime import date, timedelta, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, distinct, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    FundamentalsPeriodic, FundamentalsDerived, CorporateAction,
    AdjustedPrice, FxRate, MacroSeries, OHLCVPrice,
    ScanRun, ScanResult, AuditEvent,
)
from app.scanner.universe import UniverseBuilder, UniverseSnapshot
from app.scanner.derived_metrics import compute_derived_metrics, DerivedMetrics
from app.scanner.quality_scorer import score_universe, QualityScore
from app.scanner.explainer import get_scoring_config_hash, SCORING_CONFIG_VERSION

logger = logging.getLogger(__name__)


async def _count_dividend_years(session: AsyncSession, symbols: List[str]) -> Dict[str, int]:
    """Count distinct years with CASH_DIVIDEND for each symbol."""
    if not symbols:
        return {}

    stmt = (
        select(
            CorporateAction.symbol,
            func.count(distinct(func.extract("year", CorporateAction.ex_date))).label("years"),
        )
        .where(
            CorporateAction.symbol.in_(symbols),
            CorporateAction.action_type == "CASH_DIVIDEND",
        )
        .group_by(CorporateAction.symbol)
    )
    rows = (await session.execute(stmt)).all()
    return {r.symbol: int(r.years) for r in rows}


async def _fetch_fundamentals(
    session: AsyncSession, symbols: List[str]
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch all periodic fundamentals grouped by symbol."""
    if not symbols:
        return {}

    stmt = (
        select(FundamentalsPeriodic)
        .where(FundamentalsPeriodic.symbol.in_(symbols))
        .order_by(FundamentalsPeriodic.symbol, FundamentalsPeriodic.period_end_date.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()

    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        d = {
            "period_end_date": r.period_end_date,
            "revenue": r.revenue,
            "operating_profit": r.operating_profit,
            "net_income": r.net_income,
            "total_assets": r.total_assets,
            "total_equity": r.total_equity,
            "total_debt": r.total_debt,
            "cash": r.cash,
            "operating_cash_flow": r.operating_cash_flow,
            "capex": r.capex,
            "dividends_paid": r.dividends_paid,
            "shares_outstanding": r.shares_outstanding,
        }
        by_symbol.setdefault(r.symbol, []).append(d)

    return by_symbol


async def _compute_trailing_tri(
    session: AsyncSession,
    symbol: str,
    as_of: date,
) -> Dict[str, Optional[float]]:
    """
    Compute trailing 1Y and 3Y TRI returns in NGN, USD, and REAL_NGN.

    Returns dict with keys: tri_1y_ngn, tri_3y_ngn, tri_1y_usd, tri_3y_usd,
                             tri_1y_real, tri_3y_real
    """
    result: Dict[str, Optional[float]] = {
        "tri_1y_ngn": None, "tri_3y_ngn": None,
        "tri_1y_usd": None, "tri_3y_usd": None,
        "tri_1y_real": None, "tri_3y_real": None,
    }

    # Get TRI values at as_of and 1Y/3Y ago
    dates_needed = {
        "now": as_of,
        "1y": as_of - timedelta(days=365),
        "3y": as_of - timedelta(days=3 * 365),
    }

    tri_values: Dict[str, Optional[float]] = {}
    for label, target_date in dates_needed.items():
        # Find closest TRI on or before target_date
        stmt = (
            select(AdjustedPrice.tri, AdjustedPrice.ts)
            .where(
                AdjustedPrice.symbol == symbol,
                AdjustedPrice.ts <= target_date,
            )
            .order_by(AdjustedPrice.ts.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).first()
        tri_values[label] = row.tri if row else None

    # Compute NGN returns
    if tri_values["now"] and tri_values["1y"] and tri_values["1y"] > 0:
        result["tri_1y_ngn"] = (tri_values["now"] / tri_values["1y"]) - 1.0
    if tri_values["now"] and tri_values["3y"] and tri_values["3y"] > 0:
        result["tri_3y_ngn"] = (tri_values["now"] / tri_values["3y"]) - 1.0

    # FX conversion (USD)
    fx_now = await _get_fx_rate(session, as_of)
    fx_1y = await _get_fx_rate(session, dates_needed["1y"])
    fx_3y = await _get_fx_rate(session, dates_needed["3y"])

    if result["tri_1y_ngn"] is not None and fx_now and fx_1y and fx_1y > 0:
        # USD return = (1 + NGN_return) * (fx_old / fx_new) - 1
        result["tri_1y_usd"] = (1 + result["tri_1y_ngn"]) * (fx_1y / fx_now) - 1.0
    if result["tri_3y_ngn"] is not None and fx_now and fx_3y and fx_3y > 0:
        result["tri_3y_usd"] = (1 + result["tri_3y_ngn"]) * (fx_3y / fx_now) - 1.0

    # CPI conversion (REAL_NGN)
    cpi_now = await _get_cpi(session, as_of)
    cpi_1y = await _get_cpi(session, dates_needed["1y"])
    cpi_3y = await _get_cpi(session, dates_needed["3y"])

    if result["tri_1y_ngn"] is not None and cpi_now and cpi_1y and cpi_1y > 0:
        result["tri_1y_real"] = (1 + result["tri_1y_ngn"]) / (cpi_now / cpi_1y) - 1.0
    if result["tri_3y_ngn"] is not None and cpi_now and cpi_3y and cpi_3y > 0:
        result["tri_3y_real"] = (1 + result["tri_3y_ngn"]) / (cpi_now / cpi_3y) - 1.0

    return result


async def _get_fx_rate(session: AsyncSession, target: date) -> Optional[float]:
    """Get USDNGN rate on or before target date."""
    stmt = (
        select(FxRate.rate)
        .where(FxRate.pair == "USDNGN", FxRate.ts <= target)
        .order_by(FxRate.ts.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    return row.rate if row else None


async def _get_cpi(session: AsyncSession, target: date) -> Optional[float]:
    """Get CPI_NGN value on or before target date."""
    stmt = (
        select(MacroSeries.value)
        .where(MacroSeries.series_name == "CPI_NGN", MacroSeries.ts <= target)
        .order_by(MacroSeries.ts.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    return row.value if row else None


def _compute_universe_hash(symbols: List[str]) -> str:
    """Deterministic hash of the universe member list."""
    raw = ",".join(sorted(symbols))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _compute_fundamentals_hash(fund_by_symbol: Dict[str, List[Dict[str, Any]]]) -> str:
    """Deterministic hash of fundamentals data used in a scan."""
    raw = json.dumps(fund_by_symbol, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def run_scan(
    session: AsyncSession,
    universe_name: str = "top_liquid_50",
    as_of: Optional[date] = None,
    top_n: int = 50,
    persist: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Execute a full scan: universe → fundamentals → scoring → persistence.

    Args:
        force: If False (default), skip if a scan already exists for this
               universe + as_of date. Set True to re-run regardless.

    Returns a summary dict suitable for CLI output or API response.
    """
    if as_of is None:
        as_of = date.today()

    logger.info("Starting scan: universe=%s, as_of=%s, top_n=%d",
                universe_name, as_of, top_n)

    # ── Same-day idempotency guard ───────────────────────────────────
    if persist and not force:
        existing = (await session.execute(
            select(ScanRun).where(
                ScanRun.universe_name == universe_name,
                ScanRun.as_of_date == as_of,
            ).limit(1)
        )).scalar_one_or_none()
        if existing:
            logger.info("Scan already exists for %s as_of=%s (run_id=%d). "
                        "Use force=True to re-run.", universe_name, as_of, existing.id)
            return {
                "status": "skipped_idempotent",
                "run_id": existing.id,
                "as_of": as_of.isoformat(),
                "universe": universe_name,
                "reason": "Scan already exists for this date. Use --force to override.",
            }

    # Step 1: Build universe
    builder = UniverseBuilder(session)
    universe = await builder.build(
        universe_name=universe_name, as_of=as_of, top_n=top_n, persist=persist
    )
    member_symbols = [m.symbol for m in universe.members]
    liquidity_map = {m.symbol: m.liquidity_score for m in universe.members}

    if not member_symbols:
        logger.warning("No liquid symbols found for universe '%s'", universe_name)
        return {"status": "empty_universe", "symbols": 0}

    logger.info("Universe: %d members", len(member_symbols))

    # Step 2: Fetch fundamentals
    fund_by_symbol = await _fetch_fundamentals(session, member_symbols)

    # Step 3: Compute derived metrics
    derived_list: List[DerivedMetrics] = []
    for symbol in member_symbols:
        periods = fund_by_symbol.get(symbol, [])
        dm = compute_derived_metrics(symbol, periods, as_of)
        derived_list.append(dm)

    # Step 4: Get dividend history
    div_years = await _count_dividend_years(session, member_symbols)

    # Step 5: Score universe
    scores = score_universe(
        derived_list,
        dividend_history=div_years,
        liquidity_scores=liquidity_map,
    )

    # Step 6: Compute trailing TRI returns per symbol
    tri_returns: Dict[str, Dict[str, Optional[float]]] = {}
    for symbol in member_symbols:
        tri_returns[symbol] = await _compute_trailing_tri(session, symbol, as_of)

    # ── Compute reproducibility hashes ───────────────────────────────
    universe_hash = _compute_universe_hash(member_symbols)
    fundamentals_hash = _compute_fundamentals_hash(fund_by_symbol)
    scoring_config_hash = get_scoring_config_hash()

    # Step 7: Persist scan run + results
    scan_run = None
    if persist:
        scan_run = ScanRun(
            as_of_date=as_of,
            universe_name=universe_name,
            symbols_scanned=len(member_symbols),
            symbols_ranked=len(scores),
            summary={
                "top_5": [s.symbol for s in scores[:5]],
                "avg_quality": round(sum(s.quality_score for s in scores) / len(scores), 2) if scores else 0,
                "degraded_count": sum(1 for s in scores if s.data_quality == "DEGRADED"),
                "insufficient_count": sum(1 for s in scores if s.data_quality == "INSUFFICIENT"),
            },
            provenance={
                "universe_name": universe_name,
                "as_of": as_of.isoformat(),
                "top_n": top_n,
                "engine_version": SCORING_CONFIG_VERSION,
                "scoring_config_hash": scoring_config_hash,
                "universe_hash": universe_hash,
                "fundamentals_hash": fundamentals_hash,
                "universe_symbols": sorted(member_symbols),
                "dividend_years": div_years,
            },
        )
        session.add(scan_run)
        await session.flush()  # get scan_run.id

        for rank_idx, qs in enumerate(scores, start=1):
            tri = tri_returns.get(qs.symbol, {})
            session.add(ScanResult(
                run_id=scan_run.id,
                symbol=qs.symbol,
                rank=rank_idx,
                quality_score=qs.quality_score,
                sub_scores=qs.sub_scores,
                reasons=qs.reasons,
                red_flags=qs.red_flags,
                flags={
                    "data_quality": qs.data_quality,
                    "liquidity_gated": "LOW_LIQUIDITY" in qs.red_flags,
                },
                liquidity_score=liquidity_map.get(qs.symbol, 0),
                confidence_penalty=qs.confidence_penalty,
                tri_1y_ngn=tri.get("tri_1y_ngn"),
                tri_3y_ngn=tri.get("tri_3y_ngn"),
                tri_1y_usd=tri.get("tri_1y_usd"),
                tri_3y_usd=tri.get("tri_3y_usd"),
                tri_1y_real=tri.get("tri_1y_real"),
                tri_3y_real=tri.get("tri_3y_real"),
            ))

        # Audit event
        session.add(AuditEvent(
            component="scanner",
            event_type="SCAN_COMPLETED",
            level="INFO",
            message=f"Scan completed: {len(scores)} symbols ranked for '{universe_name}' as_of={as_of}",
            payload={
                "run_id": scan_run.id,
                "universe": universe_name,
                "as_of": as_of.isoformat(),
                "symbols_scanned": len(member_symbols),
                "symbols_ranked": len(scores),
                "top_5": [s.symbol for s in scores[:5]],
            },
        ))

        await session.commit()
        logger.info("Scan persisted: run_id=%d, %d results", scan_run.id, len(scores))

    # Build summary
    summary = {
        "status": "completed",
        "run_id": scan_run.id if scan_run else None,
        "as_of": as_of.isoformat(),
        "universe": universe_name,
        "symbols_scanned": len(member_symbols),
        "symbols_ranked": len(scores),
        "provenance": {
            "engine_version": SCORING_CONFIG_VERSION,
            "scoring_config_hash": scoring_config_hash,
            "universe_hash": universe_hash,
            "fundamentals_hash": fundamentals_hash,
        },
        "top_10": [
            {
                "rank": i + 1,
                "symbol": s.symbol,
                "quality_score": s.quality_score,
                "data_quality": s.data_quality,
                "confidence_penalty": s.confidence_penalty,
                "tri_1y_ngn": tri_returns.get(s.symbol, {}).get("tri_1y_ngn"),
                "tri_1y_usd": tri_returns.get(s.symbol, {}).get("tri_1y_usd"),
            }
            for i, s in enumerate(scores[:10])
        ],
    }

    return summary
