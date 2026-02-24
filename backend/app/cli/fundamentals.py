"""
CLI for fundamentals data management.

Usage:
  python -m app.cli.fundamentals import-csv --csv data/fundamentals.csv --source "annual_reports_2024"
  python -m app.cli.fundamentals compute-derived --as-of 2025-12-31
"""

import argparse
import asyncio
import os
import sys
import logging
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.scanner.fundamentals_csv import parse_fundamentals_csv
from app.scanner.derived_metrics import compute_derived_metrics
from app.db.models import FundamentalsPeriodic, FundamentalsDerived, AuditEvent
from app.db.engine import get_session_factory

logger = logging.getLogger(__name__)


async def import_csv(csv_path: str, source: str) -> None:
    """Import fundamentals from a CSV file into the database."""
    if not os.path.exists(csv_path):
        print(f"ERROR: File not found: {csv_path}")
        return

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    result = parse_fundamentals_csv(content, default_source=source)

    print(f"Parsed: {result.rows_total} rows, {result.rows_accepted} accepted, "
          f"{result.rows_rejected} rejected")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for err in result.errors[:20]:
            print(f"  Row {err.row}, {err.field}: {err.message}")
        if len(result.errors) > 20:
            print(f"  ... and {len(result.errors) - 20} more")

    if not result.records:
        print("No records to import.")
        return

    factory = get_session_factory()
    async with factory() as session:
        inserted = 0
        skipped = 0

        for rec in result.records:
            # Check for existing record (upsert logic)
            from sqlalchemy import select
            stmt = select(FundamentalsPeriodic).where(
                FundamentalsPeriodic.symbol == rec["symbol"],
                FundamentalsPeriodic.period_end_date == rec["period_end_date"],
                FundamentalsPeriodic.period_type == rec["period_type"],
                FundamentalsPeriodic.source == rec["source"],
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()

            if existing:
                # Update existing record
                for key, val in rec.items():
                    if key not in ("symbol", "period_end_date", "period_type", "source"):
                        setattr(existing, key, val)
                existing.ingested_at = datetime.utcnow()
                existing.provenance = {
                    "csv_hash": result.csv_hash,
                    "csv_path": os.path.basename(csv_path),
                    "import_source": source,
                    "updated": True,
                }
                skipped += 1  # count as update, not insert
            else:
                row = FundamentalsPeriodic(
                    **rec,
                    provenance={
                        "csv_hash": result.csv_hash,
                        "csv_path": os.path.basename(csv_path),
                        "import_source": source,
                    },
                )
                session.add(row)
                inserted += 1

        # Write audit event
        session.add(AuditEvent(
            component="scanner",
            event_type="FUNDAMENTALS_IMPORT",
            level="INFO",
            message=f"Imported fundamentals from {os.path.basename(csv_path)}",
            payload={
                "csv_path": csv_path,
                "source": source,
                "csv_hash": result.csv_hash,
                "rows_total": result.rows_total,
                "rows_accepted": result.rows_accepted,
                "rows_rejected": result.rows_rejected,
                "inserted": inserted,
                "updated": skipped,
                "error_count": len(result.errors),
            },
        ))

        await session.commit()
        print(f"\nDatabase: {inserted} inserted, {skipped} updated")
        print(f"Audit event written.")


async def compute_derived(as_of_str: str) -> None:
    """Compute derived metrics for all symbols with fundamentals data."""
    as_of = date.fromisoformat(as_of_str)

    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import select, distinct

        # Get all distinct symbols with fundamentals
        symbols_stmt = select(distinct(FundamentalsPeriodic.symbol))
        symbols = [row[0] for row in (await session.execute(symbols_stmt)).all()]

        if not symbols:
            print("No fundamentals data found. Import data first.")
            return

        print(f"Computing derived metrics for {len(symbols)} symbols as_of={as_of}...")

        computed = 0
        for symbol in sorted(symbols):
            # Fetch all periods for this symbol
            periods_stmt = (
                select(FundamentalsPeriodic)
                .where(FundamentalsPeriodic.symbol == symbol)
                .order_by(FundamentalsPeriodic.period_end_date.asc())
            )
            rows = (await session.execute(periods_stmt)).scalars().all()

            periods = [
                {
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
                for r in rows
            ]

            metrics = compute_derived_metrics(symbol, periods, as_of)

            # Upsert derived record
            existing_stmt = select(FundamentalsDerived).where(
                FundamentalsDerived.symbol == symbol,
                FundamentalsDerived.as_of_date == as_of,
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()

            if existing:
                for attr in ("roe", "roic_proxy", "op_margin", "net_margin",
                             "debt_to_equity", "cash_to_debt", "ocf_to_net_income",
                             "fcf", "earnings_stability", "margin_stability",
                             "data_freshness_days", "periods_available"):
                    setattr(existing, attr, getattr(metrics, attr))
                existing.red_flags = metrics.red_flags
                existing.computed_at = datetime.utcnow()
            else:
                session.add(FundamentalsDerived(
                    symbol=symbol,
                    as_of_date=as_of,
                    roe=metrics.roe,
                    roic_proxy=metrics.roic_proxy,
                    op_margin=metrics.op_margin,
                    net_margin=metrics.net_margin,
                    debt_to_equity=metrics.debt_to_equity,
                    cash_to_debt=metrics.cash_to_debt,
                    ocf_to_net_income=metrics.ocf_to_net_income,
                    fcf=metrics.fcf,
                    earnings_stability=metrics.earnings_stability,
                    margin_stability=metrics.margin_stability,
                    data_freshness_days=metrics.data_freshness_days,
                    periods_available=metrics.periods_available,
                    red_flags=metrics.red_flags,
                    provenance={"source": "compute_derived", "as_of": as_of.isoformat()},
                ))

            computed += 1
            flags = f" [{', '.join(metrics.red_flags)}]" if metrics.red_flags else ""
            print(f"  {symbol}: periods={metrics.periods_available}, "
                  f"freshness={metrics.data_freshness_days}d{flags}")

        # Audit event
        session.add(AuditEvent(
            component="scanner",
            event_type="DERIVED_METRICS_COMPUTED",
            level="INFO",
            message=f"Computed derived metrics for {computed} symbols as_of={as_of}",
            payload={"as_of": as_of.isoformat(), "symbols_computed": computed},
        ))

        await session.commit()
        print(f"\nComputed derived metrics for {computed} symbols.")


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Fundamentals data management")
    sub = parser.add_subparsers(dest="command")

    imp = sub.add_parser("import-csv", help="Import fundamentals from CSV")
    imp.add_argument("--csv", required=True, help="Path to CSV file")
    imp.add_argument("--source", default="manual_csv", help="Source label")

    comp = sub.add_parser("compute-derived", help="Compute derived metrics")
    comp.add_argument("--as-of", required=True, help="As-of date (YYYY-MM-DD)")

    args = parser.parse_args()

    if args.command == "import-csv":
        asyncio.run(import_csv(args.csv, args.source))
    elif args.command == "compute-derived":
        asyncio.run(compute_derived(args.as_of))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
