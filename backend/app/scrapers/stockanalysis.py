"""
StockAnalysis.com scraper for NGX fundamentals.

Extracts income statement, balance sheet, and cash flow data
from stockanalysis.com/quote/ngx/{SYMBOL}/financials/ pages.

Data is rendered client-side via JavaScript, requiring Playwright.
Produces ScrapedFundamentals objects (one per fiscal period, up to 3 years).

Formalized from the standalone scrape_stockanalysis.py script.
"""

import asyncio
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.scrapers.base import BaseScraper, ScrapedFundamentals

logger = logging.getLogger(__name__)

# stockanalysis.com uses different tickers for some NGX stocks
SA_TICKER_MAP = {
    "FIRSTHOLDCO": "FBNH",
}


def parse_number(text: str) -> Optional[float]:
    """
    Parse a number from stockanalysis format.

    Values shown in thousands with commas: '3,580,550' = 3,580,550 thousands.
    We multiply by 1000 to get absolute NGN values.
    Negative values shown as '-97,000' or '(97,000)'.
    Percentages like '28.29%' return None.
    """
    if not text or text.strip() in ("-", "\u2014", "N/A", "", "Upgrade"):
        return None
    text = text.strip()
    if "%" in text:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    text = text.replace(",", "")
    multiplier = 1000  # default: values in thousands
    if text.endswith("T"):
        multiplier = 1_000_000_000_000
        text = text[:-1]
    elif text.endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]
    elif text.endswith("K"):
        multiplier = 1_000
        text = text[:-1]
    try:
        val = float(text) * multiplier
        return -val if negative else val
    except ValueError:
        return None


def _extract_year(col_name: str) -> Optional[str]:
    """Extract 4-digit year from column like 'FY 2024' or '2024'."""
    m = re.search(r"(\d{4})", col_name)
    return m.group(1) if m else None


def _get_year_columns(data_rows: List[Dict[str, str]]) -> List[Tuple[str, str]]:
    """Get (column_name, year) tuples from data, excluding TTM."""
    if not data_rows:
        return []
    sample = data_rows[0]
    cols = []
    for k in sample.keys():
        if k == "metric":
            continue
        if "TTM" in k:
            continue
        year = _extract_year(k)
        if year:
            cols.append((k, year))
    return cols


# ── JavaScript table extractor ───────────────────────────────────────

TABLE_EXTRACT_JS = """
() => {
    const tables = document.querySelectorAll('table');
    for (const table of tables) {
        const headers = [];
        let headerRow = table.querySelector('thead tr');
        if (!headerRow) headerRow = table.querySelector('tr');
        if (!headerRow) continue;

        headerRow.querySelectorAll('th, td').forEach(cell => {
            headers.push(cell.innerText.trim());
        });

        if (headers.length < 2) continue;

        const rows = [];
        const bodyRows = table.querySelectorAll('tbody tr');
        const allRows = bodyRows.length > 0
            ? bodyRows
            : table.querySelectorAll('tr:not(:first-child)');

        allRows.forEach(tr => {
            const cells = [];
            tr.querySelectorAll('td, th').forEach(td => cells.push(td.innerText.trim()));
            if (cells.length >= 2) {
                const row = {};
                row['metric'] = cells[0];
                for (let i = 1; i < cells.length && i < headers.length; i++) {
                    row[headers[i]] = cells[i];
                }
                rows.push(row);
            }
        });

        if (rows.length > 0) return rows;
    }
    return [];
}
"""


