"""
Backfill all registry stocks from NGX Official List PDFs.

Downloads daily PDFs from doclib.ngxgroup.com (real exchange data)
and stores OHLCV records for all stocks.
"""
import asyncio
import logging
import sys
import time
from datetime import date, timedelta
from typing import List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
)
# Suppress noisy per-request httpx logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def main():
    from app.data.sources.ngx_stocks import NGXStockRegistry
    from app.data.sources.ngx_official_list import NgxOfficialListProvider
    from app.data.historical.storage import get_historical_storage

    registry = NGXStockRegistry()
    all_symbols = sorted(registry.STOCKS.keys())

    print(f"=== NGX PDF Backfill ===")
    print(f"Registry stocks: {len(all_symbols)}")

    end_date = date(2026, 2, 20)  # latest available PDF
    start_date = end_date - timedelta(days=250)

    # Count expected trading days
    d = start_date
    trading_days = 0
    while d <= end_date:
        if d.weekday() < 5:
            trading_days += 1
        d += timedelta(days=1)

    print(f"Date range: {start_date} → {end_date} ({trading_days} trading days)")
    print()

    provider = NgxOfficialListProvider()
    storage = get_historical_storage()

    total_records = 0
    total_pdfs = 0
    missing_dates: List[date] = []
    t0 = time.time()

    current = start_date
    while current <= end_date:
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        records, provenance = await provider.fetch_date(current, all_symbols)
        if records:
            stored, errors = storage.store_ohlcv_batch(records)
            total_records += stored
            total_pdfs += 1
            elapsed = time.time() - t0
            pct = total_pdfs / trading_days * 100
            print(
                f"  [{total_pdfs:3d}/{trading_days}] {current} "
                f"→ {len(records):3d} records, {stored:3d} stored "
                f"({pct:.0f}% done, {elapsed:.0f}s elapsed)",
                flush=True,
            )
        else:
            missing_dates.append(current)

        current += timedelta(days=1)

    elapsed = time.time() - t0
    print(f"\n=== Complete in {elapsed:.0f}s ===")
    print(f"PDFs processed: {total_pdfs}")
    print(f"Records stored: {total_records:,}")
    print(f"Missing dates: {len(missing_dates)}")

    # Summary per symbol
    print(f"\n=== Per-Symbol Results ===")
    success = 0
    insufficient = []
    for symbol in all_symbols:
        meta = storage.get_metadata(symbol)
        sessions = meta.total_sessions if meta else 0
        flag = "✓" if sessions >= 60 else "✗"
        if sessions >= 60:
            success += 1
        else:
            insufficient.append((symbol, sessions))
        print(f"  {flag} {symbol:20s} {sessions:4d} sessions")

    print(f"\n{success}/{len(all_symbols)} stocks with ≥60 sessions")
    if insufficient:
        print(f"\nInsufficient ({len(insufficient)}):")
        for sym, n in insufficient:
            print(f"  {sym}: {n} sessions")


if __name__ == "__main__":
    asyncio.run(main())
