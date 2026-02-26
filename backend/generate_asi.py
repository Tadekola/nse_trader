"""Generate ASI (All-Share Index) from backfilled stock OHLCV data."""
import sqlite3
import random
from pathlib import Path
from collections import defaultdict

db_path = Path("data/historical_ohlcv.db")
conn = sqlite3.connect(str(db_path))

# Get all stock OHLCV data (exclude ASI)
rows = conn.execute(
    "SELECT symbol, date, open, high, low, close, volume FROM ohlcv WHERE symbol != 'ASI' ORDER BY date"
).fetchall()
print(f"Stock rows: {len(rows)}")

# Group by date
by_date = defaultdict(list)
for sym, dt, o, h, l, c, v in rows:
    if c and c > 0:
        by_date[dt].append({"symbol": sym, "close": c, "open": o or c, "high": h or c, "low": l or c})

print(f"Trading days: {len(by_date)}")

# Build ASI
ASI_BASE = 100_000.0
first_close = {}
asi_rows = []

for dt in sorted(by_date.keys()):
    day = by_date[dt]
    normalised = []
    for r in day:
        sym = r["symbol"]
        if sym not in first_close:
            first_close[sym] = r["close"]
        if first_close[sym] > 0:
            normalised.append(r["close"] / first_close[sym])
    if not normalised:
        continue
    avg_norm = sum(normalised) / len(normalised)
    asi_close = round(ASI_BASE * avg_norm, 2)
    spread = asi_close * 0.003
    asi_rows.append((
        "ASI", dt,
        round(asi_close + random.uniform(-spread, spread), 2),
        round(asi_close + abs(random.gauss(0, spread)), 2),
        round(asi_close - abs(random.gauss(0, spread)), 2),
        asi_close,
        random.randint(800_000_000, 1_500_000_000),
        "synthetic_asi",
    ))

# Delete old ASI data and insert new
conn.execute("DELETE FROM ohlcv WHERE symbol = 'ASI'")
conn.executemany(
    "INSERT OR REPLACE INTO ohlcv (symbol, date, open, high, low, close, volume, source) VALUES (?,?,?,?,?,?,?,?)",
    asi_rows,
)
conn.commit()
print(f"ASI rows inserted: {len(asi_rows)}")

# Verify
count = conn.execute("SELECT COUNT(*) FROM ohlcv WHERE symbol = 'ASI'").fetchone()[0]
print(f"ASI sessions in DB: {count}")
conn.close()
