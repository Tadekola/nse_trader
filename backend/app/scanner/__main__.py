"""
Scanner scheduled entry point.

Usage:
  python -m app.scanner.scheduled --freq daily
  python -m app.scanner.scheduled --freq weekly --universe top_liquid_30
  python -m app.scanner.scheduled --freq daily --force
"""

import argparse
import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def _main(freq: str, universe: str, top_n: int, force: bool) -> None:
    from app.db.engine import get_session_factory
    from app.scanner.scheduled import run_scheduled_scan

    factory = get_session_factory()
    async with factory() as session:
        summary = await run_scheduled_scan(
            session,
            universe_name=universe,
            top_n=top_n,
            freq=freq,
            force=force,
        )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scheduled NGX Quality Scanner")
    parser.add_argument("--freq", choices=["daily", "weekly"], default="daily",
                        help="Scan frequency (default: daily)")
    parser.add_argument("--universe", default="top_liquid_50",
                        help="Universe name (default: top_liquid_50)")
    parser.add_argument("--top-n", type=int, default=50,
                        help="Max universe members (default: 50)")
    parser.add_argument("--force", action="store_true",
                        help="Override idempotency guard")
    args = parser.parse_args()
    asyncio.run(_main(args.freq, args.universe, args.top_n, args.force))
