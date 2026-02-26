"""
Playwright-based scraper framework for NGX fundamentals data.

Architecture:
- BaseScraper: Abstract base with stealth Playwright, circuit breaker, local cache
- FundamentalsStore: SQLite cache layer to prevent redundant browser launches
- StockAnalysisScraper: Primary fundamentals source (income, balance, cash flow)
- NgnmarketFundamentalsScraper: Validation source (P/E, EPS, div yield)
- ScraperRunner: Orchestrator (freshness check → scrape → validate → persist)
"""

from app.scrapers.base import BaseScraper, ScrapedFundamentals, ScrapeBatchResult
from app.scrapers.store import FundamentalsStore

__all__ = [
    "BaseScraper",
    "ScrapedFundamentals",
    "ScrapeBatchResult",
    "FundamentalsStore",
]
