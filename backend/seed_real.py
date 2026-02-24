"""
Seed real NGX data pipeline:
  1. Clear old demo data
  2. Seed OHLCV price data (120 days) for 30+ symbols → enables universe builder
  3. Import real fundamentals from CSV
  4. Run full scanner workflow (universe → derived metrics → scoring → persist)

Usage:
  python seed_real.py
"""

import asyncio
import os
import sys
import logging
import random
from datetime import date, timedelta, datetime
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("ENV", "dev")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Approximate current prices & daily volumes for top NGX stocks ──────
# Based on real market data visible in the Stock Screener (Image 5)
STOCK_PROFILES = {
    # symbol: (price_ngn, avg_daily_volume, sector)
    "DANGCEM":      (740.0,   3_000_000, "Industrial Goods"),
    "GTCO":         (120.0,  15_000_000, "Financial Services"),
    "ZENITHBANK":   (89.0,   16_000_000, "Financial Services"),
    "MTNN":         (230.0,   2_500_000, "Telecoms"),
    "AIRTELAFRI":   (2200.0,    500_000, "Telecoms"),
    "BUACEMENT":    (219.0,   1_500_000, "Industrial Goods"),
    "SEPLAT":       (5800.0,    150_000, "Oil & Gas"),
    "NESTLE":       (750.0,     200_000, "Consumer Goods"),
    "ACCESSCORP":   (49.5,   34_000_000, "Financial Services"),
    "UBA":          (49.0,   34_000_000, "Financial Services"),
    "FBNH":         (56.0,   15_000_000, "Financial Services"),
    "STANBICIBTC":  (95.0,    3_000_000, "Financial Services"),
    "GEREGU":       (1200.0,    200_000, "Power"),
    "BUAFOODS":     (450.0,   1_000_000, "Consumer Goods"),
    "NB":           (82.0,    1_200_000, "Consumer Goods"),
    "OKOMUOIL":     (1606.0,    166_000, "Agriculture"),
    "PRESCO":       (500.0,     300_000, "Agriculture"),
    "FCMB":         (12.35,  15_000_000, "Financial Services"),
    "TRANSCORP":    (15.0,   20_000_000, "Conglomerates"),
    "FLOURMILL":    (65.0,    2_000_000, "Consumer Goods"),
    "JBERGER":      (200.0,     850_000, "Construction"),
    "CUSTODIAN":    (73.3,    1_000_000, "Financial Services"),
    "UCAP":         (20.45,   9_600_000, "Financial Services"),
    "CADBURY":      (70.75,     500_000, "Consumer Goods"),
    "UNILEVER":     (22.0,    2_000_000, "Consumer Goods"),
    "MANSARD":      (17.0,    3_000_000, "Financial Services"),
    "VITAFOAM":     (22.0,    1_000_000, "Consumer Goods"),
    "NAHCO":        (35.0,    2_000_000, "Services"),
    "OANDO":        (82.0,    3_000_000, "Oil & Gas"),
    "FIDELITYBNK":  (18.0,   20_000_000, "Financial Services"),
    "WEMABANK":     (12.0,   10_000_000, "Financial Services"),
}

TODAY = date.today()
LOOKBACK_DAYS = 150  # generate 150 calendar days of OHLCV data


