"""
Local SQLite cache for scraped fundamentals data.

Prevents redundant Playwright browser launches by caching raw scraped data
keyed by (source, symbol, period_end_date). The runner checks freshness
before invoking a scraper.

Storage location: data/scraped_fundamentals.db
"""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "scraped_fundamentals.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS scraped_fundamentals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    symbol      TEXT    NOT NULL,
    period_end  TEXT    NOT NULL,
    data_json   TEXT    NOT NULL,
    scraped_at  TEXT    NOT NULL,
    UNIQUE(source, symbol, period_end)
);

CREATE INDEX IF NOT EXISTS ix_sf_source_symbol
    ON scraped_fundamentals(source, symbol);

CREATE INDEX IF NOT EXISTS ix_sf_scraped_at
    ON scraped_fundamentals(scraped_at);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    started_at  TEXT    NOT NULL,
    finished_at TEXT,
    total       INTEGER DEFAULT 0,
    succeeded   INTEGER DEFAULT 0,
    failed      INTEGER DEFAULT 0,
    cached      INTEGER DEFAULT 0,
    periods     INTEGER DEFAULT 0,
    elapsed_s   REAL    DEFAULT 0
);
"""


class FundamentalsStore:
    """
    Thread-safe SQLite cache for scraped fundamentals.

    Usage::

        store = FundamentalsStore()

        if not store.is_fresh("stockanalysis", "GTCO", max_age_days=7):
            # scrape ...
            store.put("stockanalysis", "GTCO", date(2024, 12, 31), data_dict)

        cached = store.get_cached("stockanalysis", "GTCO")
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()
        logger.info("FundamentalsStore initialized at %s", self._db_path)

    @contextmanager
    def _conn(self):
        """Thread-safe connection context manager."""
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._lock, self._conn() as conn:
            conn.executescript(_CREATE_SQL)

    # ── Freshness ────────────────────────────────────────────────────

    def is_fresh(
        self, source: str, symbol: str, max_age_days: int = 7
    ) -> bool:
        """
        Check if we have sufficiently fresh data for this source/symbol.

        Returns True if any record for (source, symbol) was scraped
        within max_age_days.
        """
        with self._lock, self._conn() as conn:
            row = conn.execute(
                """
                SELECT MAX(scraped_at) as latest
                FROM scraped_fundamentals
                WHERE source = ? AND symbol = ?
                """,
                (source, symbol.upper()),
            ).fetchone()

            if not row or not row["latest"]:
                return False

            latest = datetime.fromisoformat(row["latest"])
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - latest).days
            return age < max_age_days

    # ── Read ─────────────────────────────────────────────────────────

    def get_cached(
        self, source: str, symbol: str
    ) -> List[Dict[str, Any]]:
        """
        Get all cached periods for a source/symbol.

        Returns list of data dicts, ordered by period_end descending.
        """
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                """
                SELECT data_json, scraped_at
                FROM scraped_fundamentals
                WHERE source = ? AND symbol = ?
                ORDER BY period_end DESC
                """,
                (source, symbol.upper()),
            ).fetchall()

        return [
            {**json.loads(r["data_json"]), "_scraped_at": r["scraped_at"]}
            for r in rows
        ]

    def get_all_symbols(self, source: str) -> List[str]:
        """Get all symbols that have cached data for a source."""
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM scraped_fundamentals WHERE source = ?",
                (source,),
            ).fetchall()
        return [r["symbol"] for r in rows]

    def count(self, source: Optional[str] = None) -> int:
        """Count total cached records, optionally filtered by source."""
        with self._lock, self._conn() as conn:
            if source:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM scraped_fundamentals WHERE source = ?",
                    (source,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM scraped_fundamentals"
                ).fetchone()
        return row["cnt"] if row else 0

    # ── Write ────────────────────────────────────────────────────────

    def put(
        self,
        source: str,
        symbol: str,
        period_end_date: date,
        data: Dict[str, Any],
    ) -> None:
        """
        Insert or update a cached fundamentals record.

        Uses INSERT OR REPLACE on the (source, symbol, period_end) unique key.
        """
        symbol = symbol.upper()
        period_str = period_end_date.isoformat() if isinstance(period_end_date, date) else str(period_end_date)
        now = datetime.now(timezone.utc).isoformat()

        # Serialize: convert date objects in data to strings
        clean = {}
        for k, v in data.items():
            if isinstance(v, (date, datetime)):
                clean[k] = v.isoformat()
            else:
                clean[k] = v

        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scraped_fundamentals
                    (source, symbol, period_end, data_json, scraped_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source, symbol, period_str, json.dumps(clean), now),
            )

    def put_batch(
        self, source: str, records: List[Dict[str, Any]]
    ) -> int:
        """Batch insert/update. Returns count of records written."""
        count = 0
        for rec in records:
            symbol = rec.get("symbol", "")
            period_end = rec.get("period_end_date")
            if symbol and period_end:
                self.put(source, symbol, period_end, rec)
                count += 1
        return count

    # ── Run tracking ─────────────────────────────────────────────────

    def record_run(
        self,
        source: str,
        started_at: datetime,
        finished_at: datetime,
        total: int = 0,
        succeeded: int = 0,
        failed: int = 0,
        cached: int = 0,
        periods: int = 0,
        elapsed_s: float = 0.0,
    ) -> None:
        """Record a scrape run for audit trail."""
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO scrape_runs
                    (source, started_at, finished_at, total, succeeded, failed, cached, periods, elapsed_s)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    started_at.isoformat(),
                    finished_at.isoformat(),
                    total, succeeded, failed, cached, periods, elapsed_s,
                ),
            )

    def get_last_run(self, source: str) -> Optional[Dict[str, Any]]:
        """Get the most recent run record for a source."""
        with self._lock, self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM scrape_runs
                WHERE source = ?
                ORDER BY id DESC LIMIT 1
                """,
                (source,),
            ).fetchone()
        return dict(row) if row else None

    # ── Maintenance ──────────────────────────────────────────────────

    def purge_old(self, max_age_days: int = 90) -> int:
        """Delete records older than max_age_days. Returns count deleted."""
        cutoff = datetime.now(timezone.utc)
        from datetime import timedelta
        cutoff = (cutoff - timedelta(days=max_age_days)).isoformat()

        with self._lock, self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM scraped_fundamentals WHERE scraped_at < ?",
                (cutoff,),
            )
        deleted = cursor.rowcount
        if deleted:
            logger.info("Purged %d old records (>%d days)", deleted, max_age_days)
        return deleted
