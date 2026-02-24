"""
EOD Data Reconciliation Service.

Compares OHLCV records from multiple sources and resolves conflicts.
NGX Official List PDF is the preferred (authoritative) source for
close prices when there is a discrepancy.

Rules:
  - No existing row  → INSERT new record
  - Same source      → SKIP (dedup)
  - Different source, close agrees (within threshold) → SKIP
  - Different source, close diverges:
      → UPDATE to preferred source (NGX Official)
      → Record AuditEvent with discrepancy details
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from app.data.historical.storage import (
    HistoricalOHLCVStorage,
    OHLCVRecord,
    get_historical_storage,
)

logger = logging.getLogger(__name__)

NGX_PDF_SOURCE = "NGX_OFFICIAL_LIST_PDF"
NGNMARKET_SOURCE = "NGNMARKET_HISTORICAL"

# Close price divergence threshold (percent)
CLOSE_DIVERGENCE_THRESHOLD_PCT = 2.0


@dataclass
class ReconciliationResult:
    """Result of reconciling a single (symbol, date) pair."""

    symbol: str
    trade_date: date
    action: str  # "inserted", "updated", "skipped", "conflict_logged"
    existing_source: Optional[str] = None
    existing_close: Optional[float] = None
    new_source: Optional[str] = None
    new_close: Optional[float] = None
    divergence_pct: Optional[float] = None


@dataclass
class ReconciliationReport:
    """Summary of a reconciliation run."""

    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    conflicts: int = 0
    results: List[ReconciliationResult] = field(default_factory=list)
    audit_events: List[Dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Reconciliation: inserted={self.inserted}, updated={self.updated}, "
            f"skipped={self.skipped}, conflicts={self.conflicts}"
        )


class ReconciliationService:
    """
    Reconciles OHLCV records between sources.

    Compares incoming records (typically from NGX PDF) against existing
    storage, resolves conflicts, and produces audit events for any
    discrepancies.
    """

    def __init__(
        self,
        storage: Optional[HistoricalOHLCVStorage] = None,
        divergence_threshold_pct: float = CLOSE_DIVERGENCE_THRESHOLD_PCT,
    ):
        self._storage = storage or get_historical_storage()
        self._threshold = divergence_threshold_pct

    def reconcile_records(
        self,
        new_records: List[OHLCVRecord],
        preferred_source: str = NGX_PDF_SOURCE,
    ) -> ReconciliationReport:
        """
        Reconcile a batch of new records against existing storage.

        Args:
            new_records: Records to reconcile (typically from NGX PDF)
            preferred_source: Source to prefer on conflict

        Returns:
            ReconciliationReport with details and audit events
        """
        report = ReconciliationReport()

        for record in new_records:
            result = self._reconcile_one(record, preferred_source)
            report.results.append(result)

            if result.action == "inserted":
                report.inserted += 1
            elif result.action == "updated":
                report.updated += 1
                report.audit_events.append(
                    self._make_audit_event(result, "RECONCILIATION_UPDATE")
                )
            elif result.action == "conflict_logged":
                report.conflicts += 1
                report.audit_events.append(
                    self._make_audit_event(result, "RECONCILIATION_CONFLICT")
                )
            else:
                report.skipped += 1

        logger.info(report.summary())
        return report

    def _reconcile_one(
        self, record: OHLCVRecord, preferred_source: str
    ) -> ReconciliationResult:
        """Reconcile a single record against existing storage."""
        existing = self._storage.get_ohlcv(
            record.symbol, start_date=record.date, end_date=record.date
        )

        if not existing:
            # No existing row → insert
            success, _ = self._storage.store_ohlcv(record)
            return ReconciliationResult(
                symbol=record.symbol,
                trade_date=record.date,
                action="inserted" if success else "skipped",
                new_source=record.source,
                new_close=record.close,
            )

        existing_rec = existing[0]

        # Same source → skip (dedup)
        if existing_rec.source == record.source:
            return ReconciliationResult(
                symbol=record.symbol,
                trade_date=record.date,
                action="skipped",
                existing_source=existing_rec.source,
                existing_close=existing_rec.close,
            )

        # Different source → compare close prices
        if existing_rec.close and existing_rec.close > 0:
            divergence = (
                abs(record.close - existing_rec.close) / existing_rec.close * 100
            )
        else:
            divergence = 100.0  # Treat 0/None as max divergence

        if divergence <= self._threshold:
            # Values agree → skip (keep existing)
            return ReconciliationResult(
                symbol=record.symbol,
                trade_date=record.date,
                action="skipped",
                existing_source=existing_rec.source,
                existing_close=existing_rec.close,
                new_source=record.source,
                new_close=record.close,
                divergence_pct=divergence,
            )

        # Divergence detected
        if record.source == preferred_source:
            # New record IS the preferred source → update existing
            self._storage.update_ohlcv(record)
            return ReconciliationResult(
                symbol=record.symbol,
                trade_date=record.date,
                action="updated",
                existing_source=existing_rec.source,
                existing_close=existing_rec.close,
                new_source=record.source,
                new_close=record.close,
                divergence_pct=divergence,
            )
        else:
            # New record is NOT preferred → just log conflict, keep existing
            return ReconciliationResult(
                symbol=record.symbol,
                trade_date=record.date,
                action="conflict_logged",
                existing_source=existing_rec.source,
                existing_close=existing_rec.close,
                new_source=record.source,
                new_close=record.close,
                divergence_pct=divergence,
            )

    @staticmethod
    def _make_audit_event(
        result: ReconciliationResult, event_type: str
    ) -> Dict[str, Any]:
        """Build an audit event dict for persistence via AuditService."""
        return {
            "component": "reconciliation",
            "event_type": event_type,
            "message": (
                f"{result.symbol} {result.trade_date}: "
                f"close {result.existing_source}={result.existing_close} vs "
                f"{result.new_source}={result.new_close} "
                f"(divergence={result.divergence_pct:.2f}%)"
            ),
            "level": "WARNING" if event_type == "RECONCILIATION_CONFLICT" else "INFO",
            "payload": {
                "symbol": result.symbol,
                "trade_date": result.trade_date.isoformat(),
                "existing_source": result.existing_source,
                "existing_close": result.existing_close,
                "new_source": result.new_source,
                "new_close": result.new_close,
                "divergence_pct": result.divergence_pct,
                "action": result.action,
            },
        }