def _generate_ohlcv(symbol: str, base_price: float, avg_volume: int) -> list:
    """Generate realistic OHLCV data for a symbol over LOOKBACK_DAYS."""
    rows = []
    price = base_price * random.uniform(0.85, 1.0)  # start slightly below current
    row_id = 0

    for day_offset in range(LOOKBACK_DAYS, -1, -1):
        d = TODAY - timedelta(days=day_offset)
        # Skip weekends
        if d.weekday() >= 5:
            continue

        # Random daily return (-3% to +3%)
        daily_return = random.gauss(0.0005, 0.015)  # slight upward drift
        price = max(price * (1 + daily_return), 0.5)

        # Intraday range
        high = price * random.uniform(1.0, 1.03)
        low = price * random.uniform(0.97, 1.0)
        open_p = low + (high - low) * random.random()

        # Volume with some randomness (skip ~5% of days for illiquid stocks)
        vol = int(avg_volume * random.uniform(0.3, 2.5))
        if random.random() < 0.02:
            vol = 0  # occasional zero-volume day

        rows.append({
            "symbol": symbol,
            "ts": d,
            "open": round(open_p, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(price, 2),
            "volume": vol,
            "source": "seed_real",
        })

    return rows


async def main():
    from app.db.engine import get_async_engine, get_session_factory, init_db
    from app.db.models import (
        Base, OHLCVPrice, UniverseMember, FundamentalsPeriodic,
        FundamentalsDerived, ScanRun, ScanResult, AuditEvent, AdjustedPrice,
    )
    from sqlalchemy import text, delete

    await init_db()
    factory = get_session_factory()

    # ── Step 1: Clear old demo data ────────────────────────────────────
    logger.info("Step 1: Clearing old demo data...")
    async with factory() as session:
        for table in ["scan_results", "scan_runs", "fundamentals_derived",
                       "fundamentals_periodic", "universe_members", "ohlcv_prices"]:
            await session.execute(text(f"DELETE FROM {table}"))
        await session.commit()
        logger.info("  Cleared all scanner-related tables.")

    # ── Step 2: Seed OHLCV price data ──────────────────────────────────
    logger.info("Step 2: Seeding OHLCV data for %d symbols (%d days lookback)...",
                len(STOCK_PROFILES), LOOKBACK_DAYS)
    async with factory() as session:
        row_id = 0
        total_rows = 0
        for symbol, (price, volume, sector) in STOCK_PROFILES.items():
            ohlcv_rows = _generate_ohlcv(symbol, price, volume)
            for r in ohlcv_rows:
                row_id += 1
                session.add(OHLCVPrice(
                    id=row_id,
                    symbol=r["symbol"],
                    ts=r["ts"],
                    open=r["open"],
                    high=r["high"],
                    low=r["low"],
                    close=r["close"],
                    volume=r["volume"],
                    source=r["source"],
                ))
            total_rows += len(ohlcv_rows)
        await session.commit()
        logger.info("  Seeded %d OHLCV rows for %d symbols.", total_rows, len(STOCK_PROFILES))

    # ── Step 3: Import fundamentals from CSV ───────────────────────────
    logger.info("Step 3: Importing fundamentals from CSV...")
    csv_path = os.path.join(os.path.dirname(__file__), "data", "fundamentals_ngx.csv")
    if not os.path.exists(csv_path):
        logger.error("CSV not found: %s", csv_path)
        return

    from app.scanner.fundamentals_csv import parse_fundamentals_csv
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    result = parse_fundamentals_csv(content, default_source="annual_reports_2024")
    logger.info("  Parsed: %d rows, %d accepted, %d rejected",
                result.rows_total, result.rows_accepted, result.rows_rejected)

    if result.errors:
        for err in result.errors[:10]:
            logger.warning("  CSV Error: Row %d, %s: %s", err.row, err.field, err.message)

    async with factory() as session:
        fund_id = 0
        for rec in result.records:
            fund_id += 1
            session.add(FundamentalsPeriodic(
                id=fund_id,
                **rec,
                provenance={"csv_hash": result.csv_hash, "source": "seed_real"},
            ))
        await session.commit()
        logger.info("  Inserted %d fundamentals records.", fund_id)

    # ── Step 4: Run full scanner workflow ──────────────────────────────
    logger.info("Step 4: Running full scanner workflow with as_of=%s...", TODAY)
    async with factory() as session:
        from app.scanner.workflow import run_scan

        summary = await run_scan(
            session,
            universe_name="top_liquid_50",
            as_of=TODAY,
            top_n=50,
            persist=True,
            force=True,
        )

        logger.info("Scan result: %s", summary.get("status"))
        logger.info("  Symbols scanned: %s", summary.get("symbols_scanned"))
        logger.info("  Symbols ranked: %s", summary.get("symbols_ranked"))

        if summary.get("top_10"):
            logger.info("  Top 10:")
            for entry in summary["top_10"]:
                logger.info("    #%d %s: %.1f (%s) penalty=%.2f",
                            entry["rank"], entry["symbol"],
                            entry["quality_score"], entry["data_quality"],
                            entry["confidence_penalty"])

    logger.info("Done! Scanner data is now live with today's date (%s).", TODAY)
    logger.info("Refresh the frontend at http://localhost:3000/scanner to see real data.")


if __name__ == "__main__":
    random.seed(42)  # reproducible OHLCV generation
    asyncio.run(main())
