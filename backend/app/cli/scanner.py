"""
Scanner CLI — run quality scans from the command line.

Usage:
  python -m app.cli.scanner run --universe top_liquid_50 --as-of 2025-06-15
  python -m app.cli.scanner run --universe top_liquid_50 --force
  python -m app.cli.scanner recompute --run-id 42
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.db.engine import get_session_factory
from app.scanner.workflow import run_scan

logger = logging.getLogger(__name__)


async def _run(universe: str, as_of_str: str, top_n: int, force: bool) -> None:
    as_of = date.fromisoformat(as_of_str) if as_of_str else date.today()

    factory = get_session_factory()
    async with factory() as session:
        summary = await run_scan(
            session,
            universe_name=universe,
            as_of=as_of,
            top_n=top_n,
            persist=True,
            force=force,
        )

    print(json.dumps(summary, indent=2, default=str))


async def _recompute(run_id: int) -> None:
    """
    Recompute a scan using the provenance stored in an existing ScanRun.

    Reads the original run's provenance (universe_name, as_of, top_n),
    deletes the old results, and re-runs with force=True.
    """
    from sqlalchemy import select, delete
    from app.db.models import ScanRun, ScanResult

    factory = get_session_factory()
    async with factory() as session:
        run = (await session.execute(
            select(ScanRun).where(ScanRun.id == run_id)
        )).scalar_one_or_none()

        if not run:
            print(f"Error: ScanRun {run_id} not found")
            return

        provenance = run.provenance or {}
        universe_name = provenance.get("universe_name", run.universe_name)
        as_of = run.as_of_date
        top_n = provenance.get("top_n", 50)

        print(f"Recomputing run {run_id}: universe={universe_name}, "
              f"as_of={as_of}, top_n={top_n}")
        print(f"Original provenance: {json.dumps(provenance, indent=2, default=str)}")

        # Delete old results (cascade from FK would do this, but be explicit)
        await session.execute(
            delete(ScanResult).where(ScanResult.run_id == run_id)
        )
        await session.execute(
            delete(ScanRun).where(ScanRun.id == run_id)
        )
        await session.commit()

        # Re-run
        summary = await run_scan(
            session,
            universe_name=universe_name,
            as_of=as_of,
            top_n=top_n,
            persist=True,
            force=True,
        )

    print(json.dumps(summary, indent=2, default=str))

    # Compare hashes
    new_prov = summary.get("provenance", {})
    old_config_hash = provenance.get("scoring_config_hash")
    new_config_hash = new_prov.get("scoring_config_hash")
    old_fund_hash = provenance.get("fundamentals_hash")
    new_fund_hash = new_prov.get("fundamentals_hash")

    print("\n── Reproducibility Check ──")
    if old_config_hash and new_config_hash:
        match = "✓ MATCH" if old_config_hash == new_config_hash else "✗ CHANGED"
        print(f"  Scoring config: {match} (old={old_config_hash}, new={new_config_hash})")
    if old_fund_hash and new_fund_hash:
        match = "✓ MATCH" if old_fund_hash == new_fund_hash else "✗ CHANGED"
        print(f"  Fundamentals:   {match} (old={old_fund_hash}, new={new_fund_hash})")


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="NGX Quality Scanner CLI")
    sub = parser.add_subparsers(dest="command")

    run_cmd = sub.add_parser("run", help="Run a quality scan")
    run_cmd.add_argument("--universe", default="top_liquid_50",
                         help="Universe name (default: top_liquid_50)")
    run_cmd.add_argument("--as-of", default=None,
                         help="As-of date YYYY-MM-DD (default: today)")
    run_cmd.add_argument("--top-n", type=int, default=50,
                         help="Max universe members (default: 50)")
    run_cmd.add_argument("--force", action="store_true",
                         help="Force re-run even if scan exists for this date")

    recompute_cmd = sub.add_parser("recompute", help="Recompute an existing scan run")
    recompute_cmd.add_argument("--run-id", type=int, required=True,
                               help="ID of the ScanRun to recompute")

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(_run(args.universe, args.as_of, args.top_n, args.force))
    elif args.command == "recompute":
        asyncio.run(_recompute(args.run_id))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
