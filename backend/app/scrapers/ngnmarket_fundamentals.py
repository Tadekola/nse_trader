"""
ngnmarket.com fundamentals scraper (validation source).

Extracts supplementary fundamental fields from ngnmarket.com stock pages:
- P/E ratio, EPS, dividend yield, shares outstanding
- Market cap, sector classification

This is a lightweight HTTP scraper (no Playwright needed) because
ngnmarket.com pages are server-rendered HTML.

Used as a validation/enrichment source alongside StockAnalysis.com.
"""

import asyncio
import logging
import random
import re
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.http import http_fetch
from app.data.circuit_breaker import get_breaker_registry
from app.data.sources.symbol_aliases import get_symbol_alias_registry, DataProvider
from app.scrapers.base import ScrapedFundamentals, ScrapeBatchResult, SymbolResult

logger = logging.getLogger(__name__)


def _parse_float(text: str) -> Optional[float]:
    """Parse a float from ngnmarket text, handling commas and currency."""
    if not text:
        return None
    text = text.strip().replace(",", "").replace("₦", "").replace("NGN", "")
    text = text.replace("%", "").strip()
    if text in ("-", "--", "N/A", "n/a", ""):
        return None
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _parse_market_cap(text: str) -> Optional[float]:
    """Parse market cap like '₦1.23T' or '₦456.7B'."""
    if not text:
        return None
    text = text.strip().replace("₦", "").replace(",", "").strip()
    multiplier = 1.0
    if text.endswith("T"):
        multiplier = 1e12
        text = text[:-1]
    elif text.endswith("B"):
        multiplier = 1e9
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1e6
        text = text[:-1]
    try:
        return float(text) * multiplier
    except (ValueError, TypeError):
        return None


