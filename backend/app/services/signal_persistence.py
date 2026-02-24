"""
SQLite-backed Signal Persistence for Paper Trading.

Extends the in-memory SignalHistoryStore with durable SQLite storage so that
tracked signals survive server restarts. This enables genuine forward
performance tracking (paper trading).

The store writes every signal to SQLite on store/update and loads all
signals into memory on startup for fast reads.
"""
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.services.signal_history import (
    SignalHistoryStore,
    TrackedSignal,
    SignalStatus,
    generate_signal_id,
)

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "signal_history.db"


class PersistentSignalStore(SignalHistoryStore):
    """
    SQLite-backed signal history store.

    On init: creates table if needed, loads existing signals into memory.
    On store/update: writes to SQLite, then updates in-memory indices.
    Read operations use the fast in-memory store (inherited).
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        super().__init__()
        self._db_path = db_path
        self._db_lock = threading.Lock()
        self._init_db()
        self._load_from_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._db_lock:
            conn = self._get_conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tracked_signals (
                    signal_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    bias_direction TEXT NOT NULL,
                    bias_probability INTEGER NOT NULL,
                    regime TEXT NOT NULL,
                    regime_confidence REAL NOT NULL,
                    data_confidence_score REAL NOT NULL,
                    generated_at TEXT NOT NULL,
                    price_at_signal REAL NOT NULL,
                    horizon TEXT NOT NULL,
                    expires_at TEXT,
                    -- Forward performance
                    price_1d REAL,
                    price_5d REAL,
                    price_20d REAL,
                    return_1d REAL,
                    return_5d REAL,
                    return_20d REAL,
                    hit_1d INTEGER,
                    hit_5d INTEGER,
                    hit_20d INTEGER,
                    -- Status
                    status TEXT NOT NULL DEFAULT 'pending',
                    evaluated_at TEXT,
                    -- Context
                    pre_regime_probability INTEGER,
                    regime_adjustment_factor REAL,
                    indicator_agreement REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_symbol
                ON tracked_signals(symbol)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_status
                ON tracked_signals(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_generated
                ON tracked_signals(generated_at DESC)
            """)
            conn.commit()
            conn.close()
            logger.info("Signal persistence DB initialized at %s", self._db_path)

    def _load_from_db(self):
        """Load all signals from SQLite into the in-memory store."""
        with self._db_lock:
            conn = self._get_conn()
            cursor = conn.execute("SELECT * FROM tracked_signals ORDER BY generated_at")
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            conn.close()

        loaded = 0
        for row in rows:
            d = dict(zip(columns, row))
            signal = TrackedSignal(
                signal_id=d["signal_id"],
                symbol=d["symbol"],
                bias_direction=d["bias_direction"],
                bias_probability=d["bias_probability"],
                regime=d["regime"],
                regime_confidence=d["regime_confidence"],
                data_confidence_score=d["data_confidence_score"],
                generated_at=datetime.fromisoformat(d["generated_at"]),
                price_at_signal=d["price_at_signal"],
                horizon=d["horizon"],
                expires_at=datetime.fromisoformat(d["expires_at"]) if d["expires_at"] else None,
                price_1d=d["price_1d"],
                price_5d=d["price_5d"],
                price_20d=d["price_20d"],
                return_1d=d["return_1d"],
                return_5d=d["return_5d"],
                return_20d=d["return_20d"],
                hit_1d=bool(d["hit_1d"]) if d["hit_1d"] is not None else None,
                hit_5d=bool(d["hit_5d"]) if d["hit_5d"] is not None else None,
                hit_20d=bool(d["hit_20d"]) if d["hit_20d"] is not None else None,
                status=SignalStatus(d["status"]),
                evaluated_at=datetime.fromisoformat(d["evaluated_at"]) if d["evaluated_at"] else None,
                pre_regime_probability=d["pre_regime_probability"],
                regime_adjustment_factor=d["regime_adjustment_factor"],
                indicator_agreement=d["indicator_agreement"],
            )
            # Insert directly into in-memory store (bypass DB write)
            with self._lock:
                self._signals[signal.signal_id] = signal
                self._by_symbol.setdefault(signal.symbol, []).append(signal.signal_id)
                self._by_regime.setdefault(signal.regime, []).append(signal.signal_id)
                self._by_direction.setdefault(signal.bias_direction, []).append(signal.signal_id)
            loaded += 1

        if loaded:
            logger.info("Loaded %d persisted signals from %s", loaded, self._db_path)

    def _persist_signal(self, signal: TrackedSignal):
        """Write or update a signal in SQLite."""
        with self._db_lock:
            conn = self._get_conn()
            conn.execute("""
                INSERT OR REPLACE INTO tracked_signals (
                    signal_id, symbol, bias_direction, bias_probability,
                    regime, regime_confidence, data_confidence_score,
                    generated_at, price_at_signal, horizon, expires_at,
                    price_1d, price_5d, price_20d,
                    return_1d, return_5d, return_20d,
                    hit_1d, hit_5d, hit_20d,
                    status, evaluated_at,
                    pre_regime_probability, regime_adjustment_factor, indicator_agreement
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.signal_id,
                signal.symbol,
                signal.bias_direction,
                signal.bias_probability,
                signal.regime,
                signal.regime_confidence,
                signal.data_confidence_score,
                signal.generated_at.isoformat(),
                signal.price_at_signal,
                signal.horizon,
                signal.expires_at.isoformat() if signal.expires_at else None,
                signal.price_1d,
                signal.price_5d,
                signal.price_20d,
                signal.return_1d,
                signal.return_5d,
                signal.return_20d,
                int(signal.hit_1d) if signal.hit_1d is not None else None,
                int(signal.hit_5d) if signal.hit_5d is not None else None,
                int(signal.hit_20d) if signal.hit_20d is not None else None,
                signal.status.value,
                signal.evaluated_at.isoformat() if signal.evaluated_at else None,
                signal.pre_regime_probability,
                signal.regime_adjustment_factor,
                signal.indicator_agreement,
            ))
            conn.commit()
            conn.close()

    def store_signal(self, **kwargs) -> TrackedSignal:
        """Store a new signal — persists to both memory and SQLite."""
        signal = super().store_signal(**kwargs)
        self._persist_signal(signal)
        return signal

    def update_signal(self, signal: TrackedSignal):
        """Update a signal — persists to both memory and SQLite."""
        super().update_signal(signal)
        self._persist_signal(signal)

    def clear(self):
        """Clear all signals from memory and SQLite."""
        super().clear()
        with self._db_lock:
            conn = self._get_conn()
            conn.execute("DELETE FROM tracked_signals")
            conn.commit()
            conn.close()

    def signal_count_persistent(self) -> int:
        """Count signals in the SQLite DB (for verification)."""
        with self._db_lock:
            conn = self._get_conn()
            cursor = conn.execute("SELECT COUNT(*) FROM tracked_signals")
            count = cursor.fetchone()[0]
            conn.close()
            return count


# ── Singleton ─────────────────────────────────────────────────────────

_persistent_store: Optional[PersistentSignalStore] = None


def get_persistent_signal_store() -> PersistentSignalStore:
    """Get singleton persistent signal store."""
    global _persistent_store
    if _persistent_store is None:
        _persistent_store = PersistentSignalStore()
    return _persistent_store
