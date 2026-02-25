"""
Lightweight Python-based scheduler for daily/weekly quality scans.

Runs as a long-lived process inside Docker (no crontab needed).
Schedule: Mon-Fri at 17:00 UTC (6PM WAT, after NGX close).

Usage:
    python scheduler.py
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, time, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")

# 17:00 UTC = 6PM WAT (after NGX market close at 2:30PM)
DAILY_RUN_TIME = time(17, 0, tzinfo=timezone.utc)
WEEKLY_RUN_DAY = 6  # Sunday
WEEKLY_RUN_TIME = time(20, 0, tzinfo=timezone.utc)

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Received signal %s, shutting down...", signum)
    _shutdown = True


def _seconds_until(target_time: time, now: datetime) -> float:
    """Seconds from now until the next occurrence of target_time today or tomorrow."""
    target_dt = datetime.combine(now.date(), target_time, tzinfo=timezone.utc)
    if target_dt <= now:
        target_dt += timedelta(days=1)
    return (target_dt - now).total_seconds()


async def run_daily_scan():
    """Execute the daily scheduled scan."""
    try:
        from app.scanner.scheduled import run_scheduled_scan
        from app.db.engine import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            summary = await run_scheduled_scan(session, freq="daily")
            logger.info("Daily scan complete: %s", summary)
    except Exception:
        logger.exception("Daily scan failed")


async def run_weekly_scan():
    """Execute the weekly scheduled scan."""
    try:
        from app.scanner.scheduled import run_scheduled_scan
        from app.db.engine import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            summary = await run_scheduled_scan(session, freq="weekly")
            logger.info("Weekly scan complete: %s", summary)
    except Exception:
        logger.exception("Weekly scan failed")


async def main():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("NSE Trader Scheduler started")
    logger.info("Daily scan: Mon-Fri at %s UTC", DAILY_RUN_TIME.strftime("%H:%M"))
    logger.info("Weekly scan: Sunday at %s UTC", WEEKLY_RUN_TIME.strftime("%H:%M"))

    last_daily_date = None
    last_weekly_date = None

    while not _shutdown:
        now = datetime.now(timezone.utc)
        weekday = now.weekday()  # 0=Mon, 6=Sun

        # Daily scan: Mon-Fri after DAILY_RUN_TIME
        if weekday < 5 and now.time() >= DAILY_RUN_TIME.replace(tzinfo=None):
            if last_daily_date != now.date():
                logger.info("Triggering daily scan for %s", now.date())
                await run_daily_scan()
                last_daily_date = now.date()

        # Weekly scan: Sunday after WEEKLY_RUN_TIME
        if weekday == WEEKLY_RUN_DAY and now.time() >= WEEKLY_RUN_TIME.replace(tzinfo=None):
            if last_weekly_date != now.date():
                logger.info("Triggering weekly scan for %s", now.date())
                await run_weekly_scan()
                last_weekly_date = now.date()

        # Sleep 60s between checks
        await asyncio.sleep(60)

    logger.info("Scheduler stopped")


if __name__ == "__main__":
    asyncio.run(main())
