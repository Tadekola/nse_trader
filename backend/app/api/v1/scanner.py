"""
NGX Quality Scanner API — REST endpoints for universe, scan runs, results, buylist,
explainability, and health monitoring.

Endpoints:
  GET /api/v1/scanner/universe             — latest universe snapshot
  GET /api/v1/scanner/runs                 — list scan runs
  GET /api/v1/scanner/runs/{run_id}        — single run detail
  GET /api/v1/scanner/runs/{run_id}/results — results for a run
  GET /api/v1/scanner/buylist              — curated buylist from latest scan
  GET /api/v1/scanner/explain/{symbol}     — full scoring explanation for a symbol
  GET /api/v1/scanner/health               — scanner data health check
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_async_session
from app.db.models import (
    UniverseMember, ScanRun, ScanResult,
    FundamentalsPeriodic, AdjustedPrice, FxRate, MacroSeries, AuditEvent,
)
from app.schemas.scanner import (
    UniverseMemberResponse, UniverseResponse,
    ScanRunResponse, ScanRunListResponse,
    ScanResultResponse, ScanResultListResponse, TrailingReturns,
    BuylistEntry, BuylistResponse,
    ScoreExplanationResponse,
    MetricExplanationResponse, GuardrailTriggerResponse,
    ConfidencePenaltyResponse, WinsorBoundsResponse,
    ScannerHealthResponse, DataCoverageResponse,
    StalenessResponse, AnomalyResponse,
    ScannerDashboardResponse, ScoreDistribution, QualityTierSummary,
    ScanResultSortableResponse, ScanResultTableResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scanner", tags=["Scanner"])


# ── Universe ─────────────────────────────────────────────────────────

@router.get("/universe", response_model=UniverseResponse)
async def get_universe(
    universe_name: str = Query("top_liquid_50"),
    as_of: Optional[date] = Query(None, description="Specific date; default=latest"),
    session: AsyncSession = Depends(get_async_session),
):
    """Get universe members for a given universe name and date."""
    # Find latest as_of_date if not specified
    if as_of is None:
        latest_stmt = (
            select(func.max(UniverseMember.as_of_date))
            .where(UniverseMember.universe_name == universe_name)
        )
        row = (await session.execute(latest_stmt)).scalar()
        if row is None:
            raise HTTPException(404, f"No universe found for '{universe_name}'")
        as_of = row

    stmt = (
        select(UniverseMember)
        .where(
            UniverseMember.universe_name == universe_name,
            UniverseMember.as_of_date == as_of,
        )
        .order_by(UniverseMember.rank)
    )
    members = (await session.execute(stmt)).scalars().all()

    if not members:
        raise HTTPException(404, f"No universe '{universe_name}' for date {as_of}")

    return UniverseResponse(
        universe_name=universe_name,
        as_of_date=as_of,
        member_count=len(members),
        members=[UniverseMemberResponse.model_validate(m) for m in members],
    )


# ── Scan Runs ────────────────────────────────────────────────────────

@router.get("/runs", response_model=ScanRunListResponse)
async def list_scan_runs(
    universe_name: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
):
    """List scan runs, optionally filtered by universe name."""
    stmt = select(ScanRun).order_by(desc(ScanRun.created_at))
    count_stmt = select(func.count()).select_from(ScanRun)

    if universe_name:
        stmt = stmt.where(ScanRun.universe_name == universe_name)
        count_stmt = count_stmt.where(ScanRun.universe_name == universe_name)

    total = (await session.execute(count_stmt)).scalar() or 0
    runs = (await session.execute(stmt.limit(limit).offset(offset))).scalars().all()

    return ScanRunListResponse(
        total=total,
        runs=[ScanRunResponse.model_validate(r) for r in runs],
    )


@router.get("/runs/{run_id}", response_model=ScanRunResponse)
async def get_scan_run(
    run_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Get a single scan run by ID."""
    run = (await session.execute(
        select(ScanRun).where(ScanRun.id == run_id)
    )).scalar_one_or_none()

    if not run:
        raise HTTPException(404, f"Scan run {run_id} not found")

    return ScanRunResponse.model_validate(run)


# ── Scan Results ─────────────────────────────────────────────────────

