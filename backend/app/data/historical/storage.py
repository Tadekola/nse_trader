"""
Historical OHLCV Storage Layer for NSE Trader (Phase 3).

Provides SQLite-based persistent storage for daily OHLCV data.
This enables legitimate technical indicator computation with real data.

Phase 3 Hardening:
- OHLCV validation with strict rules
- Deterministic de-duplication (ignore new duplicates)
- Ingestion status tracking (OK|STALE|FAILED|PARTIAL)
- Staleness detection (configurable trading days threshold)

Storage format:
- SQLite database for simplicity and portability
- One table for OHLCV records
- One table for symbol metadata (last ingested, total sessions, status)
"""
import logging
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from contextlib import contextmanager
from enum import Enum
import threading

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "historical_ohlcv.db"

# Staleness threshold: data older than N trading days is considered stale
DEFAULT_STALENESS_THRESHOLD_DAYS = 5


class IngestionStatus(str, Enum):
    """Status of historical data ingestion for a symbol."""
    OK = "OK"              # Data is current and valid
    STALE = "STALE"        # Data exists but is outdated
    FAILED = "FAILED"      # Last ingestion failed completely
    PARTIAL = "PARTIAL"    # Some records were rejected during ingestion
    NEVER = "NEVER"        # Never ingested


@dataclass
class ValidationError:
    """Details of a validation failure for an OHLCV record."""
    symbol: str
    date: date
    field: str
    reason: str
    value: Any
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "date": self.date.isoformat(),
            "field": self.field,
            "reason": self.reason,
            "value": self.value,
        }


def validate_ohlcv_record(record: "OHLCVRecord") -> Optional[ValidationError]:
    """
    Validate an OHLCV record with strict rules.
    
    Rules:
    1. open > 0
    2. high > 0
    3. low > 0
    4. close > 0
    5. volume >= 0
    6. high >= max(open, close, low)
    7. low <= min(open, close, high)
    
    Returns:
        None if valid, ValidationError if invalid
    """
    # Rule 1: open > 0
    if record.open <= 0:
        return ValidationError(
            symbol=record.symbol,
            date=record.date,
            field="open",
            reason="Open price must be positive",
            value=record.open
        )
    
    # Rule 2: high > 0
    if record.high <= 0:
        return ValidationError(
            symbol=record.symbol,
            date=record.date,
            field="high",
            reason="High price must be positive",
            value=record.high
        )
    
    # Rule 3: low > 0
    if record.low <= 0:
        return ValidationError(
            symbol=record.symbol,
            date=record.date,
            field="low",
            reason="Low price must be positive",
            value=record.low
        )
    
    # Rule 4: close > 0
    if record.close <= 0:
        return ValidationError(
            symbol=record.symbol,
            date=record.date,
            field="close",
            reason="Close price must be positive",
            value=record.close
        )
    
    # Rule 5: volume >= 0
    if record.volume < 0:
        return ValidationError(
            symbol=record.symbol,
            date=record.date,
            field="volume",
            reason="Volume must be non-negative",
            value=record.volume
        )
    
    # Rule 6: high >= max(open, close, low)
    max_price = max(record.open, record.close, record.low)
    if record.high < max_price:
        return ValidationError(
            symbol=record.symbol,
            date=record.date,
            field="high",
            reason=f"High ({record.high}) must be >= max(open, close, low) = {max_price}",
            value=record.high
        )
    
    # Rule 7: low <= min(open, close, high)
    min_price = min(record.open, record.close, record.high)
    if record.low > min_price:
        return ValidationError(
            symbol=record.symbol,
            date=record.date,
            field="low",
            reason=f"Low ({record.low}) must be <= min(open, close, high) = {min_price}",
            value=record.low
        )
    
    return None  # Valid


