"""Purge synthetic OHLCV data and rebuild metadata."""
import sqlite3
from app.data.historical.storage import get_historical_storage

storage = get_historical_storage()
conn = sqlite3.connect(str(storage.db_path))

before = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
synthetic = conn.execute(
    "SELECT COUNT(*) FROM ohlcv WHERE source IN ('anchored_backfill', 'synthetic_asi')"
).fetchone()[0]
real = before - synthetic

print(f"Before purge: {before} total, {synthetic} synthetic, {real} real")

conn.execute("DELETE FROM ohlcv WHERE source IN ('anchored_backfill', 'synthetic_asi')")
conn.commit()

after = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
print(f"After purge: {after} rows remaining (all real)")

symbols_with_data = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM ohlcv")]
all_meta_syms = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM symbol_metadata")]
empty = [s for s in all_meta_syms if s not in symbols_with_data]
print(f"Symbols with real data: {len(symbols_with_data)}")
print(f"Symbols now empty: {len(empty)} -> {empty}")
conn.close()

# Rebuild metadata
for sym in set(symbols_with_data + all_meta_syms):
    storage._update_metadata(sym)
print("Metadata rebuilt")
