"""
Endpoints to trigger and track OHLCV market data scans.

POST /api/v1/scan/trigger   — fetch fresh prices, refresh metadata, log result
GET  /api/v1/scan/latest    — last scan summary (for "Last scanned: X ago")
GET  /api/v1/scan/history   — paginated scan history
"""

import asyncio
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scan", tags=["Scan"])

# Singleton lock to prevent concurrent scans
_scan_lock = asyncio.Lock()


def _get_db_path() -> Path:
    p = Path("/app/data/historical_ohlcv.db")
    if p.exists():
        return p
    return Path(__file__).resolve().parents[3] / "data" / "historical_ohlcv.db"


def _ensure_scan_history_table(conn: sqlite3.Connection):
    """Create scan_history table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            triggered_at    TEXT    NOT NULL,
            completed_at    TEXT,
            success         INTEGER NOT NULL DEFAULT 0,
            symbols_fetched INTEGER NOT NULL DEFAULT 0,
            symbols_total   INTEGER NOT NULL DEFAULT 0,
            latest_date     TEXT,
            duration_seconds REAL   NOT NULL DEFAULT 0,
            warnings        TEXT,
            message         TEXT
        )
    """)
    conn.commit()


# ── Response models ───────────────────────────────────────────────────

class ScanTriggerResponse(BaseModel):
    success: bool
    message: str
    symbols_fetched: int = 0
    symbols_total: int = 0
    latest_date: str = ""
    duration_seconds: float = 0.0
    warnings: list[str] = []


class ScanHistoryEntry(BaseModel):
    id: int
    triggered_at: str
    completed_at: Optional[str] = None
    success: bool
    symbols_fetched: int
    symbols_total: int
    latest_date: Optional[str] = None
    duration_seconds: float
    warnings: list[str] = []
    message: Optional[str] = None


class ScanHistoryResponse(BaseModel):
    total: int
    scans: list[ScanHistoryEntry]


class ScanLatestResponse(BaseModel):
    has_scans: bool
    last_scan: Optional[ScanHistoryEntry] = None


# ── POST /trigger ─────────────────────────────────────────────────────