class StockAnalysisScraper(BaseScraper):
    """
    Primary fundamentals scraper targeting stockanalysis.com.

    Extracts 3 financial statement tabs per symbol:
    - /financials/                   → Income Statement
    - /financials/balance-sheet/     → Balance Sheet
    - /financials/cash-flow-statement/ → Cash Flow

    Produces up to 3 fiscal periods per symbol.
    """

    MAX_PERIODS = 3  # Keep latest 3 fiscal years

    @property
    def source_name(self) -> str:
        return "stockanalysis"

    @property
    def base_url(self) -> str:
        return "https://stockanalysis.com"

    async def _scrape_symbol(
        self, page: Any, symbol: str
    ) -> Optional[List[ScrapedFundamentals]]:
        """Scrape all 3 financial statement tabs for a symbol."""
        sa_ticker = SA_TICKER_MAP.get(symbol, symbol)
        base = f"{self.base_url}/quote/ngx/{sa_ticker}"

        results_by_year: Dict[str, Dict[str, Any]] = {}

        # ── Income Statement ─────────────────────────────────────────
        is_data = await self._fetch_table(page, f"{base}/financials/")
        if is_data:
            year_cols = _get_year_columns(is_data)
            for col_name, year in year_cols:
                if year not in results_by_year:
                    results_by_year[year] = {}
                for row in is_data:
                    metric = row.get("metric", "").strip().lower()
                    val = parse_number(row.get(col_name, ""))
                    if metric == "revenue":
                        results_by_year[year]["revenue"] = val
                    elif metric in ("operating income", "operating profit"):
                        results_by_year[year]["operating_profit"] = val
                    elif metric == "net income":
                        results_by_year[year]["net_income"] = val
        else:
            logger.warning("[stockanalysis] %s: no income statement data", symbol)

        await asyncio.sleep(1)

        # ── Balance Sheet ────────────────────────────────────────────
        bs_data = await self._fetch_table(page, f"{base}/financials/balance-sheet/")
        if bs_data:
            year_cols = _get_year_columns(bs_data)
            for col_name, year in year_cols:
                if year not in results_by_year:
                    results_by_year[year] = {}
                for row in bs_data:
                    metric = row.get("metric", "").strip().lower()
                    val = parse_number(row.get(col_name, ""))
                    if metric == "total assets":
                        results_by_year[year]["total_assets"] = val
                    elif metric in (
                        "total equity", "shareholders' equity",
                        "total shareholders' equity", "stockholders' equity",
                        "total stockholders' equity",
                    ):
                        results_by_year[year]["total_equity"] = val
                    elif metric == "total debt":
                        results_by_year[year]["total_debt"] = val
                    elif metric in (
                        "cash & equivalents", "cash and equivalents",
                        "cash & short-term investments",
                        "cash and short-term investments",
                    ):
                        if "cash" not in results_by_year[year]:
                            results_by_year[year]["cash"] = val
                    elif metric == "shares outstanding":
                        results_by_year[year]["shares_outstanding"] = val
        else:
            logger.warning("[stockanalysis] %s: no balance sheet data", symbol)

        await asyncio.sleep(1)

        # ── Cash Flow Statement ──────────────────────────────────────
        cf_data = await self._fetch_table(
            page, f"{base}/financials/cash-flow-statement/"
        )
        if cf_data:
            year_cols = _get_year_columns(cf_data)
            for col_name, year in year_cols:
                if year not in results_by_year:
                    results_by_year[year] = {}
                for row in cf_data:
                    metric = row.get("metric", "").strip().lower()
                    val = parse_number(row.get(col_name, ""))
                    if metric in ("operating cash flow", "cash from operations"):
                        results_by_year[year]["operating_cash_flow"] = val
                    elif metric in (
                        "capital expenditures", "capital expenditure", "capex",
                    ):
                        results_by_year[year]["capex"] = val
                    elif "dividend" in metric and "paid" in metric:
                        results_by_year[year]["dividends_paid"] = val
        else:
            logger.warning("[stockanalysis] %s: no cash flow data", symbol)

        # ── Build ScrapedFundamentals ────────────────────────────────
        sorted_years = sorted(results_by_year.keys(), reverse=True)[
            : self.MAX_PERIODS
        ]
        periods = []
        for year in sorted_years:
            data = results_by_year[year]
            # Require at least revenue or total_assets
            if data.get("revenue") is None and data.get("total_assets") is None:
                continue
            periods.append(
                ScrapedFundamentals(
                    symbol=symbol,
                    period_end_date=date(int(year), 12, 31),
                    period_type="ANNUAL",
                    revenue=data.get("revenue"),
                    operating_profit=data.get("operating_profit"),
                    net_income=data.get("net_income"),
                    total_assets=data.get("total_assets"),
                    total_equity=data.get("total_equity"),
                    total_debt=data.get("total_debt"),
                    cash=data.get("cash"),
                    operating_cash_flow=data.get("operating_cash_flow"),
                    capex=data.get("capex"),
                    dividends_paid=data.get("dividends_paid"),
                    shares_outstanding=data.get("shares_outstanding"),
                )
            )

        if periods:
            logger.info(
                "[stockanalysis] %s: %d periods, fields=%s",
                symbol, len(periods),
                [p.field_count() for p in periods],
            )
        return periods if periods else None

    async def _fetch_table(
        self, page: Any, url: str
    ) -> List[Dict[str, str]]:
        """Navigate to a financials page and extract table data."""
        try:
            await page.goto(
                url, wait_until="domcontentloaded",
                timeout=self.PAGE_TIMEOUT_MS,
            )
        except Exception as e:
            logger.debug("[stockanalysis] Navigation failed: %s", e)
            return []

        # Wait for JS-rendered table
        try:
            await page.wait_for_selector("table", timeout=12_000)
            await asyncio.sleep(2)  # Extra settle time
        except Exception:
            logger.debug("[stockanalysis] No table rendered at %s", url)
            return []

        data = await page.evaluate(TABLE_EXTRACT_JS)
        return data if data else []
