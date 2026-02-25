"""
Corporate Actions CLI (Milestone A — PR2).

Commands:
  import-csv   — Import corporate actions from a CSV file
  compute-tri  — Compute adjusted close + TRI for a symbol or universe

Usage::

    # Import corporate actions
    python -m app.cli.corporate_actions import-csv --file actions.csv

    # Compute TRI for a single symbol
    python -m app.cli.corporate_actions compute-tri --symbol DANGCEM

    # Compute TRI for all symbols with OHLCV data
    python -m app.cli.corporate_actions compute-tri --all

    # Compute TRI with date range
    python -m app.cli.corporate_actions compute-tri --symbol DANGCEM --start-date 2023-01-01 --end-date 2024-12-31
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


async def import_csv(file_path: str) -> dict:
    """Import corporate actions from a CSV file into the database."""
    from app.data.corporate_actions.csv_provider import CsvCorporateActionProvider
    from app.db.engine import get_session_factory
    from app.db.models import AuditEvent, CorporateAction

    provider = CsvCorporateActionProvider()
    result = provider.parse_file(file_path)

    if result.rows_accepted == 0:
        logger.warning("No valid rows to import from %s", file_path)
        return {
            "imported": 0,
            "rejected": result.rows_rejected,
            "errors": [e.to_dict() for e in result.errors],
        }

    factory = get_session_factory()
    imported = 0
    skipped = 0

    async with factory() as session:
        for action_dict in result.actions:
            try:
                ca = CorporateAction(**action_dict)
                session.add(ca)
                await session.flush()
                imported += 1
            except Exception as e:
                await session.rollback()
                if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                    skipped += 1
                    logger.debug("Skipping duplicate: %s %s %s",
                                 action_dict["symbol"],
                                 action_dict["action_type"],
                                 action_dict["ex_date"])
                else:
                    logger.error("Failed to import action: %s", e)
                    raise

        # Audit event
        audit = AuditEvent(
            component="corporate_actions",
            event_type="CSV_IMPORT",
            level="INFO",
            message=f"Imported {imported} actions from {file_path} ({skipped} duplicates skipped, {result.rows_rejected} rejected)",
            payload={
                "file": file_path,
                "imported": imported,
                "skipped": skipped,
                "rejected": result.rows_rejected,
                "errors": [e.to_dict() for e in result.errors[:10]],
            },
        )
        session.add(audit)
        await session.commit()

    summary = {
        "imported": imported,
        "skipped_duplicates": skipped,
        "rejected": result.rows_rejected,
        "errors": [e.to_dict() for e in result.errors],
    }
    logger.info("CSV import complete: %s", json.dumps(summary, default=str))
    return summary


async def compute_tri(
    symbol: Optional[str] = None,
    all_symbols: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """
    Compute adjusted close + TRI for one or all symbols and persist.

    Fetches OHLCV prices and corporate actions from the DB, runs the
    TRI engine, and upserts results into adjusted_prices.
    """
    from sqlalchemy import select, func, delete
    from app.db.engine import get_session_factory
    from app.db.models import AdjustedPrice, AuditEvent, CorporateAction, OHLCVPrice
    from app.services.tri_engine import TRIEngine

    factory = get_session_factory()
    engine = TRIEngine()
    results_summary = {"symbols_processed": 0, "rows_written": 0, "warnings": []}

    async with factory() as session:
        # Determine which symbols to process
        if symbol:
            symbols = [symbol.upper()]
        elif all_symbols:
            stmt = select(func.distinct(OHLCVPrice.symbol))
            rows = (await session.execute(stmt)).scalars().all()
            symbols = sorted(rows)
        else:
            raise ValueError("Must specify --symbol or --all")

        sd = date.fromisoformat(start_date) if start_date else None
        ed = date.fromisoformat(end_date) if end_date else None

        for sym in symbols:
            # Fetch prices
            price_stmt = select(OHLCVPrice).where(OHLCVPrice.symbol == sym)
            if sd:
                price_stmt = price_stmt.where(OHLCVPrice.ts >= sd)
            if ed:
                price_stmt = price_stmt.where(OHLCVPrice.ts <= ed)
            price_stmt = price_stmt.order_by(OHLCVPrice.ts.asc())
            price_rows = (await session.execute(price_stmt)).scalars().all()

            if not price_rows:
                logger.warning("No prices for %s, skipping", sym)
                results_summary["warnings"].append(f"No prices for {sym}")
                continue

            prices = [{"ts": p.ts, "close": p.close} for p in price_rows]

            # Fetch corporate actions
            action_stmt = select(CorporateAction).where(CorporateAction.symbol == sym)
            if sd:
                action_stmt = action_stmt.where(CorporateAction.ex_date >= sd)
            if ed:
                action_stmt = action_stmt.where(CorporateAction.ex_date <= ed)
            action_rows = (await session.execute(action_stmt)).scalars().all()

            actions = [
                {
                    "action_type": a.action_type,
                    "ex_date": a.ex_date,
                    "amount": a.amount,
                    "ratio_from": a.ratio_from,
                    "ratio_to": a.ratio_to,
                }
                for a in action_rows
            ]

            # Compute
            tri_result = engine.compute(sym, prices, actions)

            if not tri_result.rows:
                continue

            # Delete existing rows for this symbol+date range, then insert
            del_stmt = delete(AdjustedPrice).where(AdjustedPrice.symbol == sym)
            if sd:
                del_stmt = del_stmt.where(AdjustedPrice.ts >= sd)
            if ed:
                del_stmt = del_stmt.where(AdjustedPrice.ts <= ed)
            await session.execute(del_stmt)

            now = datetime.now(timezone.utc)
            for row in tri_result.rows:
                ap = AdjustedPrice(
                    symbol=row.symbol,
                    ts=row.ts,
                    close_raw=row.close_raw,
                    adj_factor=row.adj_factor,
                    adj_close=row.adj_close,
                    tri=row.tri,
                    daily_return_price=row.daily_return_price,
                    daily_return_total=row.daily_return_total,
                    tri_quality=row.tri_quality,
                    computed_at=now,
                    provenance={
                        "source": "tri_engine",
                        "computed_at": now.isoformat(),
                        "splits_applied": tri_result.splits_applied,
                        "bonuses_applied": tri_result.bonuses_applied,
                        "dividends_applied": tri_result.dividends_applied,
                        "tri_quality": tri_result.tri_quality,
                    },
                )
                session.add(ap)

            results_summary["symbols_processed"] += 1
            results_summary["rows_written"] += len(tri_result.rows)
            results_summary["warnings"].extend(tri_result.warnings)

            logger.info(
                "%s: %d rows, quality=%s, splits=%d, dividends=%d",
                sym, len(tri_result.rows), tri_result.tri_quality,
                tri_result.splits_applied, tri_result.dividends_applied,
            )

        # Audit event
        audit = AuditEvent(
            component="corporate_actions",
            event_type="TRI_COMPUTE",
            level="INFO",
            message=f"Computed TRI for {results_summary['symbols_processed']} symbols ({results_summary['rows_written']} rows)",
            payload=results_summary,
        )
        session.add(audit)
        await session.commit()

    logger.info("TRI compute complete: %s", json.dumps(results_summary, default=str))
    return results_summary


def main():
    parser = argparse.ArgumentParser(description="Corporate Actions CLI")
    sub = parser.add_subparsers(dest="command")

    # import-csv
    imp = sub.add_parser("import-csv", help="Import corporate actions from CSV")
    imp.add_argument("--file", required=True, help="Path to CSV file")

    # compute-tri
    tri = sub.add_parser("compute-tri", help="Compute adjusted close + TRI")
    tri.add_argument("--symbol", help="Single symbol to compute")
    tri.add_argument("--all", dest="all_symbols", action="store_true",
                     help="Compute for all symbols with OHLCV data")
    tri.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    tri.add_argument("--end-date", help="End date (YYYY-MM-DD)")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.command == "import-csv":
        result = asyncio.run(import_csv(args.file))
        print(json.dumps(result, indent=2, default=str))
    elif args.command == "compute-tri":
        if not args.symbol and not args.all_symbols:
            parser.error("Must specify --symbol or --all")
        result = asyncio.run(compute_tri(
            symbol=args.symbol,
            all_symbols=args.all_symbols,
            start_date=args.start_date,
            end_date=args.end_date,
        ))
        print(json.dumps(result, indent=2, default=str))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