@router.post("/trigger", response_model=ScanTriggerResponse)
async def trigger_scan():
    """
    Trigger a fresh OHLCV data fetch and metadata refresh.
    Runs fetch_real_ohlcv.py as a subprocess, then refreshes symbol_metadata.
    Only one scan can run at a time. Result is logged to scan_history.
    """
    if _scan_lock.locked():
        raise HTTPException(status_code=409, detail="A scan is already running. Please wait.")

    async with _scan_lock:
        t0 = time.time()
        triggered_at = datetime.now(timezone.utc).isoformat()
        warnings: list[str] = []

        # Step 1: Run fetch_real_ohlcv.py
        try:
            script_path = Path("/app/fetch_real_ohlcv.py")
            if not script_path.exists():
                script_path = Path(__file__).resolve().parents[3] / "fetch_real_ohlcv.py"
            if not script_path.exists():
                raise FileNotFoundError("fetch_real_ohlcv.py not found")

            proc = await asyncio.create_subprocess_exec(
                "python", str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(script_path.parent),
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            output = stdout.decode(errors="replace") if stdout else ""

            if proc.returncode != 0:
                logger.error("fetch_real_ohlcv.py failed (rc=%d): %s", proc.returncode, output[-500:])
                warnings.append(f"Fetch script exited with code {proc.returncode}")

        except asyncio.TimeoutError:
            warnings.append("OHLCV fetch timed out after 300s")
            logger.error("fetch_real_ohlcv.py timed out")
        except Exception as e:
            warnings.append(f"Fetch error: {str(e)[:100]}")
            logger.error("fetch_real_ohlcv.py error: %s", e)

        # Step 2: Refresh metadata in historical_ohlcv.db
        db_path = _get_db_path()
        symbols_fetched = 0
        symbols_total = 0
        latest_date = ""

        try:
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()
            c.execute("SELECT DISTINCT symbol FROM ohlcv")
            symbols = [r[0] for r in c.fetchall()]
            symbols_total = len(symbols)

            for sym in symbols:
                c.execute(
                    "SELECT MIN(date), MAX(date), COUNT(*) FROM ohlcv WHERE symbol=?",
                    (sym,),
                )
                mn, mx, cnt = c.fetchone()
                if cnt and cnt > 0:
                    c.execute(
                        """INSERT OR REPLACE INTO symbol_metadata
                        (symbol, first_date, last_date, total_sessions,
                         last_ingested_at, source, ingestion_status,
                         last_error, records_rejected_count)
                        VALUES (?, ?, ?, ?, datetime('now'),
                                'NGNMARKET_HISTORICAL', 'OK', NULL, 0)""",
                        (sym, mn, mx, cnt),
                    )
                    symbols_fetched += 1

            conn.commit()
            c.execute("SELECT MAX(last_date) FROM symbol_metadata")
            row = c.fetchone()
            latest_date = row[0] if row and row[0] else ""
            conn.close()
        except Exception as e:
            warnings.append(f"Metadata refresh error: {str(e)[:100]}")
            logger.error("Metadata refresh error: %s", e)

        duration = round(time.time() - t0, 1)
        completed_at = datetime.now(timezone.utc).isoformat()
        success = len(warnings) == 0
        message = f"Scan complete: {symbols_fetched}/{symbols_total} symbols refreshed, latest date {latest_date}"

        # Step 3: Log to scan_history
        try:
            conn = sqlite3.connect(str(db_path))
            _ensure_scan_history_table(conn)
            conn.execute(
                """INSERT INTO scan_history
                   (triggered_at, completed_at, success, symbols_fetched,
                    symbols_total, latest_date, duration_seconds, warnings, message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    triggered_at, completed_at, 1 if success else 0,
                    symbols_fetched, symbols_total, latest_date,
                    duration, "|".join(warnings) if warnings else None, message,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to log scan history: %s", e)

        return ScanTriggerResponse(
            success=success,
            message=message,
            symbols_fetched=symbols_fetched,
            symbols_total=symbols_total,
            latest_date=latest_date,
            duration_seconds=duration,
            warnings=warnings,
        )


# ── GET /latest ───────────────────────────────────────────────────────

@router.get("/latest", response_model=ScanLatestResponse)
async def get_latest_scan():
    """Return the most recent scan result (for 'Last scanned: X ago' display)."""
    db_path = _get_db_path()
    try:
        conn = sqlite3.connect(str(db_path))
        _ensure_scan_history_table(conn)
        row = conn.execute(
            "SELECT id, triggered_at, completed_at, success, symbols_fetched, "
            "symbols_total, latest_date, duration_seconds, warnings, message "
            "FROM scan_history ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()

        if not row:
            return ScanLatestResponse(has_scans=False)

        return ScanLatestResponse(
            has_scans=True,
            last_scan=_row_to_entry(row),
        )
    except Exception as e:
        logger.error("Failed to read scan history: %s", e)
        return ScanLatestResponse(has_scans=False)


# ── GET /history ──────────────────────────────────────────────────────

@router.get("/history", response_model=ScanHistoryResponse)
async def get_scan_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Return paginated scan history, newest first."""
    db_path = _get_db_path()
    try:
        conn = sqlite3.connect(str(db_path))
        _ensure_scan_history_table(conn)

        total = conn.execute("SELECT COUNT(*) FROM scan_history").fetchone()[0]
        rows = conn.execute(
            "SELECT id, triggered_at, completed_at, success, symbols_fetched, "
            "symbols_total, latest_date, duration_seconds, warnings, message "
            "FROM scan_history ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        conn.close()

        return ScanHistoryResponse(
            total=total,
            scans=[_row_to_entry(r) for r in rows],
        )
    except Exception as e:
        logger.error("Failed to read scan history: %s", e)
        return ScanHistoryResponse(total=0, scans=[])


def _row_to_entry(row) -> ScanHistoryEntry:
    warnings_raw = row[8]
    warnings = warnings_raw.split("|") if warnings_raw else []
    return ScanHistoryEntry(
        id=row[0],
        triggered_at=row[1],
        completed_at=row[2],
        success=bool(row[3]),
        symbols_fetched=row[4],
        symbols_total=row[5],
        latest_date=row[6],
        duration_seconds=row[7],
        warnings=warnings,
        message=row[9],
    )
