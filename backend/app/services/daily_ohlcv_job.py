"""
Automated Daily OHLCV Fetch Job.

Runs as a background asyncio task on app startup. Fetches today's prices
from ngnmarket.com for all symbols and appends them to both databases.
Also generates today's ASI data point.

This ensures the historical DB grows daily without manual intervention,
which is critical for:
- Paper trading signal evaluation (forward prices)
- Accumulating longer backtest history
"""
import asyncio
import logging
from datetime import date, datetime, time, timezone

logger = logging.getLogger(__name__)

# Run daily at ~16:30 WAT (market closes 14:30, data settles by 16:00)
# If the server starts after this time, run immediately on first cycle
FETCH_HOUR_UTC = 15  # 15:00 UTC = 16:00 WAT
FETCH_MINUTE = 30
CHECK_INTERVAL_SECONDS = 300  # Check every 5 minutes


async def _fetch_today():
    """
    Fetch today's prices from ngnmarket and persist to both databases.
    Lightweight version of fetch_real_ohlcv.py that only grabs current-day data.
    """
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    try:
        import httpx
    except ImportError:
        logger.error("httpx not installed — daily fetch unavailable")
        return 0

    from fetch_real_ohlcv import (
        SYMBOLS, fetch_ngnmarket, generate_asi_data,
        persist_to_historical_db, _deduplicate,
    )

    all_rows = []
    real_prices = {}

    async with httpx.AsyncClient(timeout=20.0) as client:
        sem = asyncio.Semaphore(5)

        async def _fetch(sym):
            async with sem:
                await asyncio.sleep(0.3)
                return await fetch_ngnmarket(client, sym)

        tasks = [_fetch(s) for s in SYMBOLS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sym, result in zip(SYMBOLS, results):
            if isinstance(result, Exception):
                logger.debug("Daily fetch %s error: %s", sym, result)
            elif result:
                all_rows.append(result)
                real_prices[sym] = result["close"]

    if not all_rows:
        logger.warning("Daily fetch: no prices retrieved")
        return 0

    # Generate ASI for today
    asi_rows = generate_asi_data(all_rows)
    all_rows.extend(asi_rows)

    # Deduplicate
    unique = _deduplicate(all_rows)

    # Persist to historical DB only (main DB is secondary)
    persist_to_historical_db(unique)

    logger.info(
        "Daily fetch complete: %d prices for %s",
        len(real_prices), date.today().isoformat(),
    )
    return len(real_prices)


async def daily_ohlcv_loop():
    """
    Background loop that fetches OHLCV data once per trading day.

    Logic:
    - On startup, check if today's data already exists in the DB.
    - If not, fetch immediately.
    - Then check every 5 minutes if it's past fetch time and today hasn't been fetched yet.
    """
    logger.info("Daily OHLCV fetch job started")
    last_fetch_date = None

    # Check if today's data already exists
    try:
        import sqlite3
        from pathlib import Path
        db_path = Path(__file__).parent.parent.parent / "data" / "historical_ohlcv.db"
        conn = sqlite3.connect(str(db_path))
        cur = conn.execute(
            "SELECT COUNT(*) FROM ohlcv WHERE date = ? AND symbol != 'ASI'",
            (date.today().isoformat(),)
        )
        today_count = cur.fetchone()[0]
        conn.close()
        if today_count >= 20:  # Most symbols already fetched
            last_fetch_date = date.today()
            logger.info("Today's OHLCV data already exists (%d rows), skipping initial fetch", today_count)
    except Exception as e:
        logger.debug("Could not check existing data: %s", e)

    while True:
        try:
            today = date.today()
            now = datetime.now(timezone.utc)

            # Skip weekends (Sat=5, Sun=6)
            if today.weekday() >= 5:
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
                continue

            # Already fetched today?
            if last_fetch_date == today:
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
                continue

            # Is it past fetch time? Or is this the first run (no fetch yet)?
            past_fetch_time = (
                now.hour > FETCH_HOUR_UTC or
                (now.hour == FETCH_HOUR_UTC and now.minute >= FETCH_MINUTE)
            )

            if past_fetch_time or last_fetch_date is None:
                logger.info("Running daily OHLCV fetch for %s", today.isoformat())
                count = await _fetch_today()
                if count > 0:
                    last_fetch_date = today
                    logger.info("Daily OHLCV fetch successful: %d symbols", count)
                else:
                    logger.warning("Daily OHLCV fetch returned 0 symbols — will retry next cycle")

        except asyncio.CancelledError:
            logger.info("Daily OHLCV fetch job cancelled")
            break
        except Exception as e:
            logger.error("Daily OHLCV fetch error: %s", e)

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
