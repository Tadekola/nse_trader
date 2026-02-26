"""
Abstract base scraper with stealth Playwright, circuit breaker, and caching.

All concrete scrapers extend BaseScraper and implement:
  - source_name (str)
  - base_url (str)
  - _scrape_symbol(page, symbol) -> Optional[List[ScrapedFundamentals]]

The base class handles:
  - Browser lifecycle (stealth mode, randomized fingerprint)
  - Circuit breaker integration (per-source)
  - Local cache check (skip if fresh)
  - Human-like delays between requests
  - Batch orchestration with progress logging
"""

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from app.data.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, get_breaker_registry

logger = logging.getLogger(__name__)

# ── Stealth configuration ────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
]


# ── Data classes ─────────────────────────────────────────────────────

@dataclass
class ScrapedFundamentals:
    """One period of financial data scraped from a source."""
    symbol: str
    period_end_date: date
    period_type: str  # ANNUAL | INTERIM
    currency: str = "NGN"

    # Income statement
    revenue: Optional[float] = None
    operating_profit: Optional[float] = None
    net_income: Optional[float] = None

    # Balance sheet
    total_assets: Optional[float] = None
    total_equity: Optional[float] = None
    total_debt: Optional[float] = None
    cash: Optional[float] = None

    # Cash flow
    operating_cash_flow: Optional[float] = None
    capex: Optional[float] = None
    dividends_paid: Optional[float] = None

    # Shares
    shares_outstanding: Optional[float] = None

    # Supplementary (not in FundamentalsPeriodic but useful for validation)
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    dividend_yield: Optional[float] = None

    # Metadata
    source: str = ""
    scraped_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict matching FundamentalsPeriodic column names."""
        return {
            "symbol": self.symbol,
            "period_end_date": self.period_end_date,
            "period_type": self.period_type,
            "currency": self.currency,
            "revenue": self.revenue,
            "operating_profit": self.operating_profit,
            "net_income": self.net_income,
            "total_assets": self.total_assets,
            "total_equity": self.total_equity,
            "total_debt": self.total_debt,
            "cash": self.cash,
            "operating_cash_flow": self.operating_cash_flow,
            "capex": self.capex,
            "dividends_paid": self.dividends_paid,
            "shares_outstanding": self.shares_outstanding,
            "source": self.source,
        }

    def field_count(self) -> int:
        """Count how many financial fields are populated (non-None)."""
        fields = [
            self.revenue, self.operating_profit, self.net_income,
            self.total_assets, self.total_equity, self.total_debt, self.cash,
            self.operating_cash_flow, self.capex, self.dividends_paid,
        ]
        return sum(1 for f in fields if f is not None)


@dataclass
class SymbolResult:
    """Result of scraping a single symbol."""
    symbol: str
    success: bool
    periods: List[ScrapedFundamentals] = field(default_factory=list)
    error: Optional[str] = None
    elapsed_ms: float = 0.0


@dataclass
class ScrapeBatchResult:
    """Result of scraping a batch of symbols."""
    source: str
    total_symbols: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped_cached: int = 0
    total_periods: int = 0
    results: List[SymbolResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def all_periods(self) -> List[ScrapedFundamentals]:
        """Flatten all scraped periods across symbols."""
        periods = []
        for r in self.results:
            periods.extend(r.periods)
        return periods


# ── Base scraper ─────────────────────────────────────────────────────

class BaseScraper(ABC):
    """
    Abstract Playwright-based scraper with stealth and resilience.

    Subclasses implement:
      source_name: str property
      base_url: str property
      _scrape_symbol(page, symbol) -> Optional[List[ScrapedFundamentals]]
    """

    # Timing (seconds) — randomized per request
    MIN_DELAY = 2.0
    MAX_DELAY = 6.0
    PAGE_TIMEOUT_MS = 30_000  # 30s per page load

    def __init__(self):
        self._browser = None
        self._context = None
        registry = get_breaker_registry()
        self._breaker: CircuitBreaker = registry.get(
            f"scraper_{self.source_name}"
        )

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for this scraper source."""
        ...

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Base URL for the target site."""
        ...

    @abstractmethod
    async def _scrape_symbol(
        self, page: Any, symbol: str
    ) -> Optional[List[ScrapedFundamentals]]:
        """
        Scrape fundamentals for a single symbol using an open Playwright page.

        Returns a list of ScrapedFundamentals (one per fiscal period),
        or None if the symbol page could not be parsed.
        """
        ...

    # ── Public API ───────────────────────────────────────────────────

    async def scrape_batch(
        self,
        symbols: List[str],
        store: Optional[Any] = None,
        force: bool = False,
        max_age_days: int = 7,
    ) -> ScrapeBatchResult:
        """
        Scrape fundamentals for a list of symbols.

        Args:
            symbols: NGX symbols to scrape
            store: Optional FundamentalsStore for cache checking
            force: If True, ignore cache freshness
            max_age_days: Cache freshness threshold
        """
        batch_start = time.monotonic()
        result = ScrapeBatchResult(source=self.source_name, total_symbols=len(symbols))

        try:
            await self._launch_browser()

            for i, symbol in enumerate(symbols):
                # Cache check
                if store and not force and store.is_fresh(
                    self.source_name, symbol, max_age_days=max_age_days
                ):
                    result.skipped_cached += 1
                    logger.debug("Cache fresh for %s/%s, skipping", self.source_name, symbol)
                    continue

                # Circuit breaker check
                if not self._breaker.allow_request():
                    logger.warning(
                        "Circuit breaker OPEN for %s, skipping %s",
                        self.source_name, symbol,
                    )
                    result.failed += 1
                    result.results.append(SymbolResult(
                        symbol=symbol, success=False,
                        error="circuit_breaker_open",
                    ))
                    continue

                # Scrape
                sym_result = await self._scrape_one(symbol)
                result.results.append(sym_result)

                if sym_result.success:
                    result.succeeded += 1
                    result.total_periods += len(sym_result.periods)
                    self._breaker.record_success()

                    # Persist to cache
                    if store:
                        for period in sym_result.periods:
                            store.put(
                                source=self.source_name,
                                symbol=symbol,
                                period_end_date=period.period_end_date,
                                data=period.to_dict(),
                            )
                else:
                    result.failed += 1
                    self._breaker.record_failure()

                # Human-like delay between symbols (skip after last)
                if i < len(symbols) - 1:
                    delay = random.uniform(self.MIN_DELAY, self.MAX_DELAY)
                    await asyncio.sleep(delay)

                # Progress log every 5 symbols
                if (i + 1) % 5 == 0:
                    logger.info(
                        "[%s] Progress: %d/%d (ok=%d, fail=%d, cached=%d)",
                        self.source_name, i + 1, len(symbols),
                        result.succeeded, result.failed, result.skipped_cached,
                    )

        except Exception as e:
            logger.error("Batch scrape error for %s: %s", self.source_name, e)
        finally:
            await self._close_browser()

        result.elapsed_seconds = time.monotonic() - batch_start
        logger.info(
            "[%s] Batch complete: %d symbols, %d ok, %d fail, %d cached, %d periods in %.1fs",
            self.source_name, result.total_symbols, result.succeeded,
            result.failed, result.skipped_cached, result.total_periods,
            result.elapsed_seconds,
        )
        return result

    # ── Internal ─────────────────────────────────────────────────────

    async def _scrape_one(self, symbol: str) -> SymbolResult:
        """Scrape a single symbol with error handling and timing."""
        start = time.monotonic()
        try:
            page = await self._context.new_page()
            try:
                periods = await self._scrape_symbol(page, symbol)
                elapsed = (time.monotonic() - start) * 1000

                if periods:
                    # Stamp metadata
                    now = datetime.now(timezone.utc)
                    for p in periods:
                        p.source = self.source_name
                        p.scraped_at = now

                    return SymbolResult(
                        symbol=symbol, success=True,
                        periods=periods, elapsed_ms=elapsed,
                    )
                else:
                    return SymbolResult(
                        symbol=symbol, success=False,
                        error="no_data_parsed", elapsed_ms=elapsed,
                    )
            finally:
                await page.close()

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning(
                "[%s] Failed to scrape %s: %s (%.0fms)",
                self.source_name, symbol, e, elapsed,
            )
            return SymbolResult(
                symbol=symbol, success=False,
                error=str(e), elapsed_ms=elapsed,
            )

    async def _launch_browser(self) -> None:
        """Launch stealth Playwright browser."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "playwright required: pip install playwright && "
                "python -m playwright install chromium"
            )

        self._pw = await async_playwright().__aenter__()

        ua = random.choice(USER_AGENTS)
        viewport = random.choice(VIEWPORTS)

        self._browser = await self._pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        self._context = await self._browser.new_context(
            user_agent=ua,
            viewport=viewport,
            locale="en-US",
            timezone_id="Africa/Lagos",
            java_script_enabled=True,
            # Stealth: mask webdriver flag
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        # Stealth: patch navigator.webdriver
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            // Mask chrome automation
            window.chrome = { runtime: {} };
            // Mask permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters);
        """)

        logger.info(
            "[%s] Browser launched (UA=%s, viewport=%dx%d)",
            self.source_name, ua[:40] + "...", viewport["width"], viewport["height"],
        )

    async def _close_browser(self) -> None:
        """Gracefully close browser and playwright."""
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if hasattr(self, "_pw") and self._pw:
                await self._pw.__aexit__(None, None, None)
        except Exception as e:
            logger.debug("Browser cleanup error: %s", e)
        finally:
            self._browser = None
            self._context = None