@dataclass
class OHLCVRecord:
    """Single OHLCV record for a trading session."""
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str = "NGNMARKET_HISTORICAL"
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "date": self.date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def from_row(cls, row: tuple) -> "OHLCVRecord":
        """Create from database row."""
        return cls(
            symbol=row[0],
            date=date.fromisoformat(row[1]) if isinstance(row[1], str) else row[1],
            open=row[2],
            high=row[3],
            low=row[4],
            close=row[5],
            volume=row[6],
            source=row[7],
            created_at=datetime.fromisoformat(row[8]) if row[8] else None,
        )


@dataclass
class SymbolMetadata:
    """Metadata for a symbol's historical data."""
    symbol: str
    first_date: Optional[date] = None
    last_date: Optional[date] = None
    total_sessions: int = 0
    last_ingested_at: Optional[datetime] = None
    source: str = "NGNMARKET_HISTORICAL"
    # Phase 3 hardening fields
    ingestion_status: IngestionStatus = IngestionStatus.NEVER
    last_error: Optional[str] = None
    records_rejected_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "first_date": self.first_date.isoformat() if self.first_date else None,
            "last_date": self.last_date.isoformat() if self.last_date else None,
            "total_sessions": self.total_sessions,
            "last_ingested_at": self.last_ingested_at.isoformat() if self.last_ingested_at else None,
            "source": self.source,
            "ingestion_status": self.ingestion_status.value,
            "last_error": self.last_error,
            "records_rejected_count": self.records_rejected_count,
        }
    
    def is_stale(self, threshold_days: int = DEFAULT_STALENESS_THRESHOLD_DAYS) -> bool:
        """Check if data is stale (last_date older than threshold)."""
        if not self.last_date:
            return True
        days_old = (date.today() - self.last_date).days
        return days_old > threshold_days
    
    def get_stale_reason(self, threshold_days: int = DEFAULT_STALENESS_THRESHOLD_DAYS) -> Optional[str]:
        """Get reason for staleness, if stale."""
        if not self.last_date:
            return "No historical data available"
        days_old = (date.today() - self.last_date).days
        if days_old > threshold_days:
            return f"Last data is {days_old} days old (threshold: {threshold_days} days)"
        return None


