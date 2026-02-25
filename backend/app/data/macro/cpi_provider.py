"""
CPI / Macro Series CSV Import Provider + Service (Milestone B — PR1).

Parses CPI (or other macro) CSV files and provides daily lookup with
monthly-to-daily forward-fill (carry last published value until next).

CSV format (header required):
    date,series_name,value,frequency,source,confidence

Convention:
  - series_name = "CPI_NGN" for Nigerian CPI index
  - date = first day of the month for monthly series (e.g. 2024-01-01)
  - value = the CPI index value (base year = 100)

Usage::

    provider = CsvCpiProvider()
    result = provider.parse_csv_string(csv_text)

    service = CpiService(result.entries)
    deflator = service.get_deflator(date(2024, 6, 15))
    real_values = service.deflate_series("CPI_NGN", dates, nominal_values, base_date)
"""

import csv
import io
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
VALID_FREQUENCY = {"DAILY", "MONTHLY", "QUARTERLY"}


@dataclass
class CpiParseError:
    row: int
    field: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"row": self.row, "field": self.field, "message": self.message}


@dataclass
class CpiParseResult:
    entries: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[CpiParseError] = field(default_factory=list)
    rows_total: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0


def _parse_date(val: str) -> Optional[date]:
    val = val.strip()
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except (ValueError, TypeError):
        return None


class CsvCpiProvider:
    """Parse and validate CPI / macro series CSV files."""

    def parse_file(self, path: str) -> CpiParseResult:
        if not os.path.exists(path):
            raise FileNotFoundError(f"CPI CSV file not found: {path}")
        with open(path, newline="", encoding="utf-8-sig") as f:
            return self.parse_rows(csv.DictReader(f))

    def parse_csv_string(self, csv_text: str) -> CpiParseResult:
        reader = csv.DictReader(io.StringIO(csv_text))
        return self.parse_rows(reader)

    def parse_rows(self, reader: csv.DictReader) -> CpiParseResult:
        result = CpiParseResult()
        for row_num, row in enumerate(reader, start=2):
            result.rows_total += 1
            entry, errors = self._validate_row(row_num, row)
            if errors:
                result.errors.extend(errors)
                result.rows_rejected += 1
            else:
                result.entries.append(entry)
                result.rows_accepted += 1
        logger.info("CPI CSV parse: %d total, %d accepted, %d rejected",
                     result.rows_total, result.rows_accepted, result.rows_rejected)
        return result

    def _validate_row(
        self, row_num: int, row: Dict[str, str]
    ) -> Tuple[Optional[Dict[str, Any]], List[CpiParseError]]:
        errors: List[CpiParseError] = []

        series_name = row.get("series_name", "").strip().upper()
        if not series_name:
            errors.append(CpiParseError(row_num, "series_name", "missing or empty"))

        ts = _parse_date(row.get("date", ""))
        if ts is None:
            errors.append(CpiParseError(row_num, "date", "missing or invalid (YYYY-MM-DD)"))

        value_str = row.get("value", "").strip()
        value = None
        if not value_str:
            errors.append(CpiParseError(row_num, "value", "missing"))
        else:
            try:
                value = float(value_str)
                if value <= 0:
                    errors.append(CpiParseError(row_num, "value", "must be positive"))
            except ValueError:
                errors.append(CpiParseError(row_num, "value", "not a valid number"))

        frequency = row.get("frequency", "MONTHLY").strip().upper()
        if frequency not in VALID_FREQUENCY:
            frequency = "MONTHLY"

        source = row.get("source", "CSV_IMPORT").strip() or "CSV_IMPORT"
        confidence = row.get("confidence", "HIGH").strip().upper()
        if confidence not in VALID_CONFIDENCE:
            confidence = "MEDIUM"

        if errors:
            return None, errors

        return {
            "series_name": series_name,
            "ts": ts,
            "value": value,
            "frequency": frequency,
            "source": source,
            "confidence": confidence,
            "ingested_at": datetime.now(timezone.utc),
            "provenance": {
                "source": source,
                "method": "csv_import",
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            },
        }, []


class CpiService:
    """
    In-memory CPI lookup with monthly-to-daily forward-fill.

    Monthly CPI values are carried forward from their publication date
    until the next publication. This is standard practice for inflation
    adjustment of daily financial data.
    """

    def __init__(self, entries: List[Dict[str, Any]], default_series: str = "CPI_NGN"):
        self._default_series = default_series
        # Index: series_name -> sorted list of (date, value)
        self._series: Dict[str, List[Tuple[date, float]]] = {}
        for e in entries:
            name = e["series_name"] if isinstance(e.get("series_name"), str) else ""
            ts = e["ts"]
            val = e["value"]
            self._series.setdefault(name, []).append((ts, val))

        for name in self._series:
            self._series[name].sort(key=lambda x: x[0])

    def get_value(self, ts: date, series_name: Optional[str] = None) -> Optional[float]:
        """
        Get CPI value for a date (forward-filled from monthly data).
        Returns None if no data available on or before the date.
        """
        name = series_name or self._default_series
        entries = self._series.get(name)
        if not entries:
            return None

        # Forward-fill: find most recent entry on or before ts
        best = None
        for entry_ts, entry_val in entries:
            if entry_ts <= ts:
                best = entry_val
            else:
                break
        return best

    def get_deflator(
        self, ts: date, base_date: Optional[date] = None,
        series_name: Optional[str] = None,
    ) -> Optional[float]:
        """
        Get the CPI deflator for a date relative to a base date.

        deflator = cpi[ts] / cpi[base_date]
        To get real value: real_value = nominal_value / deflator

        If base_date is None, uses the earliest available CPI as base.
        """
        name = series_name or self._default_series
        cpi_now = self.get_value(ts, name)
        if cpi_now is None:
            return None

        if base_date is not None:
            cpi_base = self.get_value(base_date, name)
        else:
            entries = self._series.get(name)
            if not entries:
                return None
            cpi_base = entries[0][1]

        if cpi_base is None or cpi_base == 0:
            return None

        return cpi_now / cpi_base

    def deflate_series(
        self,
        dates: List[date],
        nominal_values: List[float],
        base_date: Optional[date] = None,
        series_name: Optional[str] = None,
    ) -> Tuple[List[Optional[float]], str]:
        """
        Convert nominal NGN values to real NGN values using CPI deflation.

        Returns:
            (real_values, inflation_mode)
            inflation_mode: "CPI_FULL" if all dates have CPI, "CPI_MISSING" if gaps
        """
        real_values: List[Optional[float]] = []
        missing_count = 0

        for ts, val in zip(dates, nominal_values):
            deflator = self.get_deflator(ts, base_date, series_name)
            if deflator is not None and deflator > 0:
                real_values.append(val / deflator)
            else:
                real_values.append(None)
                missing_count += 1

        mode = "CPI_FULL" if missing_count == 0 else "CPI_MISSING"
        return real_values, mode

    def get_available_range(self, series_name: Optional[str] = None) -> Optional[Tuple[date, date]]:
        name = series_name or self._default_series
        entries = self._series.get(name)
        if not entries:
            return None
        return entries[0][0], entries[-1][0]

    @property
    def series_names(self) -> List[str]:
        return list(self._series.keys())
