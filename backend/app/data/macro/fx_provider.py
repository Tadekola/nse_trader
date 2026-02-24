"""
FX Rate CSV Import Provider + Service (Milestone B — PR1).

Parses FX rate CSV files and provides daily rate lookup with
weekday/holiday interpolation (forward-fill from last known rate).

CSV format (header required):
    date,pair,rate,source,confidence

Convention: pair = "USDNGN" means rate = NGN per 1 USD.
Dates: YYYY-MM-DD

Usage::

    provider = CsvFxRateProvider()
    result = provider.parse_csv_string(csv_text)
    # result.rates: list of validated dicts ready for DB

    service = FxRateService(rates)  # list of {ts, pair, rate}
    usd_rate = service.get_rate("USDNGN", date(2024, 6, 15))
    ngn_values = [100_000, 120_000]
    usd_values = service.convert_series("USDNGN", dates, ngn_values)
"""

import csv
import io
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FxParseError:
    row: int
    field: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"row": self.row, "field": self.field, "message": self.message}


@dataclass
class FxParseResult:
    rates: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[FxParseError] = field(default_factory=list)
    rows_total: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0


VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}


def _parse_date(val: str) -> Optional[date]:
    val = val.strip()
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except (ValueError, TypeError):
        return None


class CsvFxRateProvider:
    """Parse and validate FX rate CSV files."""

    def parse_file(self, path: str) -> FxParseResult:
        if not os.path.exists(path):
            raise FileNotFoundError(f"FX CSV file not found: {path}")
        with open(path, newline="", encoding="utf-8-sig") as f:
            return self.parse_rows(csv.DictReader(f))

    def parse_csv_string(self, csv_text: str) -> FxParseResult:
        reader = csv.DictReader(io.StringIO(csv_text))
        return self.parse_rows(reader)

    def parse_rows(self, reader: csv.DictReader) -> FxParseResult:
        result = FxParseResult()
        for row_num, row in enumerate(reader, start=2):
            result.rows_total += 1
            rate_dict, errors = self._validate_row(row_num, row)
            if errors:
                result.errors.extend(errors)
                result.rows_rejected += 1
            else:
                result.rates.append(rate_dict)
                result.rows_accepted += 1
        logger.info("FX CSV parse: %d total, %d accepted, %d rejected",
                     result.rows_total, result.rows_accepted, result.rows_rejected)
        return result

    def _validate_row(
        self, row_num: int, row: Dict[str, str]
    ) -> Tuple[Optional[Dict[str, Any]], List[FxParseError]]:
        errors: List[FxParseError] = []

        pair = row.get("pair", "").strip().upper()
        if not pair or len(pair) < 6:
            errors.append(FxParseError(row_num, "pair", "missing or invalid (e.g. USDNGN)"))

        ts = _parse_date(row.get("date", ""))
        if ts is None:
            errors.append(FxParseError(row_num, "date", "missing or invalid (YYYY-MM-DD)"))

        rate_str = row.get("rate", "").strip()
        rate = None
        if not rate_str:
            errors.append(FxParseError(row_num, "rate", "missing"))
        else:
            try:
                rate = float(rate_str)
                if rate <= 0:
                    errors.append(FxParseError(row_num, "rate", "must be positive"))
            except ValueError:
                errors.append(FxParseError(row_num, "rate", "not a valid number"))

        source = row.get("source", "CSV_IMPORT").strip() or "CSV_IMPORT"
        confidence = row.get("confidence", "HIGH").strip().upper()
        if confidence not in VALID_CONFIDENCE:
            confidence = "MEDIUM"

        if errors:
            return None, errors

        return {
            "pair": pair,
            "ts": ts,
            "rate": rate,
            "source": source,
            "confidence": confidence,
            "ingested_at": datetime.utcnow(),
            "provenance": {
                "source": source,
                "method": "csv_import",
                "ingested_at": datetime.utcnow().isoformat(),
            },
        }, []


class FxRateService:
    """
    In-memory FX rate lookup with forward-fill interpolation.

    Handles weekends/holidays by carrying forward the last known rate.
    Reports gaps explicitly via quality flags.
    """

    def __init__(self, rates: List[Dict[str, Any]]):
        # Index: pair -> sorted list of (date, rate)
        self._rates: Dict[str, List[Tuple[date, float]]] = {}
        for r in rates:
            pair = r["pair"] if isinstance(r.get("pair"), str) else r.get("pair", "")
            ts = r["ts"]
            rate = r["rate"]
            self._rates.setdefault(pair, []).append((ts, rate))

        # Sort each pair by date
        for pair in self._rates:
            self._rates[pair].sort(key=lambda x: x[0])

        # Build lookup dict for O(1) access after forward-fill
        self._lookup: Dict[str, Dict[date, float]] = {}
        for pair, entries in self._rates.items():
            self._lookup[pair] = {ts: rate for ts, rate in entries}

    def get_rate(self, pair: str, ts: date) -> Optional[float]:
        """
        Get FX rate for a pair on a given date.
        Uses forward-fill: if no rate on exact date, use most recent prior rate.
        Returns None if no rate available on or before the date.
        """
        lookup = self._lookup.get(pair)
        if not lookup:
            return None

        # Exact match
        if ts in lookup:
            return lookup[ts]

        # Forward-fill: find most recent rate before ts
        entries = self._rates.get(pair, [])
        best = None
        for entry_ts, entry_rate in entries:
            if entry_ts <= ts:
                best = entry_rate
            else:
                break
        return best

    def convert_series(
        self,
        pair: str,
        dates: List[date],
        ngn_values: List[float],
    ) -> Tuple[List[Optional[float]], str]:
        """
        Convert a series of NGN values to foreign currency.

        Returns:
            (converted_values, fx_mode)
            fx_mode: "FX_FULL" if all dates have rates, "FX_MISSING" if any gaps
        """
        converted: List[Optional[float]] = []
        missing_count = 0

        for ts, val in zip(dates, ngn_values):
            rate = self.get_rate(pair, ts)
            if rate is not None and rate > 0:
                converted.append(val / rate)
            else:
                converted.append(None)
                missing_count += 1

        fx_mode = "FX_FULL" if missing_count == 0 else "FX_MISSING"
        return converted, fx_mode

    def get_available_range(self, pair: str) -> Optional[Tuple[date, date]]:
        """Return (min_date, max_date) for a pair, or None if no data."""
        entries = self._rates.get(pair)
        if not entries:
            return None
        return entries[0][0], entries[-1][0]

    @property
    def pairs(self) -> List[str]:
        return list(self._rates.keys())