class NgnmarketFundamentalsScraper:
    """
    Lightweight HTTP-based fundamentals scraper for ngnmarket.com.

    Does NOT extend BaseScraper (no Playwright needed).
    Uses the centralized http_fetch with circuit breaker.

    Extracts: P/E, EPS, dividend yield, shares outstanding, market cap.
    These fields supplement the full financial statements from StockAnalysis.com.
    """

    SOURCE_NAME = "ngnmarket_fundamentals"
    BASE_URL = "https://www.ngnmarket.com/stocks/{symbol}"
    MIN_DELAY = 1.0
    MAX_DELAY = 3.0

    def __init__(self):
        registry = get_breaker_registry()
        self._breaker = registry.get(self.SOURCE_NAME)
        self._alias_registry = get_symbol_alias_registry()

    @property
    def source_name(self) -> str:
        return self.SOURCE_NAME

    async def scrape_batch(
        self,
        symbols: List[str],
        store: Optional[Any] = None,
        force: bool = False,
        max_age_days: int = 7,
    ) -> ScrapeBatchResult:
        """Scrape fundamental fields for a batch of symbols."""
        batch_start = time.monotonic()
        result = ScrapeBatchResult(source=self.SOURCE_NAME, total_symbols=len(symbols))

        for i, symbol in enumerate(symbols):
            # Cache check
            if store and not force and store.is_fresh(
                self.SOURCE_NAME, symbol, max_age_days=max_age_days
            ):
                result.skipped_cached += 1
                continue

            # Circuit breaker
            if not self._breaker.allow_request():
                logger.warning("Circuit breaker OPEN for %s", self.SOURCE_NAME)
                result.failed += 1
                result.results.append(SymbolResult(
                    symbol=symbol, success=False, error="circuit_breaker_open",
                ))
                continue

            # Scrape
            sym_result = await self._scrape_one(symbol)
            result.results.append(sym_result)

            if sym_result.success:
                result.succeeded += 1
                result.total_periods += len(sym_result.periods)
                self._breaker.record_success()
                if store:
                    for period in sym_result.periods:
                        store.put(
                            self.SOURCE_NAME, symbol,
                            period.period_end_date, period.to_dict(),
                        )
            else:
                result.failed += 1
                self._breaker.record_failure()

            # Rate limiting
            if i < len(symbols) - 1:
                await asyncio.sleep(random.uniform(self.MIN_DELAY, self.MAX_DELAY))

        result.elapsed_seconds = time.monotonic() - batch_start
        logger.info(
            "[%s] Batch: %d symbols, %d ok, %d fail, %d cached in %.1fs",
            self.SOURCE_NAME, result.total_symbols, result.succeeded,
            result.failed, result.skipped_cached, result.elapsed_seconds,
        )
        return result

    async def _scrape_one(self, symbol: str) -> SymbolResult:
        """Scrape a single symbol from ngnmarket.com."""
        start = time.monotonic()
        try:
            # Map symbol to ngnmarket format
            mapped = self._alias_registry.resolve(symbol, DataProvider.NGNMARKET)
            url = self.BASE_URL.format(symbol=mapped)

            response = await http_fetch(
                url, timeout=10.0, max_retries=1, raise_for_status=False,
            )

            if response.status_code == 404:
                return SymbolResult(
                    symbol=symbol, success=False, error="404_not_found",
                    elapsed_ms=(time.monotonic() - start) * 1000,
                )

            if response.status_code >= 400:
                return SymbolResult(
                    symbol=symbol, success=False,
                    error=f"http_{response.status_code}",
                    elapsed_ms=(time.monotonic() - start) * 1000,
                )

            data = self._parse_html(symbol, response.text)
            elapsed = (time.monotonic() - start) * 1000

            if data:
                return SymbolResult(
                    symbol=symbol, success=True,
                    periods=[data], elapsed_ms=elapsed,
                )
            else:
                return SymbolResult(
                    symbol=symbol, success=False,
                    error="no_data_parsed", elapsed_ms=elapsed,
                )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning("[ngnmarket_fund] %s failed: %s", symbol, e)
            return SymbolResult(
                symbol=symbol, success=False,
                error=str(e), elapsed_ms=elapsed,
            )

    def _parse_html(self, symbol: str, html: str) -> Optional[ScrapedFundamentals]:
        """
        Parse fundamental fields from ngnmarket stock page HTML.

        Looks for key-value pairs in the stock detail section like:
          <td>P/E Ratio</td><td>5.23</td>
          <td>EPS</td><td>₦12.34</td>
        """
        if not html:
            return None

        fields: Dict[str, Optional[float]] = {}

        # Pattern: table cells with label → value pairs
        # ngnmarket uses <td> or <th> for labels and adjacent <td> for values
        patterns = [
            (r"(?:P/E\s*Ratio|PE\s*Ratio)[^<]*</(?:td|th)>\s*<td[^>]*>([^<]+)",
             "pe_ratio"),
            (r"(?:EPS|Earnings\s*Per\s*Share)[^<]*</(?:td|th)>\s*<td[^>]*>([^<]+)",
             "eps"),
            (r"(?:Dividend\s*Yield)[^<]*</(?:td|th)>\s*<td[^>]*>([^<]+)",
             "dividend_yield"),
            (r"(?:Shares\s*Outstanding|Outstanding\s*Shares)[^<]*</(?:td|th)>\s*<td[^>]*>([^<]+)",
             "shares_outstanding"),
            (r"(?:Market\s*Cap(?:italization)?)[^<]*</(?:td|th)>\s*<td[^>]*>([^<]+)",
             "market_cap"),
        ]

        for pattern, field_name in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                raw = match.group(1).strip()
                if field_name == "market_cap":
                    fields[field_name] = _parse_market_cap(raw)
                else:
                    fields[field_name] = _parse_float(raw)

        if not fields:
            return None

        # Build a ScrapedFundamentals with current date as period
        # (these are point-in-time metrics, not periodic statements)
        now = datetime.now(timezone.utc)
        return ScrapedFundamentals(
            symbol=symbol,
            period_end_date=date.today(),
            period_type="SNAPSHOT",
            pe_ratio=fields.get("pe_ratio"),
            eps=fields.get("eps"),
            dividend_yield=fields.get("dividend_yield"),
            shares_outstanding=fields.get("shares_outstanding"),
            source=self.SOURCE_NAME,
            scraped_at=now,
        )
