"""
CSV Import Provider for Corporate Actions (Milestone A — PR1).

Parses a structured CSV file into validated CorporateAction records.
This is the primary MVP ingestion path — reliable, auditable, admin-controlled.

CSV format (header required):
    symbol,action_type,ex_date,record_date,payment_date,amount,ratio_from,ratio_to,currency,source,confidence,notes

action_type values: CASH_DIVIDEND, STOCK_SPLIT, BONUS_ISSUE, RIGHTS_ISSUE, SUSPENSION
Dates: YYYY-MM-DD (record_date, payment_date may be empty)
amount: required for CASH_DIVIDEND, ignored for splits/bonuses
ratio_from/ratio_to: required for STOCK_SPLIT and BONUS_ISSUE

Usage::

    provider = CsvCorporateActionProvider()
    actions, errors = provider.parse_file("path/to/actions.csv")
    # actions: list of validated dicts ready for DB insertion
    # errors: list of {row, field, message} for rejected rows
"""

import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

VALID_ACTION_TYPES = {
    "CASH_DIVIDEND",
    "STOCK_SPLIT",
    "BONUS_ISSUE",
    "RIGHTS_ISSUE",
    "SUSPENSION",
}

VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}

REQUIRED_COLUMNS = {
    "symbol", "action_type", "ex_date",
}


@dataclass
class ParseError:
    """A single validation error from CSV parsing."""
    row: int
    field: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"row": self.row, "field": self.field, "message": self.message}


@dataclass
class ParseResult:
    """Result of parsing a corporate actions CSV."""
    actions: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[ParseError] = field(default_factory=list)
    rows_total: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0


def _parse_date(val: str) -> Optional[date]:
    """Parse YYYY-MM-DD string to date, or None if empty/invalid."""
    val = val.strip()
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def _parse_float(val: str) -> Optional[float]:
    val = val.strip()
    if not val:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_int(val: str) -> Optional[int]:
    val = val.strip()
    if not val:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


class CsvCorporateActionProvider:
    """
    Parses and validates corporate action CSV files.

    Each valid row produces a dict matching the CorporateAction model columns.
    Invalid rows are collected as ParseError instances for audit/review.
    """

    def parse_file(self, path: str) -> ParseResult:
        """Parse a CSV file and return validated actions + errors."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"CSV file not found: {path}")

        with open(path, newline="", encoding="utf-8-sig") as f:
            return self.parse_rows(csv.DictReader(f))

    def parse_csv_string(self, csv_text: str) -> ParseResult:
        """Parse CSV from a string (useful for tests and API uploads)."""
        import io
        reader = csv.DictReader(io.StringIO(csv_text))
        return self.parse_rows(reader)

    def parse_rows(self, reader: csv.DictReader) -> ParseResult:
        """Validate rows from a csv.DictReader."""
        result = ParseResult()

        for row_num, row in enumerate(reader, start=2):  # row 1 = header
            result.rows_total += 1
            action, errors = self._validate_row(row_num, row)

            if errors:
                result.errors.extend(errors)
                result.rows_rejected += 1
            else:
                result.actions.append(action)
                result.rows_accepted += 1

        logger.info(
            "CSV parse complete: %d total, %d accepted, %d rejected",
            result.rows_total, result.rows_accepted, result.rows_rejected,
        )
        return result

    def _validate_row(
        self, row_num: int, row: Dict[str, str]
    ) -> Tuple[Optional[Dict[str, Any]], List[ParseError]]:
        """Validate a single CSV row. Returns (action_dict, errors)."""
        errors: List[ParseError] = []

        # ── Required fields ──
        symbol = row.get("symbol", "").strip().upper()
        if not symbol:
            errors.append(ParseError(row_num, "symbol", "missing or empty"))

        action_type = row.get("action_type", "").strip().upper()
        if action_type not in VALID_ACTION_TYPES:
            errors.append(ParseError(
                row_num, "action_type",
                f"invalid: '{action_type}' (expected one of {sorted(VALID_ACTION_TYPES)})"
            ))

        ex_date = _parse_date(row.get("ex_date", ""))
        if ex_date is None:
            errors.append(ParseError(row_num, "ex_date", "missing or invalid date (YYYY-MM-DD)"))

        # ── Optional date fields ──
        record_date = _parse_date(row.get("record_date", ""))
        payment_date = _parse_date(row.get("payment_date", ""))

        # ── Type-specific validation ──
        amount = _parse_float(row.get("amount", ""))
        ratio_from = _parse_int(row.get("ratio_from", ""))
        ratio_to = _parse_int(row.get("ratio_to", ""))

        if action_type == "CASH_DIVIDEND":
            if amount is None or amount <= 0:
                errors.append(ParseError(
                    row_num, "amount", "CASH_DIVIDEND requires positive amount"
                ))

        if action_type in ("STOCK_SPLIT", "BONUS_ISSUE"):
            if ratio_from is None or ratio_from <= 0:
                errors.append(ParseError(
                    row_num, "ratio_from", f"{action_type} requires positive ratio_from"
                ))
            if ratio_to is None or ratio_to <= 0:
                errors.append(ParseError(
                    row_num, "ratio_to", f"{action_type} requires positive ratio_to"
                ))

        # ── Confidence ──
        confidence = row.get("confidence", "HIGH").strip().upper()
        if confidence not in VALID_CONFIDENCE:
            confidence = "MEDIUM"

        # ── Source ──
        source = row.get("source", "CSV_IMPORT").strip()
        if not source:
            source = "CSV_IMPORT"

        currency = row.get("currency", "NGN").strip().upper()
        if not currency:
            currency = "NGN"

        notes = row.get("notes", "").strip() or None

        if errors:
            return None, errors

        action = {
            "symbol": symbol,
            "action_type": action_type,
            "ex_date": ex_date,
            "record_date": record_date,
            "payment_date": payment_date,
            "amount": amount,
            "ratio_from": ratio_from,
            "ratio_to": ratio_to,
            "currency": currency,
            "source": source,
            "confidence": confidence,
            "notes": notes,
            "artifact_ref": None,
            "ingested_at": datetime.utcnow(),
            "provenance": {
                "source": source,
                "ingested_at": datetime.utcnow().isoformat(),
                "method": "csv_import",
            },
        }
        return action, []
