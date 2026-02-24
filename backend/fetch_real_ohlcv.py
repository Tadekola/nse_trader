"""
Fetch real OHLCV data from ngnmarket.com and afx.kwayisi.org,
then persist to the main SQLAlchemy DB.

Strategy:
1. Fetch current-day real prices from ngnmarket.com (31 symbols)
2. Fetch historical OHLCV from afx.kwayisi.org (HTML table scraping)
3. For symbols lacking sufficient history, generate anchored backfill:
   backward random walk from the REAL current price so the latest price
   is always genuine market data.
4. Write all rows into the OHLCVPrice table used by the scanner.
"""

import asyncio
import json
import math
import random
import re
import sys
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Run: pip install httpx")
    sys.exit(1)

# ── Symbols & mappings ───────────────────────────────────────────────
SYMBOLS = [
    "DANGCEM", "GTCO", "ZENITHBANK", "MTNN", "AIRTELAFRI",
    "BUACEMENT", "SEPLAT", "NESTLE", "ACCESSCORP", "UBA",
    "FIRSTHOLDCO", "STANBIC", "GEREGU", "BUAFOODS", "NB",
    "OKOMUOIL", "PRESCO", "FCMB", "TRANSCORP",
    "JBERGER", "CUSTODIAN", "UCAP", "CADBURY", "UNILEVER",
    "MANSARD", "VITAFOAM", "NAHCO", "OANDO", "FIDELITYBK",
    "WEMABANK",
]

# Canonical symbol → ngnmarket.com URL slug (try multiple variants)
NGNMARKET_VARIANTS: Dict[str, List[str]] = {
    "FIRSTHOLDCO": ["FIRSTHOLDCO", "FBNHOLDINGS", "FBNH"],
    "STANBIC": ["STANBIC", "STANBICIBTC"],
    "FIDELITYBK":  ["FIDELITYBK", "FIDELITYBNK"],
}

# Canonical symbol → kwayisi slug
KWAYISI_MAP: Dict[str, str] = {
    "FIRSTHOLDCO": "FIRSTHOLDCO",
    "STANBIC": "STANBIC",
    "FIDELITYBK": "FIDELITYBK",
}

# Avg daily volume estimates for backfill (used when real volume unavailable)
AVG_VOLUMES: Dict[str, int] = {
    "DANGCEM": 2_000_000, "GTCO": 15_000_000, "ZENITHBANK": 20_000_000,
    "MTNN": 3_000_000, "AIRTELAFRI": 500_000, "BUACEMENT": 1_500_000,
    "SEPLAT": 400_000, "NESTLE": 200_000, "ACCESSCORP": 25_000_000,
    "UBA": 15_000_000, "FIRSTHOLDCO": 20_000_000, "STANBIC": 1_500_000,
    "GEREGU": 500_000, "BUAFOODS": 1_000_000, "NB": 800_000,
    "OKOMUOIL": 300_000, "PRESCO": 250_000, "FCMB": 10_000_000,
    "TRANSCORP": 5_000_000, "JBERGER": 850_000,
    "CUSTODIAN": 1_000_000, "UCAP": 9_600_000, "CADBURY": 500_000,
    "UNILEVER": 2_000_000, "MANSARD": 3_000_000, "VITAFOAM": 1_000_000,
    "NAHCO": 2_000_000, "OANDO": 3_000_000, "FIDELITYBK": 20_000_000,
    "WEMABANK": 10_000_000,
}

BACKFILL_DAYS = 150  # trading days of history to generate if needed

NGNMARKET_BASE = "https://www.ngnmarket.com/stocks/{symbol}"
KWAYISI_BASE = "https://afx.kwayisi.org/ngx/{symbol}/"


# ── Parsing helpers ──────────────────────────────────────────────────
def parse_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        if isinstance(val, str):
            val = val.replace(",", "").strip()
        f = float(val)
        return f if f > 0 else None
    except (ValueError, TypeError):
        return None


def parse_int(val: Any) -> int:
    if val is None:
        return 0
    try:
        if isinstance(val, str):
            val = val.replace(",", "").strip()
        return int(float(val))
    except (ValueError, TypeError):
        return 0


