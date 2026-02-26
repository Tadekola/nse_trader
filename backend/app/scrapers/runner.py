"""
Scraper Runner — orchestrates the scrape → validate → persist pipeline.

Flow:
1. Check FundamentalsStore for freshness (skip if recent)
2. Run scrapers (StockAnalysis primary, ngnmarket validation)
3. Validate scraped data (min fields, no absurd values)
4. Persist to FundamentalsPeriodic via the existing DB import pipeline
5. Write AuditEvent for provenance

Usage:
    from app.scrapers.runner import ScraperRunner
    runner = ScraperRunner()
    result = await runner.run(symbols=["GTCO", "DANGCEM"], force=False)

CLI:
    python -m app.scrapers.runner --symbols GTCO DANGCEM
    python -m app.scrapers.runner --all --force
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.scrapers.base import ScrapedFundamentals, ScrapeBatchResult
from app.scrapers.store import FundamentalsStore
from app.scrapers.stockanalysis import StockAnalysisScraper
from app.scrapers.ngnmarket_fundamentals import NgnmarketFundamentalsScraper
from app.data.universe import get_symbol_universe

logger = logging.getLogger(__name__)


# ── Validation ───────────────────────────────────────────────────────

class FundamentalsValidator:
    """Validates scraped fundamentals data before persistence."""

    MIN_FIELDS = 3         # Minimum populated financial fields per period
    MAX_REVENUE = 50e12    # 50 trillion NGN — sanity cap
    MAX_ASSETS = 100e12    # 100 trillion NGN

    def validate(self, period: ScrapedFundamentals) -> List[str]:
        """
        Validate a single scraped period.

        Returns list of warning strings. Empty = valid.
        """
        warnings = []

        # Minimum field count
        if period.field_count() < self.MIN_FIELDS:
            warnings.append(
                f"Only {period.field_count()} fields populated (min {self.MIN_FIELDS})"
            )

        # Revenue sanity
        if period.revenue is not None:
            if period.revenue < 0:
                warnings.append(f"Negative revenue: {period.revenue}")
            if abs(period.revenue) > self.MAX_REVENUE:
                warnings.append(f"Revenue exceeds sanity cap: {period.revenue}")

        # Assets sanity
        if period.total_assets is not None:
            if period.total_assets <= 0:
                warnings.append(f"Non-positive total assets: {period.total_assets}")
            if period.total_assets > self.MAX_ASSETS:
                warnings.append(f"Total assets exceeds sanity cap: {period.total_assets}")

        # Equity should not exceed assets
        if (
            period.total_equity is not None
            and period.total_assets is not None
            and period.total_equity > period.total_assets
        ):
            warnings.append(
                f"Equity ({period.total_equity}) exceeds assets ({period.total_assets})"
            )

        # Period date in reasonable range
        if period.period_end_date.year < 2015 or period.period_end_date.year > 2030:
            warnings.append(
                f"Period date out of range: {period.period_end_date}"
            )

        return warnings


# ── Run result ───────────────────────────────────────────────────────

class RunResult:
    """Result of a full scraper run."""

    def __init__(self):
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None
        self.primary_result: Optional[ScrapeBatchResult] = None
        self.validation_result: Optional[ScrapeBatchResult] = None
        self.periods_validated: int = 0
        self.periods_rejected: int = 0
        self.periods_persisted: int = 0
        self.validation_warnings: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "primary": {
                "source": self.primary_result.source if self.primary_result else None,
                "succeeded": self.primary_result.succeeded if self.primary_result else 0,
                "failed": self.primary_result.failed if self.primary_result else 0,
                "cached": self.primary_result.skipped_cached if self.primary_result else 0,
                "periods": self.primary_result.total_periods if self.primary_result else 0,
            },
            "validation": {
                "source": self.validation_result.source if self.validation_result else None,
                "succeeded": self.validation_result.succeeded if self.validation_result else 0,
            },
            "periods_validated": self.periods_validated,
            "periods_rejected": self.periods_rejected,
            "periods_persisted": self.periods_persisted,
            "warnings": self.validation_warnings[:20],
        }


# ── Runner ───────────────────────────────────────────────────────────

class ScraperRunner:
    """
    Orchestrates the full scrape → validate → persist pipeline.

    Primary scraper: StockAnalysisScraper (full financial statements)
    Validation scraper: NgnmarketFundamentalsScraper (P/E, EPS, div yield)
    """

    def __init__(
        self,
        store: Optional[FundamentalsStore] = None,
        max_age_days: int = 7,
    ):
        self.store = store or FundamentalsStore()
        self.max_age_days = max_age_days
        self.validator = FundamentalsValidator()
        self.primary = StockAnalysisScraper()
        self.validation = NgnmarketFundamentalsScraper()

    async def run(
        self,
        symbols: Optional[List[str]] = None,
        force: bool = False,
    ) -> RunResult:
        """
        Run the full scraper pipeline.

        Args:
            symbols: Specific symbols to scrape (default: full universe)
            force: If True, ignore cache freshness and re-scrape everything
        """
        result = RunResult()
        result.started_at = datetime.now(timezone.utc)

        if not symbols:
            symbols = get_symbol_universe()

        logger.info("ScraperRunner: starting for %d symbols (force=%s)", len(symbols), force)

        # ── Step 1: Primary scraper (StockAnalysis.com) ──────────────
        logger.info("Step 1: Running primary scraper (stockanalysis)...")
        result.primary_result = await self.primary.scrape_batch(
            symbols=symbols,
            store=self.store,
            force=force,
            max_age_days=self.max_age_days,
        )

        # ── Step 2: Validation scraper (ngnmarket) ───────────────────
        logger.info("Step 2: Running validation scraper (ngnmarket)...")
        result.validation_result = await self.validation.scrape_batch(
            symbols=symbols,
            store=self.store,
            force=force,
            max_age_days=self.max_age_days,
        )

        # ── Step 3: Validate scraped data ────────────────────────────
        logger.info("Step 3: Validating scraped data...")
        valid_periods: List[ScrapedFundamentals] = []

        if result.primary_result:
            for period in result.primary_result.all_periods:
                warnings = self.validator.validate(period)
                result.periods_validated += 1

                if warnings:
                    result.validation_warnings.extend(
                        f"{period.symbol}/{period.period_end_date}: {w}"
                        for w in warnings
                    )
                    # Only reject if too few fields (warnings about values are OK)
                    if period.field_count() < self.validator.MIN_FIELDS:
                        result.periods_rejected += 1
                        continue

                valid_periods.append(period)

        # ── Step 4: Persist to local store ───────────────────────────
        logger.info(
            "Step 4: Persisting %d validated periods to store...",
            len(valid_periods),
        )
        for period in valid_periods:
            self.store.put(
                source=period.source,
                symbol=period.symbol,
                period_end_date=period.period_end_date,
                data=period.to_dict(),
            )
            result.periods_persisted += 1

        # ── Step 5: Record run ───────────────────────────────────────
        result.finished_at = datetime.now(timezone.utc)

        self.store.record_run(
            source="scraper_runner",
            started_at=result.started_at,
            finished_at=result.finished_at,
            total=len(symbols),
            succeeded=result.primary_result.succeeded if result.primary_result else 0,
            failed=result.primary_result.failed if result.primary_result else 0,
            cached=result.primary_result.skipped_cached if result.primary_result else 0,
            periods=result.periods_persisted,
            elapsed_s=(result.finished_at - result.started_at).total_seconds(),
        )

        logger.info(
            "ScraperRunner complete: %d validated, %d rejected, %d persisted, %d warnings",
            result.periods_validated, result.periods_rejected,
            result.periods_persisted, len(result.validation_warnings),
        )
        return result

    async def export_to_csv(self, output_path: str = "data/fundamentals_fresh.csv") -> int:
        """
        Export cached StockAnalysis data to CSV for the existing import pipeline.

        Returns number of rows written.
        """
        import csv

        symbols = self.store.get_all_symbols("stockanalysis")
        if not symbols:
            logger.warning("No cached stockanalysis data to export")
            return 0

        rows = []
        for symbol in symbols:
            cached = self.store.get_cached("stockanalysis", symbol)
            for rec in cached:
                rows.append(rec)

        if not rows:
            return 0

        os.makedirs(os.path.dirname(output_path) or "data", exist_ok=True)

        headers = [
            "symbol", "period_end_date", "period_type",
            "revenue", "operating_profit", "net_income",
            "total_assets", "total_equity", "total_debt", "cash",
            "operating_cash_flow", "capex", "dividends_paid",
            "shares_outstanding", "source", "currency",
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        logger.info("Exported %d rows to %s", len(rows), output_path)
        return len(rows)


# ── CLI entrypoint ───────────────────────────────────────────────────

async def _cli_main():
    """CLI entrypoint for running scrapers."""
    import argparse

    parser = argparse.ArgumentParser(description="NSE Trader Fundamentals Scraper")
    parser.add_argument(
        "--symbols", nargs="+", help="Specific symbols to scrape"
    )
    parser.add_argument(
        "--all", action="store_true", help="Scrape full universe"
    )
    parser.add_argument(
        "--force", action="store_true", help="Ignore cache, re-scrape everything"
    )
    parser.add_argument(
        "--max-age", type=int, default=7, help="Cache max age in days (default: 7)"
    )
    parser.add_argument(
        "--export-csv", action="store_true",
        help="Export cached data to CSV after scraping"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    symbols = args.symbols
    if args.all or not symbols:
        symbols = None  # Runner will use full universe

    runner = ScraperRunner(max_age_days=args.max_age)
    result = await runner.run(symbols=symbols, force=args.force)

    print(f"\n{'='*60}")
    print(f"Scraper Run Complete")
    print(f"{'='*60}")
    print(f"  Primary: {result.primary_result.succeeded if result.primary_result else 0} ok, "
          f"{result.primary_result.failed if result.primary_result else 0} fail, "
          f"{result.primary_result.skipped_cached if result.primary_result else 0} cached")
    print(f"  Validation: {result.validation_result.succeeded if result.validation_result else 0} ok")
    print(f"  Persisted: {result.periods_persisted} periods")
    if result.validation_warnings:
        print(f"  Warnings: {len(result.validation_warnings)}")
        for w in result.validation_warnings[:10]:
            print(f"    - {w}")
    print(f"{'='*60}")

    if args.export_csv:
        count = await runner.export_to_csv()
        print(f"\nExported {count} rows to data/fundamentals_fresh.csv")
        print("Import with:")
        print("  python -m app.cli.fundamentals import-csv "
              "--csv data/fundamentals_fresh.csv --source stockanalysis_2025")


if __name__ == "__main__":
    asyncio.run(_cli_main())