def _build_result_response(r: ScanResult) -> ScanResultResponse:
    """Convert a ScanResult ORM object to API response with nested trailing returns."""
    return ScanResultResponse(
        symbol=r.symbol,
        rank=r.rank,
        quality_score=r.quality_score,
        sub_scores=r.sub_scores,
        reasons=r.reasons,
        red_flags=r.red_flags,
        flags=r.flags,
        liquidity_score=r.liquidity_score,
        confidence_penalty=r.confidence_penalty,
        trailing_returns=TrailingReturns(
            tri_1y_ngn=r.tri_1y_ngn,
            tri_3y_ngn=r.tri_3y_ngn,
            tri_1y_usd=r.tri_1y_usd,
            tri_3y_usd=r.tri_3y_usd,
            tri_1y_real=r.tri_1y_real,
            tri_3y_real=r.tri_3y_real,
        ),
    )


@router.get("/runs/{run_id}/results", response_model=ScanResultListResponse)
async def get_scan_results(
    run_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
):
    """Get ranked results for a specific scan run."""
    run = (await session.execute(
        select(ScanRun).where(ScanRun.id == run_id)
    )).scalar_one_or_none()

    if not run:
        raise HTTPException(404, f"Scan run {run_id} not found")

    total_stmt = (
        select(func.count())
        .select_from(ScanResult)
        .where(ScanResult.run_id == run_id)
    )
    total = (await session.execute(total_stmt)).scalar() or 0

    stmt = (
        select(ScanResult)
        .where(ScanResult.run_id == run_id)
        .order_by(ScanResult.rank)
        .limit(limit)
        .offset(offset)
    )
    results = (await session.execute(stmt)).scalars().all()

    return ScanResultListResponse(
        run_id=run_id,
        as_of_date=run.as_of_date,
        universe_name=run.universe_name,
        total=total,
        results=[_build_result_response(r) for r in results],
    )


# ── Buylist ──────────────────────────────────────────────────────────

