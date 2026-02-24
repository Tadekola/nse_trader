"""
Seed demo data into SQLite for local frontend development.

Creates:
  - UniverseMembers (10 symbols)
  - FundamentalsPeriodic (2 periods each)
  - FundamentalsDerived
  - A complete ScanRun + ScanResults via the workflow
"""

import asyncio
import os
import sys
import logging
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("ENV", "dev")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYMBOLS = [
    "DANGCEM", "GTCO", "ZENITHBANK", "MTNN", "AIRTELAFRI",
    "BUACEMENT", "SEPLAT", "NESTLE", "STANBIC", "ACCESSCORP",
]

SEED_DATE = date(2025, 6, 15)


async def seed():
    from app.db.engine import get_async_engine, get_session_factory, init_db
    from app.db.models import (
        Base, UniverseMember, FundamentalsPeriodic, FundamentalsDerived,
        ScanRun, ScanResult, AuditEvent,
    )
    from sqlalchemy import text

    await init_db()
    factory = get_session_factory()

    async with factory() as session:
        # Check if already seeded
        existing = (await session.execute(
            text("SELECT COUNT(*) FROM universe_members")
        )).scalar()
        if existing and existing > 0:
            logger.info("Database already seeded (%d universe members). Skipping.", existing)
            return

        logger.info("Seeding %d symbols...", len(SYMBOLS))

        # ── Universe Members ────────────────────────────────────────
        for i, sym in enumerate(SYMBOLS):
            session.add(UniverseMember(
                id=i + 1,
                symbol=sym,
                as_of_date=SEED_DATE,
                universe_name="top_liquid_50",
                liquidity_score=round(0.95 - i * 0.08, 4),
                avg_daily_value=Decimal(str(500_000_000 - i * 40_000_000)),
                rank=i + 1,
            ))

        # ── Fundamentals ────────────────────────────────────────────
        for i, sym in enumerate(SYMBOLS):
            revenue_base = 500_000_000_000 - i * 40_000_000_000
            for y, end_date in enumerate([date(2023, 12, 31), date(2024, 12, 31)]):
                rev = revenue_base + y * 20_000_000_000
                session.add(FundamentalsPeriodic(
                    id=(i * 2) + y + 1,
                    symbol=sym,
                    period_end_date=end_date,
                    revenue=Decimal(str(rev)),
                    operating_profit=Decimal(str(int(rev * 0.30))),
                    net_income=Decimal(str(int(rev * 0.20))),
                    total_assets=Decimal(str(int(rev * 5))),
                    total_equity=Decimal(str(int(rev * 1.2))),
                    total_debt=Decimal(str(int(rev * 0.5))),
                    cash=Decimal(str(int(rev * 0.3))),
                    operating_cash_flow=Decimal(str(int(rev * 0.25))),
                    capex=Decimal(str(int(rev * 0.10))),
                    dividends_paid=Decimal(str(int(rev * 0.05))),
                    shares_outstanding=Decimal("17000000000"),
                    source="seed_demo",
                ))

        # ── Derived Metrics ─────────────────────────────────────────
        for i, sym in enumerate(SYMBOLS):
            rev_base = 500_000_000_000 - i * 40_000_000_000
            session.add(FundamentalsDerived(
                id=i + 1,
                symbol=sym,
                as_of_date=SEED_DATE,
                roe=round(0.20 - i * 0.015, 4),
                roic_proxy=round(0.18 - i * 0.013, 4),
                op_margin=round(0.30 - i * 0.02, 4),
                net_margin=round(0.20 - i * 0.015, 4),
                debt_to_equity=round(0.40 + i * 0.05, 4),
                cash_to_debt=round(0.60 - i * 0.04, 4),
                ocf_to_net_income=round(1.25 - i * 0.05, 4),
                fcf=float(int(rev_base * 0.15)),
                earnings_stability=round(0.90 - i * 0.05, 4),
                margin_stability=round(0.88 - i * 0.04, 4),
                red_flags=[],
                periods_available=2,
                data_freshness_days=180,
            ))

        await session.commit()
        logger.info("Seeded universe members, fundamentals, and derived metrics.")

        # ── Score using pure computation (no DB queries) ────────────
        logger.info("Computing scores via pure engines...")
        from app.scanner.derived_metrics import compute_derived_metrics
        from app.scanner.quality_scorer import score_universe
        from app.scanner.explainer import get_scoring_config_hash, SCORING_CONFIG_VERSION

        # Build fundamentals dicts for derived metrics
        fund_data = {}
        for i, sym in enumerate(SYMBOLS):
            revenue_base = 500_000_000_000 - i * 40_000_000_000
            periods = []
            for y, end_date in enumerate([date(2023, 12, 31), date(2024, 12, 31)]):
                rev = revenue_base + y * 20_000_000_000
                periods.append({
                    "period_end_date": end_date,
                    "revenue": rev,
                    "operating_profit": int(rev * 0.30),
                    "net_income": int(rev * 0.20),
                    "total_assets": int(rev * 5),
                    "total_equity": int(rev * 1.2),
                    "total_debt": int(rev * 0.5),
                    "cash": int(rev * 0.3),
                    "operating_cash_flow": int(rev * 0.25),
                    "capex": int(rev * 0.10),
                    "dividends_paid": int(rev * 0.05),
                    "shares_outstanding": 17_000_000_000,
                })
            fund_data[sym] = periods

        derived = [compute_derived_metrics(sym, fund_data[sym], SEED_DATE) for sym in SYMBOLS]
        scores = score_universe(derived)

        # Persist ScanRun
        scan_run = ScanRun(
            id=1,
            universe_name="top_liquid_50",
            as_of_date=SEED_DATE,
            symbols_scanned=len(SYMBOLS),
            symbols_ranked=len(scores),
            provenance={
                "engine_version": SCORING_CONFIG_VERSION,
                "scoring_config_hash": get_scoring_config_hash(),
                "universe_symbols": SYMBOLS,
                "seeded": True,
            },
        )
        session.add(scan_run)
        await session.flush()

        # Persist ScanResults (scores are already sorted by quality_score desc)
        for rank_idx, s in enumerate(scores, 1):
            sym_idx = SYMBOLS.index(s.symbol) if s.symbol in SYMBOLS else 5
            liq_score = max(0, 0.95 - sym_idx * 0.08)
            session.add(ScanResult(
                id=rank_idx,
                run_id=scan_run.id,
                symbol=s.symbol,
                rank=rank_idx,
                quality_score=s.quality_score,
                sub_scores=s.sub_scores,
                reasons=s.reasons,
                red_flags=s.red_flags,
                flags={"data_quality": s.data_quality},
                liquidity_score=liq_score,
                confidence_penalty=s.confidence_penalty,
                tri_1y_ngn=round(0.15 - sym_idx * 0.02, 4),
                tri_1y_usd=round(0.05 - sym_idx * 0.015, 4),
                tri_3y_ngn=round(0.45 - sym_idx * 0.05, 4),
            ))

        await session.commit()
        logger.info("Scan seeded: run_id=%d, %d results", scan_run.id, len(scores))
        for i, s in enumerate(scores[:5], 1):
            logger.info("  #%d %s: %.1f", i, s.symbol, s.quality_score)


if __name__ == "__main__":
    asyncio.run(seed())
