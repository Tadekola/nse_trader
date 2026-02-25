"""
NGX Official Daily List PDF Provider.

Downloads and parses "Daily Official List - Equities" PDFs from
doclib.ngxgroup.com to extract authoritative EOD OHLCV data.

URL pattern:
  https://doclib.ngxgroup.com/DownloadsContent/
  Daily%20Official%20List%20-%20Equities%20for%20DD-MM-YYYY.pdf

Architecture:
  NgxOfficialListDownloader — httpx download + local cache + provenance
  NgxOfficialListParser     — pdfplumber table extraction → ParsedRow list
  NgxOfficialListProvider   — orchestrator: download → parse → OHLCVRecord list
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import get_settings
from app.core.http import http_fetch
from app.data.historical.storage import OHLCVRecord

try:
    import pdfplumber

    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

logger = logging.getLogger(__name__)

SOURCE_NAME = "NGX_OFFICIAL_LIST_PDF"


# ── Data classes ─────────────────────────────────────────────────────


@dataclass
class PDFProvenance:
    """Provenance metadata for a downloaded PDF."""

    source: str = SOURCE_NAME
    trade_date: Optional[date] = None
    url: str = ""
    local_path: str = ""
    sha256: str = ""
    downloaded_at: Optional[datetime] = None
    file_size_bytes: int = 0
    pages: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "trade_date": self.trade_date.isoformat() if self.trade_date else None,
            "url": self.url,
            "local_path": self.local_path,
            "sha256": self.sha256,
            "downloaded_at": (
                self.downloaded_at.isoformat() if self.downloaded_at else None
            ),
            "file_size_bytes": self.file_size_bytes,
            "pages": self.pages,
        }


@dataclass
class ParsedRow:
    """A single parsed row from the PDF, with quality flags."""

    symbol: str
    trade_date: date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    value: Optional[float] = None
    trades: Optional[int] = None
    prev_close: Optional[float] = None
    change: Optional[float] = None
    # Quality
    has_all_ohlcv: bool = False
    missing_fields: List[str] = field(default_factory=list)
    raw_row: Optional[List[str]] = None

    def to_ohlcv_record(self) -> Optional[OHLCVRecord]:
        """Convert to OHLCVRecord if close price is present."""
        if self.close is None or self.close <= 0:
            return None
        return OHLCVRecord(
            symbol=self.symbol.upper(),
            date=self.trade_date,
            open=self.open or self.close,
            high=self.high or max(self.open or self.close, self.close),
            low=self.low or min(self.open or self.close, self.close),
            close=self.close,
            volume=self.volume or 0,
            source=SOURCE_NAME,
        )


# ── Downloader ───────────────────────────────────────────────────────


class NgxOfficialListDownloader:
    """Downloads and locally caches NGX Daily Official List PDFs."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        settings = get_settings()
        self.cache_dir = Path(cache_dir or settings.NGX_PDF_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_retries = max_retries
        self._url_template = settings.NGX_PDF_URL_TEMPLATE

    def _build_url(self, trade_date: date) -> str:
        return self._url_template.format(
            dd=f"{trade_date.day:02d}",
            mm=f"{trade_date.month:02d}",
            yyyy=trade_date.year,
        )

    def _cache_path(self, trade_date: date) -> Path:
        filename = f"ngx_daily_list_{trade_date.isoformat()}.pdf"
        return self.cache_dir / filename

    async def download(
        self, trade_date: date
    ) -> Optional[Tuple[Path, PDFProvenance]]:
        """
        Download the PDF for a given trade date.

        Returns (local_path, provenance) or None if 404 / unavailable.
        Uses local cache — skips download if already cached.
        """
        cached = self._cache_path(trade_date)
        if cached.exists() and cached.stat().st_size > 0:
            logger.info("PDF cache hit for %s", trade_date)
            provenance = self._build_provenance(trade_date, cached)
            return cached, provenance

        url = self._build_url(trade_date)

        try:
            resp = await http_fetch(
                url,
                timeout=self.timeout,
                max_retries=self.max_retries,
                raise_for_status=False,
            )

            if resp.status_code == 404:
                logger.warning(
                    "PDF not found for %s (404): %s", trade_date, url
                )
                return None

            if resp.status_code >= 400:
                logger.error(
                    "HTTP %d downloading PDF for %s",
                    resp.status_code, trade_date,
                )
                return None

            # Verify we got a PDF (not an HTML error page)
            content_type = resp.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and not resp.content[:5] == b"%PDF-":
                logger.warning(
                    "Non-PDF response for %s (content-type: %s)",
                    trade_date,
                    content_type,
                )
                return None

            cached.write_bytes(resp.content)
            provenance = self._build_provenance(trade_date, cached, url)
            logger.info(
                "Downloaded NGX PDF for %s (%d bytes)",
                trade_date,
                len(resp.content),
            )
            return cached, provenance

        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.error(
                "Failed to download PDF for %s after retries: %s",
                trade_date, e,
            )
            return None

    def _build_provenance(
        self, trade_date: date, path: Path, url: Optional[str] = None
    ) -> PDFProvenance:
        content = path.read_bytes()
        return PDFProvenance(
            source=SOURCE_NAME,
            trade_date=trade_date,
            url=url or self._build_url(trade_date),
            local_path=str(path),
            sha256=hashlib.sha256(content).hexdigest(),
            downloaded_at=datetime.now(timezone.utc),
            file_size_bytes=len(content),
        )


# ── Parser ───────────────────────────────────────────────────────────


class NgxOfficialListParser:
    """
    Parses NGX Daily Official List PDFs using pdfplumber table extraction.

    Uses pdfplumber's built-in table detection (coordinate-based line
    detection) rather than brittle text splitting.  Handles multi-page
    tables, header repetition, and Nigerian numeric formatting.
    """

    # Canonical column name → normalized field name
    _COLUMN_MAP: Dict[str, str] = {
        # security / symbol
        "security": "security",
        "symbol": "security",
        "ticker": "security",
        "stock": "security",
        "security name": "security",
        # serial number (skip)
        "s/n": "sn",
        "no": "sn",
        "no.": "sn",
        # prev close
        "prev. close": "prev_close",
        "prev close": "prev_close",
        "previous close": "prev_close",
        "ref price": "prev_close",
        "reference price": "prev_close",
        "prev.close": "prev_close",
        # OHLC
        "open": "open",
        "opening": "open",
        "opening price": "open",
        "high": "high",
        "highest": "high",
        "high price": "high",
        "low": "low",
        "lowest": "low",
        "low price": "low",
        "close": "close",
        "closing": "close",
        "closing price": "close",
        "last": "close",
        # change
        "change": "change",
        "chg": "change",
        "+/-": "change",
        "change (+/-)": "change",
        "change(+/-)": "change",
        # trades / volume / value
        "trades": "trades",
        "deals": "trades",
        "no. of deals": "trades",
        "volume": "volume",
        "vol": "volume",
        "quantity": "volume",
        "vol. traded": "volume",
        "volume traded": "volume",
        "value": "value",
        "turnover": "value",
        "value (n)": "value",
        "value (₦)": "value",
        "value(n)": "value",
    }

    def parse(self, pdf_path: Path, trade_date: date) -> List[ParsedRow]:
        """
        Parse a Daily Official List PDF into rows.

        Args:
            pdf_path: Path to the PDF file
            trade_date: The trade date for this PDF

        Returns:
            List of ParsedRow objects
        """
        if not PDFPLUMBER_AVAILABLE:
            logger.error("pdfplumber not installed; cannot parse PDF")
            return []

        rows: List[ParsedRow] = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                column_map: Optional[Dict[int, str]] = None

                for page_num, page in enumerate(pdf.pages):
                    tables = page.extract_tables(
                        table_settings={
                            "vertical_strategy": "lines",
                            "horizontal_strategy": "lines",
                            "snap_tolerance": 5,
                        }
                    )

                    if not tables:
                        # Fallback: try text-based extraction
                        tables = page.extract_tables(
                            table_settings={
                                "vertical_strategy": "text",
                                "horizontal_strategy": "text",
                            }
                        )

                    if not tables:
                        logger.debug(
                            "No tables found on page %d of %s",
                            page_num + 1,
                            pdf_path.name,
                        )
                        continue

                    for table in tables:
                        for row_data in table:
                            if not row_data or all(
                                cell is None or str(cell).strip() == ""
                                for cell in row_data
                            ):
                                continue

                            # Detect header row
                            if column_map is None:
                                detected = self._detect_header(row_data)
                                if detected:
                                    column_map = detected
                                    logger.debug(
                                        "Header detected on page %d: %s",
                                        page_num + 1,
                                        column_map,
                                    )
                                    continue

                            # Handle repeated headers on subsequent pages
                            if self._is_header_row(row_data):
                                potential = self._detect_header(row_data)
                                if potential:
                                    column_map = potential
                                continue

                            if column_map is None:
                                continue

                            parsed = self._parse_data_row(
                                row_data, column_map, trade_date
                            )
                            if parsed:
                                rows.append(parsed)

        except Exception as e:
            logger.error("Error parsing PDF %s: %s", pdf_path, e)

        logger.info(
            "Parsed %d equity rows from %s for %s",
            len(rows),
            pdf_path.name,
            trade_date,
        )
        return rows

    def _detect_header(
        self, row: List[Optional[str]]
    ) -> Optional[Dict[int, str]]:
        """
        Detect if a row is a table header and return
        column index → field name mapping.
        """
        mapping: Dict[int, str] = {}
        has_security = False
        has_close = False

        for idx, cell in enumerate(row):
            if cell is None:
                continue
            # Normalize: lower, strip, collapse whitespace
            normalized = " ".join(str(cell).strip().lower().split())
            if normalized in self._COLUMN_MAP:
                field_name = self._COLUMN_MAP[normalized]
                mapping[idx] = field_name
                if field_name == "security":
                    has_security = True
                if field_name == "close":
                    has_close = True

        # Must have at least security + close to be a valid header
        if has_security and has_close:
            return mapping
        return None

    def _is_header_row(self, row: List[Optional[str]]) -> bool:
        """Check if row looks like a repeated header."""
        text = " ".join(str(c).lower() for c in row if c)
        return "security" in text and ("close" in text or "closing" in text)

    def _parse_data_row(
        self,
        row: List[Optional[str]],
        column_map: Dict[int, str],
        trade_date: date,
    ) -> Optional[ParsedRow]:
        """Parse a single data row using the column mapping."""
        fields: Dict[str, Optional[str]] = {}
        for idx, field_name in column_map.items():
            if idx < len(row):
                fields[field_name] = row[idx]

        # Must have a security name
        symbol_raw = fields.get("security")
        if not symbol_raw or not str(symbol_raw).strip():
            return None

        symbol = self._normalize_symbol(str(symbol_raw).strip())
        if not symbol:
            return None

        # Parse numeric fields
        open_p = self._parse_price(fields.get("open"))
        high_p = self._parse_price(fields.get("high"))
        low_p = self._parse_price(fields.get("low"))
        close_p = self._parse_price(fields.get("close"))
        volume = self._parse_int(fields.get("volume"))
        value = self._parse_price(fields.get("value"))
        trades = self._parse_int(fields.get("trades"))
        prev_close = self._parse_price(fields.get("prev_close"))
        change = self._parse_change(fields.get("change"))

        # Quality check
        missing: List[str] = []
        if open_p is None:
            missing.append("open")
        if high_p is None:
            missing.append("high")
        if low_p is None:
            missing.append("low")
        if close_p is None:
            missing.append("close")
        if volume is None:
            missing.append("volume")

        return ParsedRow(
            symbol=symbol,
            trade_date=trade_date,
            open=open_p,
            high=high_p,
            low=low_p,
            close=close_p,
            volume=volume,
            value=value,
            trades=trades,
            prev_close=prev_close,
            change=change,
            has_all_ohlcv=len(missing) == 0,
            missing_fields=missing,
            raw_row=[str(c) for c in row if c is not None],
        )

    def _normalize_symbol(self, raw: str) -> Optional[str]:
        """Normalize a security name/symbol from the PDF to canonical form."""
        symbol = raw.upper().strip()

        # Skip section headers, totals, summary rows
        skip_patterns = [
            "total",
            "grand total",
            "main board",
            "premium board",
            "growth board",
            "all share index",
            "market cap",
            "s/n",
            "no.",
            "date",
            "equities",
            "bond",
            "etf",
            "memorandum",
            "securities",
        ]
        if any(symbol.lower().startswith(p) for p in skip_patterns):
            return None

        # Skip if it's purely numeric (serial number column leaked)
        if symbol.replace(".", "").replace(",", "").isdigit():
            return None

        # Remove common corporate suffixes (longest first to avoid partial strips)
        for suffix in [" NIG LTD", " NIG LIMITED", " NIGERIA", " LIMITED", " PLC.", " PLC", " NIG", " LTD"]:
            if symbol.endswith(suffix):
                symbol = symbol[: -len(suffix)].strip()
                break  # only strip one suffix pass

        return symbol if symbol else None

    @staticmethod
    def _parse_price(value: Optional[str]) -> Optional[float]:
        """Parse a price string, handling commas and currency markers."""
        if value is None:
            return None
        text = str(value).strip()
        if not text or text in ("-", "--", "N/A", "n/a", ""):
            return None
        # Remove commas, currency symbols, whitespace
        text = text.replace(",", "").replace("₦", "").strip()
        # Handle accounting-style negatives: (1.50)
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
        try:
            val = float(text)
            return val if val >= 0 else None  # prices can't be negative
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_change(value: Optional[str]) -> Optional[float]:
        """Parse a change value (can be negative)."""
        if value is None:
            return None
        text = str(value).strip()
        if not text or text in ("-", "--", "N/A", "n/a", ""):
            return None
        text = text.replace(",", "").strip()
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
        try:
            return float(text)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_int(value: Optional[str]) -> Optional[int]:
        """Parse an integer string, handling commas."""
        if value is None:
            return None
        text = str(value).strip()
        if not text or text in ("-", "--", "N/A", "n/a", ""):
            return None
        text = text.replace(",", "").replace(" ", "").strip()
        try:
            return int(float(text))
        except (ValueError, TypeError):
            return None


# ── Provider (orchestrator) ──────────────────────────────────────────


class NgxOfficialListProvider:
    """
    High-level provider: download → parse → OHLCVRecord list.

    Usage::

        provider = NgxOfficialListProvider()
        records, provenance = await provider.fetch_date(date(2026, 2, 2))
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.downloader = NgxOfficialListDownloader(
            cache_dir=cache_dir,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.parser = NgxOfficialListParser()

    async def fetch_date(
        self, trade_date: date, symbols: Optional[List[str]] = None
    ) -> Tuple[List[OHLCVRecord], Optional[PDFProvenance]]:
        """
        Fetch and parse OHLCV data for a single trade date.

        Args:
            trade_date: The trade date to fetch
            symbols: Optional filter — only return records for these symbols

        Returns:
            (list of OHLCVRecords, provenance) or ([], None) if unavailable
        """
        result = await self.downloader.download(trade_date)
        if result is None:
            return [], None

        pdf_path, provenance = result

        # Parse
        parsed_rows = self.parser.parse(pdf_path, trade_date)

        # Enrich provenance with page count
        if PDFPLUMBER_AVAILABLE:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    provenance.pages = len(pdf.pages)
            except Exception:
                pass

        # Convert to OHLCVRecords
        symbols_upper = {s.upper() for s in symbols} if symbols else None
        records: List[OHLCVRecord] = []

        for row in parsed_rows:
            record = row.to_ohlcv_record()
            if record is None:
                continue
            if symbols_upper and record.symbol not in symbols_upper:
                continue
            records.append(record)

        logger.info(
            "NGX PDF %s: %d rows parsed, %d valid records%s",
            trade_date,
            len(parsed_rows),
            len(records),
            f" (filtered to {len(symbols_upper)} symbols)" if symbols_upper else "",
        )

        return records, provenance

    async def fetch_date_range(
        self,
        start_date: date,
        end_date: date,
        symbols: Optional[List[str]] = None,
        skip_weekends: bool = True,
    ) -> Tuple[List[OHLCVRecord], List[date], List[PDFProvenance]]:
        """
        Fetch OHLCV data for a range of trade dates.

        Returns:
            (all records, missing_dates, provenances)
        """
        all_records: List[OHLCVRecord] = []
        missing_dates: List[date] = []
        provenances: List[PDFProvenance] = []

        current = start_date
        while current <= end_date:
            # Skip weekends
            if skip_weekends and current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            records, provenance = await self.fetch_date(current, symbols)
            if records:
                all_records.extend(records)
                if provenance:
                    provenances.append(provenance)
            else:
                missing_dates.append(current)
                logger.info("Missing PDF for %s", current)

            current += timedelta(days=1)

        logger.info(
            "NGX PDF range %s → %s: %d records, %d missing dates",
            start_date,
            end_date,
            len(all_records),
            len(missing_dates),
        )

        return all_records, missing_dates, provenances