@router.get("/buylist", response_model=BuylistResponse)
async def get_buylist(
    universe_name: str = Query("top_liquid_50"),
    top_n: int = Query(20, ge=1, le=50, description="Number of stocks in buylist"),
    max_confidence_penalty: float = Query(
        0.5, ge=0, le=1.0,
        description="Exclude stocks with confidence penalty above this threshold"
    ),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Curated buylist from the latest scan run.

    Filters:
      - Only stocks with confidence_penalty <= max_confidence_penalty
      - Excludes stocks with data_quality=INSUFFICIENT
      - Returns top_n stocks by quality_score rank

    Trailing returns include NGN, USD, and inflation-adjusted (REAL_NGN).
    """
    # Find latest scan run for this universe
    latest_run = (await session.execute(
        select(ScanRun)
        .where(ScanRun.universe_name == universe_name)
        .order_by(desc(ScanRun.created_at))
        .limit(1)
    )).scalar_one_or_none()

    if not latest_run:
        raise HTTPException(404, f"No scan runs found for universe '{universe_name}'")

    # Fetch results, filtered by quality
    stmt = (
        select(ScanResult)
        .where(
            ScanResult.run_id == latest_run.id,
            ScanResult.confidence_penalty <= max_confidence_penalty,
        )
        .order_by(ScanResult.rank)
    )
    all_results = (await session.execute(stmt)).scalars().all()

    # Filter out INSUFFICIENT data quality
    filtered = [
        r for r in all_results
        if not (r.flags and r.flags.get("data_quality") == "INSUFFICIENT")
    ][:top_n]

    buylist = []
    for r in filtered:
        data_quality = (r.flags or {}).get("data_quality", "UNKNOWN")
        buylist.append(BuylistEntry(
            rank=r.rank,
            symbol=r.symbol,
            quality_score=r.quality_score,
            data_quality=data_quality,
            confidence_penalty=r.confidence_penalty or 0.0,
            sub_scores=r.sub_scores,
            top_reasons=(r.reasons or [])[:3],
            red_flags=r.red_flags or [],
            trailing_returns=TrailingReturns(
                tri_1y_ngn=r.tri_1y_ngn,
                tri_3y_ngn=r.tri_3y_ngn,
                tri_1y_usd=r.tri_1y_usd,
                tri_3y_usd=r.tri_3y_usd,
                tri_1y_real=r.tri_1y_real,
                tri_3y_real=r.tri_3y_real,
            ),
        ))

    # Currency note
    has_usd = any(e.trailing_returns.tri_1y_usd is not None for e in buylist)
    has_real = any(e.trailing_returns.tri_1y_real is not None for e in buylist)
    if has_usd and has_real:
        currency_note = "Returns shown in NGN, USD, and inflation-adjusted REAL_NGN"
    elif has_usd:
        currency_note = "Returns shown in NGN and USD (CPI data unavailable for REAL_NGN)"
    elif has_real:
        currency_note = "Returns shown in NGN and REAL_NGN (FX data unavailable for USD)"
    else:
        currency_note = "Returns shown in NGN only (FX and CPI data unavailable)"

    return BuylistResponse(
        as_of_date=latest_run.as_of_date,
        universe_name=universe_name,
        run_id=latest_run.id,
        currency_note=currency_note,
        total=len(buylist),
        buylist=buylist,
    )


# ── Explainability ──────────────────────────────────────────────────

@router.get("/explain/{symbol}", response_model=ScoreExplanationResponse)
async def explain_symbol_score(
    symbol: str,
    run_id: Optional[int] = Query(None, description="Specific run; default=latest"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Full scoring explanation for a symbol from a scan run.

    Reconstructs the entire scoring pipeline with instrumentation:
    metric values, winsorization bounds, percentile ranks, component scores,
    guardrail triggers, and confidence penalty decomposition.
    """
    from app.scanner.explainer import explain_score
    from app.scanner.derived_metrics import compute_derived_metrics, DerivedMetrics

    # Resolve run
    if run_id is None:
        run = (await session.execute(
            select(ScanRun).order_by(desc(ScanRun.created_at)).limit(1)
        )).scalar_one_or_none()
    else:
        run = (await session.execute(
            select(ScanRun).where(ScanRun.id == run_id)
        )).scalar_one_or_none()

    if not run:
        raise HTTPException(404, "No scan run found")

    # Check the symbol exists in this run
    result_row = (await session.execute(
        select(ScanResult).where(
            ScanResult.run_id == run.id, ScanResult.symbol == symbol.upper()
        )
    )).scalar_one_or_none()

    if not result_row:
        raise HTTPException(404, f"Symbol '{symbol}' not found in run {run.id}")

    # Get all symbols from this run to reconstruct the universe context
    all_results = (await session.execute(
        select(ScanResult.symbol).where(ScanResult.run_id == run.id)
    )).scalars().all()
    all_symbols = list(all_results)

    # Fetch fundamentals for all symbols in the run
    fund_stmt = (
        select(FundamentalsPeriodic)
        .where(FundamentalsPeriodic.symbol.in_(all_symbols))
        .order_by(FundamentalsPeriodic.symbol, FundamentalsPeriodic.period_end_date.asc())
    )
    fund_rows = (await session.execute(fund_stmt)).scalars().all()
    fund_by_symbol = {}
    for r in fund_rows:
        d = {
            "period_end_date": r.period_end_date,
            "revenue": r.revenue, "operating_profit": r.operating_profit,
            "net_income": r.net_income, "total_assets": r.total_assets,
            "total_equity": r.total_equity, "total_debt": r.total_debt,
            "cash": r.cash, "operating_cash_flow": r.operating_cash_flow,
            "capex": r.capex, "dividends_paid": r.dividends_paid,
            "shares_outstanding": r.shares_outstanding,
        }
        fund_by_symbol.setdefault(r.symbol, []).append(d)

    # Recompute derived metrics for all symbols
    as_of = run.as_of_date
    metrics_list = []
    for sym in all_symbols:
        periods = fund_by_symbol.get(sym, [])
        dm = compute_derived_metrics(sym, periods, as_of)
        metrics_list.append(dm)

    # Get liquidity scores from the run results
    liq_stmt = select(ScanResult.symbol, ScanResult.liquidity_score).where(
        ScanResult.run_id == run.id)
    liq_rows = (await session.execute(liq_stmt)).all()
    liq_map = {r.symbol: r.liquidity_score or 0.5 for r in liq_rows}

    # Dividend history is not stored in ScanResult, default to 0
    # (for full reproducibility, this should be stored in provenance — PR8)
    div_history = {}

    explanation = explain_score(
        target_symbol=symbol.upper(),
        metrics_list=metrics_list,
        dividend_history=div_history,
        liquidity_scores=liq_map,
    )

    if explanation is None:
        raise HTTPException(404, f"Could not explain score for '{symbol}'")

    # Convert dataclass to response
    return ScoreExplanationResponse(
        symbol=explanation.symbol,
        quality_score=explanation.quality_score,
        scoring_config_version=explanation.scoring_config_version,
        scoring_config_hash=explanation.scoring_config_hash,
        metric_explanations=[
            MetricExplanationResponse(**me.to_dict())
            for me in explanation.metric_explanations
        ],
        guardrail_triggers=[
            GuardrailTriggerResponse(**gt.to_dict())
            for gt in explanation.guardrail_triggers
        ],
        confidence_breakdown=ConfidencePenaltyResponse(
            **explanation.confidence_breakdown.to_dict()
        ),
        winsor_bounds=[
            WinsorBoundsResponse(**wb.to_dict())
            for wb in explanation.winsor_bounds
        ],
        derived_metrics_snapshot=explanation.derived_metrics_snapshot,
        dividend_years=explanation.dividend_years,
        data_quality=explanation.data_quality,
        red_flags=explanation.red_flags,
        reasons=explanation.reasons,
    )


# ── Scanner Health ──────────────────────────────────────────────────

@router.get("/health", response_model=ScannerHealthResponse)
async def scanner_health(
    universe_name: str = Query("top_liquid_50"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Scanner data health check.

    Reports: last scan time, data coverage (fundamentals, TRI, FX, CPI),
    staleness metrics, detected anomalies, and recommendations.
    """
    now = datetime.now(timezone.utc)
    today = now.date()
    anomalies = []
    recommendations = []

    # ── Last scan ────────────────────────────────────────────────────
    last_run = (await session.execute(
        select(ScanRun)
        .where(ScanRun.universe_name == universe_name)
        .order_by(desc(ScanRun.created_at))
        .limit(1)
    )).scalar_one_or_none()

    last_scan_ts = last_run.created_at if last_run else None
    last_scan_age_hours = None
    if last_scan_ts:
        delta = now - last_scan_ts.replace(tzinfo=timezone.utc)
        last_scan_age_hours = round(delta.total_seconds() / 3600, 1)
        if last_scan_age_hours > 168:  # > 1 week
            anomalies.append(AnomalyResponse(
                anomaly_type="STALE_SCAN",
                description=f"Last scan was {last_scan_age_hours:.0f} hours ago",
                severity="WARNING",
            ))
            recommendations.append("Run a new scan: python -m app.cli.scanner run")

    # ── Universe members from latest run ─────────────────────────────
    universe_symbols = []
    if last_run:
        syms = (await session.execute(
            select(ScanResult.symbol).where(ScanResult.run_id == last_run.id)
        )).scalars().all()
        universe_symbols = list(syms)

    total_universe = len(universe_symbols)

    # ── Fundamentals coverage ────────────────────────────────────────
    with_fund = 0
    if universe_symbols:
        fund_count = (await session.execute(
            select(func.count(distinct(FundamentalsPeriodic.symbol)))
            .where(FundamentalsPeriodic.symbol.in_(universe_symbols))
        )).scalar() or 0
        with_fund = fund_count

    fund_pct = round(with_fund / total_universe * 100, 1) if total_universe > 0 else 0
    if total_universe > 0 and fund_pct < 50:
        anomalies.append(AnomalyResponse(
            anomaly_type="LOW_FUNDAMENTALS_COVERAGE",
            description=f"Only {fund_pct}% of universe has fundamentals data",
            severity="CRITICAL",
        ))
        recommendations.append("Import fundamentals: python -m app.cli.fundamentals import-csv")

    # ── TRI coverage ─────────────────────────────────────────────────
    with_tri = 0
    if universe_symbols:
        tri_count = (await session.execute(
            select(func.count(distinct(AdjustedPrice.symbol)))
            .where(AdjustedPrice.symbol.in_(universe_symbols))
        )).scalar() or 0
        with_tri = tri_count

    tri_pct = round(with_tri / total_universe * 100, 1) if total_universe > 0 else 0
    if total_universe > 0 and tri_pct < 50:
        anomalies.append(AnomalyResponse(
            anomaly_type="LOW_TRI_COVERAGE",
            description=f"Only {tri_pct}% of universe has TRI data",
            severity="WARNING",
        ))
        recommendations.append("Compute TRI: python -m app.cli.corporate_actions compute-tri")

    # ── FX staleness ─────────────────────────────────────────────────
    fx_latest = (await session.execute(
        select(func.max(FxRate.ts)).where(FxRate.pair == "USDNGN")
    )).scalar()
    fx_staleness = (today - fx_latest).days if fx_latest else None
    if fx_staleness is not None and fx_staleness > 30:
        anomalies.append(AnomalyResponse(
            anomaly_type="STALE_FX",
            description=f"FX data is {fx_staleness} days old",
            severity="WARNING",
        ))
        recommendations.append("Update FX rates")

    # ── CPI staleness ────────────────────────────────────────────────
    cpi_latest = (await session.execute(
        select(func.max(MacroSeries.ts)).where(MacroSeries.series_name == "CPI_NGN")
    )).scalar()
    cpi_staleness = (today - cpi_latest).days if cpi_latest else None
    if cpi_staleness is not None and cpi_staleness > 60:
        anomalies.append(AnomalyResponse(
            anomaly_type="STALE_CPI",
            description=f"CPI data is {cpi_staleness} days old",
            severity="WARNING",
        ))
        recommendations.append("Update CPI series")

    # ── Last fundamentals import ─────────────────────────────────────
    last_fund_import = (await session.execute(
        select(func.max(FundamentalsPeriodic.ingested_at))
    )).scalar()

    # ── Overall status ───────────────────────────────────────────────
    critical_count = sum(1 for a in anomalies if a.severity == "CRITICAL")
    warning_count = sum(1 for a in anomalies if a.severity == "WARNING")

    if critical_count > 0:
        status = "CRITICAL"
    elif warning_count > 0:
        status = "DEGRADED"
    else:
        status = "HEALTHY"

    # Write audit event if degraded (best-effort; may fail on SQLite dev)
    if status != "HEALTHY":
        try:
            session.add(AuditEvent(
                component="scanner",
                event_type="SCANNER_HEALTH_DEGRADED",
                level="WARNING" if status == "DEGRADED" else "ERROR",
                message=f"Scanner health: {status} ({len(anomalies)} anomalies)",
                payload={
                    "status": status,
                    "anomalies": [{"type": a.anomaly_type, "severity": a.severity}
                                  for a in anomalies],
                },
            ))
            await session.commit()
        except Exception:
            await session.rollback()
            logger.warning("Failed to write scanner health audit event")

    return ScannerHealthResponse(
        status=status,
        last_scan_ts=last_scan_ts,
        data_coverage=DataCoverageResponse(
            total_universe=total_universe,
            with_fundamentals=with_fund,
            with_tri=with_tri,
            with_fx=fx_latest is not None,
            with_cpi=cpi_latest is not None,
            fundamentals_coverage_pct=fund_pct,
            tri_coverage_pct=tri_pct,
        ),
        staleness=StalenessResponse(
            last_scan_ts=last_scan_ts,
            last_scan_age_hours=last_scan_age_hours,
            last_fundamentals_import_ts=last_fund_import,
            fx_latest_date=fx_latest,
            cpi_latest_date=cpi_latest,
            fx_staleness_days=fx_staleness,
            cpi_staleness_days=cpi_staleness,
        ),
        anomalies=anomalies,
        recommendations=recommendations,
    )


# ── UI Dashboard ────────────────────────────────────────────────────

def _quality_tier(score: float, data_quality: str) -> str:
    """Map quality_score + data_quality to a tier label."""
    if data_quality == "INSUFFICIENT":
        return "INSUFFICIENT"
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def _score_bucket(score: float) -> str:
    """Map a 0-100 score to a histogram bucket."""
    if score >= 80:
        return "80-100"
    if score >= 60:
        return "60-80"
    if score >= 40:
        return "40-60"
    if score >= 20:
        return "20-40"
    return "0-20"


@router.get("/dashboard", response_model=ScannerDashboardResponse)
async def scanner_dashboard(
    universe_name: str = Query("top_liquid_50"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Dashboard summary for the Next.js frontend.

    Powers: hero card, score distribution chart, tier breakdown,
    top/bottom 5, quick stats, and provenance info.
    """
    # Find latest run
    latest_run = (await session.execute(
        select(ScanRun)
        .where(ScanRun.universe_name == universe_name)
        .order_by(desc(ScanRun.created_at))
        .limit(1)
    )).scalar_one_or_none()

    if not latest_run:
        raise HTTPException(404, f"No scan runs found for universe '{universe_name}'")

    # Fetch all results for this run
    results = (await session.execute(
        select(ScanResult)
        .where(ScanResult.run_id == latest_run.id)
        .order_by(ScanResult.rank)
    )).scalars().all()

    if not results:
        raise HTTPException(404, "No results in latest scan run")

    scores = [r.quality_score for r in results]
    avg_score = round(sum(scores) / len(scores), 2)
    sorted_scores = sorted(scores)
    mid = len(sorted_scores) // 2
    median_score = round(
        sorted_scores[mid] if len(sorted_scores) % 2 == 1
        else (sorted_scores[mid - 1] + sorted_scores[mid]) / 2, 2
    )

    # Score distribution
    bucket_counts = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
    for s in scores:
        bucket_counts[_score_bucket(s)] += 1
    distribution = [
        ScoreDistribution(bucket=b, count=c)
        for b, c in bucket_counts.items()
    ]

    # Quality tiers
    tier_data = {"HIGH": [], "MEDIUM": [], "LOW": [], "INSUFFICIENT": []}
    for r in results:
        dq = (r.flags or {}).get("data_quality", "FULL")
        tier = _quality_tier(r.quality_score, dq)
        tier_data[tier].append(r.symbol)

    tiers = [
        QualityTierSummary(
            tier="HIGH", min_score=70, max_score=100,
            count=len(tier_data["HIGH"]), symbols=tier_data["HIGH"][:10]),
        QualityTierSummary(
            tier="MEDIUM", min_score=40, max_score=70,
            count=len(tier_data["MEDIUM"]), symbols=tier_data["MEDIUM"][:10]),
        QualityTierSummary(
            tier="LOW", min_score=0, max_score=40,
            count=len(tier_data["LOW"]), symbols=tier_data["LOW"][:10]),
        QualityTierSummary(
            tier="INSUFFICIENT", min_score=0, max_score=100,
            count=len(tier_data["INSUFFICIENT"]), symbols=tier_data["INSUFFICIENT"][:10]),
    ]

    # Quick stats
    total_red_flags = sum(len(r.red_flags or []) for r in results)
    degraded = sum(1 for r in results
                   if (r.flags or {}).get("data_quality") == "DEGRADED")
    insufficient = sum(1 for r in results
                       if (r.flags or {}).get("data_quality") == "INSUFFICIENT")

    # Fundamentals coverage
    universe_symbols = [r.symbol for r in results]
    fund_count = 0
    if universe_symbols:
        fund_count = (await session.execute(
            select(func.count(distinct(FundamentalsPeriodic.symbol)))
            .where(FundamentalsPeriodic.symbol.in_(universe_symbols))
        )).scalar() or 0
    fund_pct = round(fund_count / len(results) * 100, 1) if results else 0

    # Top 5 / Bottom 5
    top_5 = [_build_result_response(r) for r in results[:5]]
    bottom_5 = [_build_result_response(r) for r in results[-5:]]

    # Provenance
    prov = latest_run.provenance or {}

    # Health status (simplified)
    health = "HEALTHY"
    if fund_pct < 50 or insufficient > len(results) * 0.3:
        health = "CRITICAL"
    elif degraded > len(results) * 0.2 or fund_pct < 80:
        health = "DEGRADED"

    return ScannerDashboardResponse(
        last_scan_date=latest_run.as_of_date,
        last_scan_run_id=latest_run.id,
        universe_name=universe_name,
        universe_size=len(results),
        avg_quality_score=avg_score,
        median_quality_score=median_score,
        health_status=health,
        score_distribution=distribution,
        quality_tiers=tiers,
        total_red_flags=total_red_flags,
        degraded_count=degraded,
        insufficient_count=insufficient,
        fundamentals_coverage_pct=fund_pct,
        top_5=top_5,
        bottom_5=bottom_5,
        scoring_config_version=prov.get("engine_version"),
        scoring_config_hash=prov.get("scoring_config_hash"),
    )


# ── Sortable Results Table ──────────────────────────────────────────

VALID_SORT_FIELDS = {
    "rank", "quality_score", "symbol",
    "profitability", "cash_quality", "balance_sheet",
    "stability", "shareholder_return",
    "liquidity_score", "confidence_penalty", "red_flag_count",
}


def _build_sortable_result(r: ScanResult) -> ScanResultSortableResponse:
    """Convert ScanResult to a flat, sortable response for the UI table."""
    sub = r.sub_scores or {}
    dq = (r.flags or {}).get("data_quality", "FULL")
    red_flags = r.red_flags or []
    reasons = r.reasons or []

    return ScanResultSortableResponse(
        symbol=r.symbol,
        rank=r.rank,
        quality_score=r.quality_score,
        quality_tier=_quality_tier(r.quality_score, dq),
        data_quality=dq,
        profitability=sub.get("profitability", 0),
        cash_quality=sub.get("cash_quality", 0),
        balance_sheet=sub.get("balance_sheet", 0),
        stability=sub.get("stability", 0),
        shareholder_return=sub.get("shareholder_return", 0),
        liquidity_score=r.liquidity_score,
        confidence_penalty=r.confidence_penalty,
        red_flag_count=len(red_flags),
        top_red_flag=red_flags[0] if red_flags else None,
        trailing_returns=TrailingReturns(
            tri_1y_ngn=r.tri_1y_ngn, tri_3y_ngn=r.tri_3y_ngn,
            tri_1y_usd=r.tri_1y_usd, tri_3y_usd=r.tri_3y_usd,
            tri_1y_real=r.tri_1y_real, tri_3y_real=r.tri_3y_real,
        ),
        top_reason=reasons[0] if reasons else None,
    )


@router.get("/table", response_model=ScanResultTableResponse)
async def scanner_table(
    universe_name: str = Query("top_liquid_50"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query("rank", description="Field to sort by"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    quality_tier: Optional[str] = Query(None, pattern="^(HIGH|MEDIUM|LOW|INSUFFICIENT)$"),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    max_score: Optional[float] = Query(None, ge=0, le=100),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Paginated, sortable, filterable scan results for the Next.js screener table.

    Supports server-side sorting by: rank, quality_score, symbol, profitability,
    cash_quality, balance_sheet, stability, shareholder_return, liquidity_score,
    confidence_penalty, red_flag_count.

    Supports filtering by quality_tier and score range.
    """
    # Find latest run
    latest_run = (await session.execute(
        select(ScanRun)
        .where(ScanRun.universe_name == universe_name)
        .order_by(desc(ScanRun.created_at))
        .limit(1)
    )).scalar_one_or_none()

    if not latest_run:
        raise HTTPException(404, f"No scan runs found for universe '{universe_name}'")

    # Fetch all results (we need to sort by JSONB sub-fields, so fetch all and sort in Python)
    all_results = (await session.execute(
        select(ScanResult)
        .where(ScanResult.run_id == latest_run.id)
        .order_by(ScanResult.rank)
    )).scalars().all()

    # Convert to sortable format
    sortable = [_build_sortable_result(r) for r in all_results]

    # Apply filters
    if quality_tier:
        sortable = [r for r in sortable if r.quality_tier == quality_tier]
    if min_score is not None:
        sortable = [r for r in sortable if r.quality_score >= min_score]
    if max_score is not None:
        sortable = [r for r in sortable if r.quality_score <= max_score]

    total = len(sortable)

    # Sort
    if sort_by in VALID_SORT_FIELDS:
        reverse = sort_dir == "desc"
        sortable.sort(key=lambda r: getattr(r, sort_by) or 0, reverse=reverse)

    # Paginate
    offset = (page - 1) * page_size
    page_results = sortable[offset:offset + page_size]

    return ScanResultTableResponse(
        run_id=latest_run.id,
        as_of_date=latest_run.as_of_date,
        universe_name=universe_name,
        total=total,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        results=page_results,
    )