class HistoricalOHLCVStorage:
    """
    SQLite-based storage for historical OHLCV data.
    
    Thread-safe with connection pooling per thread.
    
    Schema:
    - ohlcv: symbol, date, open, high, low, close, volume, source, created_at
    - symbol_metadata: symbol, first_date, last_date, total_sessions, last_ingested_at, source
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize storage.
        
        Args:
            db_path: Path to SQLite database. Defaults to data/historical_ohlcv.db
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._initialized = False
        
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database schema
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    @contextmanager
    def _cursor(self):
        """Context manager for database cursor."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    
    def _init_db(self):
        """Initialize database schema."""
        with self._init_lock:
            if self._initialized:
                return
            
            with self._cursor() as cursor:
                # Create OHLCV table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ohlcv (
                        symbol TEXT NOT NULL,
                        date TEXT NOT NULL,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        volume INTEGER NOT NULL,
                        source TEXT NOT NULL DEFAULT 'NGNMARKET_HISTORICAL',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (symbol, date)
                    )
                """)
                
                # Create index for efficient queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_date 
                    ON ohlcv(symbol, date DESC)
                """)
                
                # Create symbol metadata table with Phase 3 hardening fields
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS symbol_metadata (
                        symbol TEXT PRIMARY KEY,
                        first_date TEXT,
                        last_date TEXT,
                        total_sessions INTEGER DEFAULT 0,
                        last_ingested_at TEXT,
                        source TEXT DEFAULT 'NGNMARKET_HISTORICAL',
                        ingestion_status TEXT DEFAULT 'NEVER',
                        last_error TEXT,
                        records_rejected_count INTEGER DEFAULT 0
                    )
                """)
                
                # Migration: Add new columns if they don't exist (for existing DBs)
                try:
                    cursor.execute("ALTER TABLE symbol_metadata ADD COLUMN ingestion_status TEXT DEFAULT 'NEVER'")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                try:
                    cursor.execute("ALTER TABLE symbol_metadata ADD COLUMN last_error TEXT")
                except sqlite3.OperationalError:
                    pass
                try:
                    cursor.execute("ALTER TABLE symbol_metadata ADD COLUMN records_rejected_count INTEGER DEFAULT 0")
                except sqlite3.OperationalError:
                    pass
            
            self._initialized = True
            logger.info(f"Historical OHLCV database initialized at {self.db_path}")
    
    def store_ohlcv(
        self, 
        record: OHLCVRecord, 
        validate: bool = True
    ) -> Tuple[bool, Optional[ValidationError]]:
        """
        Store a single OHLCV record with validation.
        
        De-duplication policy: IGNORE new duplicates (keep existing).
        
        Args:
            record: OHLCV record to store
            validate: Whether to validate the record (default True)
            
        Returns:
            Tuple of (success, validation_error)
            - (True, None) if stored successfully
            - (False, None) if duplicate (ignored)
            - (False, ValidationError) if validation failed
        """
        # Validate if requested
        if validate:
            error = validate_ohlcv_record(record)
            if error:
                logger.warning(f"Validation failed for {record.symbol} {record.date}: {error.reason}")
                return False, error
        
        try:
            with self._cursor() as cursor:
                cursor.execute("""
                    INSERT OR IGNORE INTO ohlcv 
                    (symbol, date, open, high, low, close, volume, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.symbol.upper(),
                    record.date.isoformat(),
                    record.open,
                    record.high,
                    record.low,
                    record.close,
                    record.volume,
                    record.source,
                ))
                
                if cursor.rowcount > 0:
                    self._update_metadata(record.symbol.upper())
                    return True, None
                return False, None  # Duplicate ignored
                
        except Exception as e:
            logger.error(f"Error storing OHLCV for {record.symbol}: {e}")
            return False, None
    
    def update_ohlcv(self, record: OHLCVRecord) -> bool:
        """
        Update an existing OHLCV record (used by reconciliation).
        
        Overwrites open/high/low/close/volume/source for a given (symbol, date).
        Returns True if a row was actually updated.
        """
        try:
            with self._cursor() as cursor:
                cursor.execute("""
                    UPDATE ohlcv
                    SET open = ?, high = ?, low = ?, close = ?, volume = ?, source = ?
                    WHERE symbol = ? AND date = ?
                """, (
                    record.open,
                    record.high,
                    record.low,
                    record.close,
                    record.volume,
                    record.source,
                    record.symbol.upper(),
                    record.date.isoformat(),
                ))
                updated = cursor.rowcount > 0
                if updated:
                    self._update_metadata(record.symbol.upper())
                return updated
        except Exception as e:
            logger.error("Error updating OHLCV for %s %s: %s", record.symbol, record.date, e)
            return False

    def store_ohlcv_batch(
        self, 
        records: List[OHLCVRecord],
        validate: bool = True,
        upsert: bool = False
    ) -> Tuple[int, List[ValidationError]]:
        """
        Store multiple OHLCV records in a batch with validation.
        
        De-duplication policy:
        - upsert=False (default): IGNORE new duplicates (keep existing)
        - upsert=True: REPLACE existing records (for updating with fresh data)
        
        Args:
            records: List of OHLCV records
            validate: Whether to validate records (default True)
            upsert: If True, use INSERT OR REPLACE to update existing records
            
        Returns:
            Tuple of (records_stored, validation_errors)
        """
        if not records:
            return 0, []
        
        stored = 0
        validation_errors: List[ValidationError] = []
        symbols_updated = set()
        symbols_rejected: Dict[str, int] = {}
        
        insert_sql = """
            INSERT OR REPLACE INTO ohlcv 
            (symbol, date, open, high, low, close, volume, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """ if upsert else """
            INSERT OR IGNORE INTO ohlcv 
            (symbol, date, open, high, low, close, volume, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        try:
            with self._cursor() as cursor:
                for record in records:
                    symbol = record.symbol.upper()
                    
                    # Validate if requested
                    if validate:
                        error = validate_ohlcv_record(record)
                        if error:
                            validation_errors.append(error)
                            symbols_rejected[symbol] = symbols_rejected.get(symbol, 0) + 1
                            continue
                    
                    cursor.execute(insert_sql, (
                        symbol,
                        record.date.isoformat(),
                        record.open,
                        record.high,
                        record.low,
                        record.close,
                        record.volume,
                        record.source,
                    ))
                    
                    if cursor.rowcount > 0:
                        stored += 1
                        symbols_updated.add(symbol)
            
            # Update metadata for affected symbols
            for symbol in symbols_updated:
                rejected_count = symbols_rejected.get(symbol, 0)
                status = IngestionStatus.PARTIAL if rejected_count > 0 else IngestionStatus.OK
                self._update_metadata(symbol, status=status, rejected_count=rejected_count)
            
            # Update metadata for symbols with only rejections (no records stored)
            for symbol in symbols_rejected:
                if symbol not in symbols_updated:
                    self._update_failed_metadata(
                        symbol, 
                        rejected_count=symbols_rejected[symbol],
                        error=f"All {symbols_rejected[symbol]} records failed validation"
                    )
            
            if validation_errors:
                logger.warning(f"Rejected {len(validation_errors)} records due to validation failures")
            logger.info(f"Stored {stored} OHLCV records for {len(symbols_updated)} symbols")
            
            return stored, validation_errors
            
        except Exception as e:
            logger.error(f"Error storing OHLCV batch: {e}")
            return stored, validation_errors
    
    def _update_metadata(
        self, 
        symbol: str,
        status: IngestionStatus = IngestionStatus.OK,
        rejected_count: int = 0,
        error: Optional[str] = None
    ):
        """Update metadata for a symbol after storing records."""
        try:
            with self._cursor() as cursor:
                # Get stats for symbol
                cursor.execute("""
                    SELECT 
                        MIN(date) as first_date,
                        MAX(date) as last_date,
                        COUNT(*) as total_sessions
                    FROM ohlcv
                    WHERE symbol = ?
                """, (symbol,))
                
                row = cursor.fetchone()
                if row and row['total_sessions'] > 0:
                    # Check staleness
                    last_date_str = row['last_date']
                    if last_date_str:
                        last_date_obj = date.fromisoformat(last_date_str)
                        days_old = (date.today() - last_date_obj).days
                        if days_old > DEFAULT_STALENESS_THRESHOLD_DAYS:
                            status = IngestionStatus.STALE
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO symbol_metadata
                        (symbol, first_date, last_date, total_sessions, last_ingested_at, source,
                         ingestion_status, last_error, records_rejected_count)
                        VALUES (?, ?, ?, ?, ?, 'NGNMARKET_HISTORICAL', ?, ?, ?)
                    """, (
                        symbol,
                        row['first_date'],
                        row['last_date'],
                        row['total_sessions'],
                        datetime.utcnow().isoformat(),
                        status.value,
                        error,
                        rejected_count,
                    ))
                    
        except Exception as e:
            logger.error("Error updating metadata for %s: %s", symbol, e)
    
    def _update_failed_metadata(
        self,
        symbol: str,
        rejected_count: int,
        error: str
    ):
        """Update metadata for a symbol where all records failed validation."""
        try:
            with self._cursor() as cursor:
                cursor.execute("""
                    INSERT OR REPLACE INTO symbol_metadata
                    (symbol, first_date, last_date, total_sessions, last_ingested_at, source,
                     ingestion_status, last_error, records_rejected_count)
                    VALUES (?, NULL, NULL, 0, ?, 'NGNMARKET_HISTORICAL', ?, ?, ?)
                """, (
                    symbol,
                    datetime.utcnow().isoformat(),
                    IngestionStatus.FAILED.value,
                    error,
                    rejected_count,
                ))
        except Exception as e:
            logger.error("Error updating failed metadata for %s: %s", symbol, e)
    
    def get_ohlcv(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None
    ) -> List[OHLCVRecord]:
        """
        Get OHLCV records for a symbol.
        
        Args:
            symbol: Stock symbol
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Optional limit on records returned
            
        Returns:
            List of OHLCV records ordered by date ascending
        """
        try:
            with self._cursor() as cursor:
                query = "SELECT symbol, date, open, high, low, close, volume, source, created_at FROM ohlcv WHERE symbol = ?"
                params: List[Any] = [symbol.upper()]
                
                if start_date:
                    query += " AND date >= ?"
                    params.append(start_date.isoformat())
                
                if end_date:
                    query += " AND date <= ?"
                    params.append(end_date.isoformat())
                
                query += " ORDER BY date ASC"
                
                if limit:
                    query += " LIMIT ?"
                    params.append(limit)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                return [OHLCVRecord.from_row(tuple(row)) for row in rows]
                
        except Exception as e:
            logger.error(f"Error getting OHLCV for {symbol}: {e}")
            return []
    
    def get_latest_ohlcv(self, symbol: str, sessions: int = 1) -> List[OHLCVRecord]:
        """
        Get the most recent OHLCV records for a symbol.
        
        Args:
            symbol: Stock symbol
            sessions: Number of sessions to retrieve
            
        Returns:
            List of OHLCV records ordered by date descending
        """
        try:
            with self._cursor() as cursor:
                cursor.execute("""
                    SELECT symbol, date, open, high, low, close, volume, source, created_at
                    FROM ohlcv
                    WHERE symbol = ?
                    ORDER BY date DESC
                    LIMIT ?
                """, (symbol.upper(), sessions))
                
                rows = cursor.fetchall()
                return [OHLCVRecord.from_row(tuple(row)) for row in rows]
                
        except Exception as e:
            logger.error(f"Error getting latest OHLCV for {symbol}: {e}")
            return []
    
    def get_metadata(self, symbol: str) -> Optional[SymbolMetadata]:
        """Get metadata for a symbol including ingestion status."""
        try:
            with self._cursor() as cursor:
                cursor.execute("""
                    SELECT symbol, first_date, last_date, total_sessions, last_ingested_at, source,
                           ingestion_status, last_error, records_rejected_count
                    FROM symbol_metadata
                    WHERE symbol = ?
                """, (symbol.upper(),))
                
                row = cursor.fetchone()
                if row:
                    status_str = row['ingestion_status'] if 'ingestion_status' in row.keys() else 'NEVER'
                    return SymbolMetadata(
                        symbol=row['symbol'],
                        first_date=date.fromisoformat(row['first_date']) if row['first_date'] else None,
                        last_date=date.fromisoformat(row['last_date']) if row['last_date'] else None,
                        total_sessions=row['total_sessions'],
                        last_ingested_at=datetime.fromisoformat(row['last_ingested_at']) if row['last_ingested_at'] else None,
                        source=row['source'],
                        ingestion_status=IngestionStatus(status_str) if status_str else IngestionStatus.NEVER,
                        last_error=row['last_error'] if 'last_error' in row.keys() else None,
                        records_rejected_count=row['records_rejected_count'] if 'records_rejected_count' in row.keys() else 0,
                    )
                return None
                
        except Exception as e:
            logger.error("Error getting metadata for %s: %s", symbol, e)
            return None
    
    def get_all_metadata(self) -> List[SymbolMetadata]:
        """Get metadata for all symbols with stored data."""
        try:
            with self._cursor() as cursor:
                cursor.execute("""
                    SELECT symbol, first_date, last_date, total_sessions, last_ingested_at, source,
                           ingestion_status, last_error, records_rejected_count
                    FROM symbol_metadata
                    ORDER BY symbol
                """)
                
                rows = cursor.fetchall()
                result = []
                for row in rows:
                    status_str = row['ingestion_status'] if 'ingestion_status' in row.keys() else 'NEVER'
                    result.append(SymbolMetadata(
                        symbol=row['symbol'],
                        first_date=date.fromisoformat(row['first_date']) if row['first_date'] else None,
                        last_date=date.fromisoformat(row['last_date']) if row['last_date'] else None,
                        total_sessions=row['total_sessions'],
                        last_ingested_at=datetime.fromisoformat(row['last_ingested_at']) if row['last_ingested_at'] else None,
                        source=row['source'],
                        ingestion_status=IngestionStatus(status_str) if status_str else IngestionStatus.NEVER,
                        last_error=row['last_error'] if 'last_error' in row.keys() else None,
                        records_rejected_count=row['records_rejected_count'] if 'records_rejected_count' in row.keys() else 0,
                    ))
                return result
                
        except Exception as e:
            logger.error("Error getting all metadata: %s", e)
            return []
    
    def get_sessions_available(self, symbol: str) -> int:
        """Get number of sessions available for a symbol."""
        metadata = self.get_metadata(symbol)
        return metadata.total_sessions if metadata else 0
    
    def get_symbols_with_sufficient_history(self, min_sessions: int) -> List[str]:
        """Get symbols with at least min_sessions of history."""
        try:
            with self._cursor() as cursor:
                cursor.execute("""
                    SELECT symbol
                    FROM symbol_metadata
                    WHERE total_sessions >= ?
                    ORDER BY symbol
                """, (min_sessions,))
                
                return [row['symbol'] for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Error getting symbols with sufficient history: {e}")
            return []
    
    def delete_symbol(self, symbol: str) -> bool:
        """Delete all data for a symbol."""
        try:
            with self._cursor() as cursor:
                cursor.execute("DELETE FROM ohlcv WHERE symbol = ?", (symbol.upper(),))
                cursor.execute("DELETE FROM symbol_metadata WHERE symbol = ?", (symbol.upper(),))
                return True
        except Exception as e:
            logger.error(f"Error deleting symbol {symbol}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get overall storage statistics."""
        try:
            with self._cursor() as cursor:
                cursor.execute("SELECT COUNT(DISTINCT symbol) as symbols FROM ohlcv")
                symbols = cursor.fetchone()['symbols']
                
                cursor.execute("SELECT COUNT(*) as records FROM ohlcv")
                records = cursor.fetchone()['records']
                
                cursor.execute("SELECT MIN(date) as min_date, MAX(date) as max_date FROM ohlcv")
                dates = cursor.fetchone()
                
                return {
                    "total_symbols": symbols,
                    "total_records": records,
                    "earliest_date": dates['min_date'],
                    "latest_date": dates['max_date'],
                    "db_path": str(self.db_path),
                }
                
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}
    
    def get_ohlcv_dataframe(
        self,
        symbol: str,
        min_sessions: int = 0,
    ) -> Optional["pd.DataFrame"]:
        """
        Get OHLCV records as a pandas DataFrame.

        Returns None if fewer than min_sessions are available.
        DataFrame columns: Open, High, Low, Close, Volume
        Index: DatetimeIndex (UTC-naive, ascending)
        """
        import pandas as pd

        records = self.get_ohlcv(symbol)
        if len(records) < min_sessions:
            return None

        rows = [
            {
                "Date": r.date,
                "Open": r.open,
                "High": r.high,
                "Low": r.low,
                "Close": r.close,
                "Volume": r.volume,
            }
            for r in records
        ]
        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        return df

    def close(self):
        """Close database connection."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None


# Singleton instance
_storage_instance: Optional[HistoricalOHLCVStorage] = None
_storage_lock = threading.Lock()


def get_historical_storage(db_path: Optional[Path] = None) -> HistoricalOHLCVStorage:
    """Get the singleton historical storage instance."""
    global _storage_instance
    with _storage_lock:
        if _storage_instance is None:
            _storage_instance = HistoricalOHLCVStorage(db_path)
        return _storage_instance
