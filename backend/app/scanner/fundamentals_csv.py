"""
CSV Fundamentals Import Provider for NGX Quality Scanner.

Expected CSV header:
  symbol,period_end_date,period_type,revenue,operating_profit,net_income,
  total_assets,total_equity,total_debt,cash,operating_cash_flow,capex,
  dividends_paid,shares_outstanding,source,currency

Rules:
  - symbol and period_end_date are required
  - period_type defaults to ANNUAL if missing
  - currency defaults to NGN if missing
  - source defaults to "manual_csv" if missing
  - Numeric fields are nullable — missing/blank = None
  - Negative values are allowed (losses, negative cash flow)
  - Rows with invalid dates or missing symbol are rejected
"""

import csv
import hashlib
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"symbol", "period_end_date"}
NUMERIC_FIELDS = {
    "revenue", "operating_profit", "net_income",
    "total_assets", "total_equity", "total_debt", "cash",
    "operating_cash_flow", "capex", "dividends_paid", "shares_outstanding",
}
VALID_PERIOD_TYPES = {"ANNUAL", "INTERIM"}


@dataclass
class FundamentalsParseError:
    row: int
    field: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"row": self.row, "field": self.field, "message": self.message}


@dataclass
class FundamentalsParseResult:
    records: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[FundamentalsParseError] = field(default_factory=list)
    rows_total: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    csv_hash: str = ""


def _parse_date(val: str) -> Optional[date]:
    """Parse YYYY-MM-DD date string."""
    val = val.strip()
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def _parse_float(val: str) -> Optional[float]:
    """Parse numeric value, return None for blank/invalid."""
    val = val.strip()
    if not val or val == "-" or val.lower() in ("n/a", "na", "null", "none"):
        return None
    # Remove commas (common in financial CSVs)
    val = val.replace(",", "")
    try:
        return float(val)
    except ValueError:
        return None


def parse_fundamentals_csv(
    csv_content: str,
    default_source: str = "manual_csv",
) -> FundamentalsParseResult:
    """
    Parse a fundamentals CSV string into validated records.

    Returns FundamentalsParseResult with accepted records and any errors.
    """
    result = FundamentalsParseResult()
    result.csv_hash = hashlib.sha256(csv_content.encode()).hexdigest()[:16]

    reader = csv.DictReader(io.StringIO(csv_content))

    if not reader.fieldnames:
        result.errors.append(FundamentalsParseError(0, "header", "Empty or invalid CSV"))
        return result

    # Normalize header names to lowercase
    header_map = {f.strip().lower(): f.strip() for f in reader.fieldnames}
    missing_required = REQUIRED_FIELDS - set(header_map.keys())
    if missing_required:
        result.errors.append(FundamentalsParseError(
            0, "header", f"Missing required columns: {missing_required}"
        ))
        return result

    for row_num, raw_row in enumerate(reader, start=2):  # row 1 is header
        result.rows_total += 1
        row_errors = []

        # Normalize keys
        row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items()}

        # Required: symbol
        symbol = row.get("symbol", "").strip().upper()
        if not symbol:
            row_errors.append(FundamentalsParseError(row_num, "symbol", "Missing symbol"))

        # Required: period_end_date
        period_end_date = _parse_date(row.get("period_end_date", ""))
        if period_end_date is None:
            row_errors.append(FundamentalsParseError(
                row_num, "period_end_date",
                f"Invalid or missing date: {row.get('period_end_date', '')!r}"
            ))

        # Optional: period_type (default ANNUAL)
        period_type = row.get("period_type", "ANNUAL").strip().upper()
        if period_type not in VALID_PERIOD_TYPES:
            row_errors.append(FundamentalsParseError(
                row_num, "period_type",
                f"Invalid period_type: {period_type!r}. Must be ANNUAL or INTERIM."
            ))
            period_type = "ANNUAL"

        # Optional: currency (default NGN)
        currency = row.get("currency", "NGN").strip().upper() or "NGN"

        # Optional: source
        source = row.get("source", default_source).strip() or default_source

        if row_errors:
            result.errors.extend(row_errors)
            result.rows_rejected += 1
            continue

        # Parse all numeric fields
        record: Dict[str, Any] = {
            "symbol": symbol,
            "period_end_date": period_end_date,
            "period_type": period_type,
            "currency": currency,
            "source": source,
        }

        for fld in NUMERIC_FIELDS:
            raw_val = row.get(fld, "")
            parsed = _parse_float(raw_val)
            record[fld] = parsed

        # Sanity warnings (not errors — these are common in NGX data)
        if record["total_equity"] is not None and record["total_equity"] < 0:
            logger.warning("Row %d (%s): negative total_equity = %.2f",
                           row_num, symbol, record["total_equity"])

        result.records.append(record)
        result.rows_accepted += 1

    return result