# ══════════════════════════════════════════════════════════════════════
# TIER 1: ngnmarket.com — real current-day snapshot
# ══════════════════════════════════════════════════════════════════════
async def fetch_ngnmarket(
    client: httpx.AsyncClient, symbol: str
) -> Optional[dict]:
    """Return a single current-day OHLCV dict, or None."""
    slugs = NGNMARKET_VARIANTS.get(symbol, [symbol])

    for slug in slugs:
        url = NGNMARKET_BASE.format(symbol=slug)
        try:
            resp = await client.get(url, follow_redirects=True)
        except httpx.HTTPError as e:
            logger.debug(f"{symbol}/{slug}: HTTP error - {e}")
            continue

        if resp.status_code != 200:
            continue

        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            resp.text, re.DOTALL,
        )
        if not m:
            continue

        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue

        company = data.get("props", {}).get("pageProps", {}).get("ssCompany", {})
        if not company:
            continue

        price = parse_float(company.get("currentPrice"))
        if not price:
            continue

        open_p = parse_float(company.get("openPrice")) or price
        high = parse_float(company.get("dayHigh")) or price
        low = parse_float(company.get("dayLow")) or price
        vol = parse_int(company.get("volume"))

        logger.info(f"{symbol}: ngnmarket OK via /{slug} — ₦{price:,.2f}")
        return {
            "symbol": symbol,
            "ts": date.today(),
            "open": round(open_p, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(price, 2),
            "volume": vol,
            "source": "ngnmarket_live",
        }

    logger.warning(f"{symbol}: ngnmarket FAILED (tried {slugs})")
    return None


# ══════════════════════════════════════════════════════════════════════
# TIER 2: afx.kwayisi.org — historical OHLCV from HTML table
# ══════════════════════════════════════════════════════════════════════
async def fetch_kwayisi_history(
    client: httpx.AsyncClient, symbol: str
) -> List[dict]:
    """Scrape historical OHLCV from kwayisi.org stock page."""
    slug = KWAYISI_MAP.get(symbol, symbol).lower()
    url = KWAYISI_BASE.format(symbol=slug)

    try:
        resp = await client.get(url, follow_redirects=True)
    except httpx.HTTPError as e:
        logger.debug(f"{symbol}: kwayisi error - {e}")
        return []

    if resp.status_code != 200:
        logger.debug(f"{symbol}: kwayisi HTTP {resp.status_code}")
        return []

    rows: List[dict] = []

    # kwayisi.org has a table with columns: Date, Open, High, Low, Close, Volume
    # Look for table rows in the HTML
    table_match = re.search(r'<table[^>]*class="[^"]*data[^"]*"[^>]*>(.*?)</table>',
                            resp.text, re.DOTALL | re.IGNORECASE)
    if not table_match:
        # Try any table
        table_match = re.search(r'<table[^>]*>(.*?)</table>', resp.text, re.DOTALL)

    if not table_match:
        logger.debug(f"{symbol}: kwayisi no table found")
        return []

    table_html = table_match.group(1)
    tr_pattern = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)

    for tr in tr_pattern:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        if len(cells) < 5:
            continue

        # Clean HTML tags from cell content
        clean_cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]

        # Try to parse as: Date, Open, High, Low, Close, [Volume]
        date_str = clean_cells[0]
        d = None
        for fmt in ("%b %d, %Y", "%Y-%m-%d", "%d %b %Y", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                d = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue

        if not d:
            continue

        o = parse_float(clean_cells[1])
        h = parse_float(clean_cells[2])
        l = parse_float(clean_cells[3])
        c = parse_float(clean_cells[4])
        v = parse_int(clean_cells[5]) if len(clean_cells) > 5 else 0

        if not c:
            continue

        rows.append({
            "symbol": symbol,
            "ts": d,
            "open": round(o or c, 2),
            "high": round(h or c, 2),
            "low": round(l or c, 2),
            "close": round(c, 2),
            "volume": v,
            "source": "kwayisi_historical",
        })

    if rows:
        logger.info(f"{symbol}: kwayisi OK — {len(rows)} historical rows")
    else:
        logger.debug(f"{symbol}: kwayisi no parseable rows")

    return rows


# ══════════════════════════════════════════════════════════════════════
# TIER 3: Anchored backfill — backward random walk from real price
# ══════════════════════════════════════════════════════════════════════
def generate_anchored_backfill(
    symbol: str,
    anchor_price: float,
    anchor_date: date,
    num_trading_days: int = BACKFILL_DAYS,
    avg_volume: int = 1_000_000,
) -> List[dict]:
    """
    Generate realistic historical OHLCV working backward from a real anchor price.

    Uses backward random walk: today's price is real, older prices are derived
    by undoing realistic daily returns. This ensures the most recent data point
    is always genuine.
    """
    rows = []
    price = anchor_price

    # Walk backward from anchor_date
    current = anchor_date - timedelta(days=1)
    day_count = 0

    while day_count < num_trading_days:
        # Skip weekends
        if current.weekday() >= 5:
            current -= timedelta(days=1)
            continue

        # Reverse a realistic daily return
        daily_return = random.gauss(0.0003, 0.018)  # slight drift, ~1.8% vol
        prev_price = price / (1 + daily_return)
        prev_price = max(prev_price, 0.50)

        # Intraday range
        spread = abs(daily_return) + random.uniform(0.005, 0.02)
        high = prev_price * (1 + spread / 2)
        low = prev_price * (1 - spread / 2)
        open_p = low + (high - low) * random.random()

        vol = int(avg_volume * random.uniform(0.3, 2.2))
        if random.random() < 0.02:
            vol = 0  # occasional zero-vol day

        rows.append({
            "symbol": symbol,
            "ts": current,
            "open": round(open_p, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(prev_price, 2),
            "volume": vol,
            "source": "anchored_backfill",
        })

        price = prev_price
        current -= timedelta(days=1)
        day_count += 1

    rows.reverse()  # chronological order
    return rows


# ══════════════════════════════════════════════════════════════════════
# Orchestration
# ══════════════════════════════════════════════════════════════════════
async def fetch_all() -> Tuple[List[dict], Dict[str, float]]:
    """
    Fetch real OHLCV for all symbols.

    Returns (all_rows, real_prices) where real_prices maps symbol→close
    for symbols that got real ngnmarket data.
    """
    all_rows: List[dict] = []
    real_prices: Dict[str, float] = {}

    async with httpx.AsyncClient(timeout=20.0) as client:
        sem = asyncio.Semaphore(5)

        # ── Phase 1: ngnmarket current prices ────────────────────────
        async def ngn_fetch(sym: str):
            async with sem:
                await asyncio.sleep(0.3)
                return await fetch_ngnmarket(client, sym)

        tasks = [ngn_fetch(s) for s in SYMBOLS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sym, result in zip(SYMBOLS, results):
            if isinstance(result, Exception):
                logger.error(f"{sym}: ngnmarket exception - {result}")
            elif result:
                all_rows.append(result)
                real_prices[sym] = result["close"]

        print(f"\n  ngnmarket: {len(real_prices)}/{len(SYMBOLS)} symbols with real prices")

        # ── Phase 2: kwayisi historical ──────────────────────────────
        kwayisi_total = 0
        async def kw_fetch(sym: str):
            async with sem:
                await asyncio.sleep(0.5)
                return await fetch_kwayisi_history(client, sym)

        kw_tasks = [kw_fetch(s) for s in SYMBOLS]
        kw_results = await asyncio.gather(*kw_tasks, return_exceptions=True)

        for sym, result in zip(SYMBOLS, kw_results):
            if isinstance(result, Exception):
                logger.debug(f"{sym}: kwayisi exception - {result}")
            elif result:
                all_rows.extend(result)
                kwayisi_total += len(result)
                # If we didn't get a ngnmarket price, use kwayisi's latest
                if sym not in real_prices and result:
                    latest = max(result, key=lambda r: r["ts"])
                    real_prices[sym] = latest["close"]

        print(f"  kwayisi:   {kwayisi_total} historical rows across symbols")

    return all_rows, real_prices


def add_anchored_backfill(
    all_rows: List[dict], real_prices: Dict[str, float]
) -> List[dict]:
    """Add backfill for symbols that lack sufficient history."""
    # Count existing rows per symbol
    rows_per_symbol: Dict[str, int] = {}
    earliest_per_symbol: Dict[str, date] = {}
    for r in all_rows:
        sym = r["symbol"]
        rows_per_symbol[sym] = rows_per_symbol.get(sym, 0) + 1
        if sym not in earliest_per_symbol or r["ts"] < earliest_per_symbol[sym]:
            earliest_per_symbol[sym] = r["ts"]

    backfill_rows: List[dict] = []
    for sym in SYMBOLS:
        existing = rows_per_symbol.get(sym, 0)
        if existing >= 50:
            continue  # enough history

        anchor = real_prices.get(sym)
        if not anchor:
            logger.warning(f"{sym}: no real price — skipping backfill")
            continue

        # Generate backfill up to BACKFILL_DAYS, avoiding overlap
        anchor_date = earliest_per_symbol.get(sym, date.today())
        need = BACKFILL_DAYS - existing
        if need <= 0:
            continue

        avg_vol = AVG_VOLUMES.get(sym, 1_000_000)
        bf = generate_anchored_backfill(sym, anchor, anchor_date, need, avg_vol)
        backfill_rows.extend(bf)
        logger.info(f"{sym}: +{len(bf)} anchored backfill rows (anchor ₦{anchor:,.2f})")

    return backfill_rows


def _deduplicate(rows: List[dict]) -> List[dict]:
    """Deduplicate by (symbol, ts) — keep real data over backfill."""
    SOURCE_PRIORITY = {
        "ngnmarket_live": 0,
        "kwayisi_historical": 1,
        "ngnmarket_historical": 2,
        "anchored_backfill": 3,
    }
    best: Dict[Tuple[str, date], dict] = {}
    for r in rows:
        key = (r["symbol"], r["ts"])
        if key not in best:
            best[key] = r
        else:
            existing_prio = SOURCE_PRIORITY.get(best[key]["source"], 9)
            new_prio = SOURCE_PRIORITY.get(r["source"], 9)
            if new_prio < existing_prio:
                best[key] = r
    return list(best.values())


def persist_to_historical_db(rows: List[dict]):
    """
    Write OHLCV rows into the HISTORICAL storage (historical_ohlcv.db).

    This is the database that the recommendation engine reads from
    via _build_price_dataframe → get_historical_storage().
    """
    from app.data.historical.storage import (
        get_historical_storage, OHLCVRecord,
    )

    storage = get_historical_storage()

    # Clear existing data by dropping and re-creating
    # (HistoricalOHLCVStorage uses INSERT OR IGNORE, so we need to clear first)
    import sqlite3
    conn = sqlite3.connect(str(storage.db_path))
    try:
        conn.execute("DELETE FROM ohlcv")
        conn.execute("DELETE FROM symbol_metadata")
        conn.commit()
        logger.info("Cleared historical_ohlcv.db")
    finally:
        conn.close()

    # Re-initialize to pick up clean state
    storage._initialized = False
    storage._init_db()

    records = [
        OHLCVRecord(
            symbol=r["symbol"],
            date=r["ts"],
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
            source=r["source"],
        )
        for r in rows
    ]

    stored, errors = storage.store_ohlcv_batch(records, validate=True)
    logger.info(
        f"Historical DB: {stored} stored, {len(errors)} validation errors"
    )

    # Verify
    stats = storage.get_stats()
    print(f"  historical_ohlcv.db: {stats}")


async def persist_to_db(rows: List[dict]):
    """Write OHLCV rows into the main SQLAlchemy OHLCVPrice table."""
    if not rows:
        logger.warning("No rows to persist.")
        return

    from app.db.engine import init_db, get_session_factory
    from app.db.models import OHLCVPrice

    await init_db()
    session_factory = get_session_factory()

    unique_rows = _deduplicate(rows)

    async with session_factory() as session:
        # Clear ALL old OHLCV data (synthetic + stale)
        from sqlalchemy import delete
        result = await session.execute(delete(OHLCVPrice))
        logger.info(f"Cleared {result.rowcount} old OHLCV rows")

        # Insert
        for r in unique_rows:
            session.add(OHLCVPrice(
                symbol=r["symbol"],
                ts=r["ts"],
                open=r["open"],
                high=r["high"],
                low=r["low"],
                close=r["close"],
                volume=r["volume"],
                source=r["source"],
            ))

        await session.commit()
        logger.info(f"Persisted {len(unique_rows)} OHLCV rows to main DB")

    # Also persist to the historical storage used by the recommendation engine
    persist_to_historical_db(unique_rows)

    # ── Print summary ────────────────────────────────────────────────
    unique_rows = _deduplicate(rows)
    symbols_data: Dict[str, Dict[str, Any]] = {}
    for r in unique_rows:
        sym = r["symbol"]
        if sym not in symbols_data:
            symbols_data[sym] = {"count": 0, "dates": [], "sources": set()}
        symbols_data[sym]["count"] += 1
        symbols_data[sym]["dates"].append(r["ts"])
        symbols_data[sym]["sources"].add(r["source"])

    print("\n" + "=" * 72)
    print("OHLCV DATA SUMMARY")
    print("=" * 72)
    total_real = 0
    total_backfill = 0
    for sym in sorted(symbols_data):
        info = symbols_data[sym]
        dates = sorted(info["dates"])
        src_labels = ", ".join(sorted(info["sources"]))
        real = sum(1 for d in unique_rows if d["symbol"] == sym and d["source"] != "anchored_backfill")
        bf = info["count"] - real
        total_real += real
        total_backfill += bf
        print(f"  {sym:15s}  {info['count']:3d} rows  ({dates[0]} → {dates[-1]})  [{src_labels}]")

    print(f"\nTotal: {len(unique_rows)} rows across {len(symbols_data)} symbols")
    print(f"  Real data:       {total_real} rows")
    print(f"  Anchored backfill: {total_backfill} rows")
    print("=" * 72)


def generate_asi_data(stock_rows: List[dict]) -> List[dict]:
    """
    Generate synthetic ASI (All Share Index) data from stock-level data.

    The ASI is a market-cap-weighted index. We approximate it by averaging
    the normalised price series of our stocks and scaling to a realistic
    ASI level (~100 000).
    """
    from collections import defaultdict

    # Group rows by date
    by_date: Dict[date, List[dict]] = defaultdict(list)
    for r in stock_rows:
        by_date[r["ts"]].append(r)

    if not by_date:
        return []

    ASI_BASE = 100_000.0
    sorted_dates = sorted(by_date.keys())

    # Build a simple equal-weight index from close prices
    # Normalise each symbol's close to its first-seen close
    first_close: Dict[str, float] = {}
    asi_rows: List[dict] = []

    for d in sorted_dates:
        day_rows = by_date[d]
        normalised = []
        for r in day_rows:
            sym = r["symbol"]
            if sym not in first_close:
                first_close[sym] = r["close"]
            if first_close[sym] > 0:
                normalised.append(r["close"] / first_close[sym])

        if not normalised:
            continue

        avg_norm = sum(normalised) / len(normalised)
        asi_close = round(ASI_BASE * avg_norm, 2)
        # Simulate OHLV around close
        spread = asi_close * 0.003  # 0.3 % daily spread
        asi_rows.append({
            "symbol": "ASI",
            "ts": d,
            "open": round(asi_close + random.uniform(-spread, spread), 2),
            "high": round(asi_close + abs(random.gauss(0, spread)), 2),
            "low": round(asi_close - abs(random.gauss(0, spread)), 2),
            "close": asi_close,
            "volume": random.randint(800_000_000, 1_500_000_000),
            "source": "synthetic_asi",
        })

    logger.info(f"ASI: generated {len(asi_rows)} index rows")
    return asi_rows


async def main():
    print("=" * 72)
    print("FETCHING REAL OHLCV DATA")
    print("=" * 72)

    # Fetch real data
    all_rows, real_prices = await fetch_all()
    print(f"\nPhase 1+2: {len(all_rows)} rows from live sources")

    # Add backfill where needed
    backfill = add_anchored_backfill(all_rows, real_prices)
    all_rows.extend(backfill)
    print(f"Phase 3:   +{len(backfill)} anchored backfill rows")

    # Generate ASI index data for regime detection
    asi_rows = generate_asi_data(all_rows)
    all_rows.extend(asi_rows)
    print(f"Phase 4:   +{len(asi_rows)} ASI index rows")

    # Persist
    if all_rows:
        await persist_to_db(all_rows)
    else:
        print("\nWARNING: No data at all. Check network connectivity.")


if __name__ == "__main__":
    asyncio.run(main())
