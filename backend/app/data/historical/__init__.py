"""
Historical OHLCV Data Module for NSE Trader (Phase 3).

Provides persistent storage and retrieval of daily OHLCV data
to enable legitimate technical indicator computation.

Phase 3 Hardening:
- OHLCV validation with strict rules
- Deterministic de-duplication (ignore new duplicates)
- Ingestion status tracking (OK|STALE|FAILED|PARTIAL)
- Staleness detection (configurable trading days threshold)
"""
from .storage import (
    HistoricalOHLCVStorage,
    OHLCVRecord,
    SymbolMetadata,
    ValidationError,
    IngestionStatus,
    validate_ohlcv_record,
    get_historical_storage,
    DEFAULT_STALENESS_THRESHOLD_DAYS,
)
from .ingestion import (
    HistoricalIngestionService,
    IngestionResult,
    get_ingestion_service,
)

__all__ = [
    "HistoricalOHLCVStorage",
    "OHLCVRecord",
    "SymbolMetadata",
    "ValidationError",
    "IngestionStatus",
    "validate_ohlcv_record",
    "get_historical_storage",
    "DEFAULT_STALENESS_THRESHOLD_DAYS",
    "HistoricalIngestionService",
    "IngestionResult",
    "get_ingestion_service",
]
