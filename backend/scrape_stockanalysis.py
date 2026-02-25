"""
Scrape NGX fundamentals from stockanalysis.com using Playwright.

stockanalysis.com has income statement, balance sheet, and cash flow data
for NGX-listed stocks at /quote/ngx/{SYMBOL}/financials/ — but the data
is rendered client-side via JavaScript, so we need a headless browser.

Usage:
    python scrape_stockanalysis.py

Output:
    data/fundamentals_fresh.csv  — ready for:
    python -m app.cli.fundamentals import-csv --csv data/fundamentals_fresh.csv --source stockanalysis_2025
"""

import asyncio
import csv
import io
import json
import logging
import os
import re
import sys
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: playwright required. Run: pip install playwright && python -m playwright install chromium")
    sys.exit(1)

# ── Universe ────────────────────────────────────────────────────────
SYMBOLS = [
    "DANGCEM", "GTCO", "ZENITHBANK", "MTNN", "AIRTELAFRI",
    "BUACEMENT", "SEPLAT", "NESTLE", "ACCESSCORP", "UBA",
    "FIRSTHOLDCO", "STANBIC", "GEREGU", "BUAFOODS", "NB",
    "OKOMUOIL", "PRESCO", "FCMB", "TRANSCORP",
    "JBERGER", "CUSTODIAN", "UCAP", "CADBURY", "UNILEVER",
    "MANSARD", "VITAFOAM", "NAHCO", "OANDO", "FIDELITYBK",
    "WEMABANK",
]

# stockanalysis.com ticker mapping (most use the same symbol)
SA_TICKER_MAP = {
    "FIRSTHOLDCO": "FBNH",  # FBN Holdings
    "NB": "NB",
    "STANBIC": "STANBIC",
    "FIDELITYBK": "FIDELITYBK",
}


def parse_number(text: str) -> Optional[float]:
    """
    Parse a number from stockanalysis format.
    stockanalysis shows values in thousands with commas: '3,580,550' = 3,580,550 thousands = 3.58T.
    We multiply by 1000 to get absolute NGN values.
    Negative values shown as '-97,000' or '(97,000)'.
    Percentages like '28.29%' return None.
    """
    if not text or text.strip() in ("-", "\u2014", "N/A", "", "Upgrade"):
        return None
    text = text.strip()
    # Skip percentages
    if "%" in text:
        return None
    # Handle parentheses for negatives: (97,000) -> -97000
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    # Remove commas
    text = text.replace(",", "")
    # Handle suffix multipliers (some views use B/M)
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


async def scrape_financial_table(page, url: str) -> List[Dict[str, str]]:
    """
    Navigate to a stockanalysis financials page and extract the table data.
    Returns list of dicts: [{column_header: value, ...}, ...] — one per fiscal year.
    """
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except Exception as e:
        logger.warning(f"  Navigation failed: {e}")
        return []

    # Wait for financial data to render (JS-loaded)
    try:
        await page.wait_for_selector("table", timeout=12000)
        await asyncio.sleep(2)  # Extra time for data to populate
    except Exception:
        logger.warning(f"  No table rendered at {url}")
        return []

    # Extract table data via JavaScript — try multiple strategies
    data = await page.evaluate("""
    () => {
        // Strategy 1: Standard table with thead/tbody
        const tables = document.querySelectorAll('table');
        for (const table of tables) {
            const headers = [];
            // Try thead th, then first row th/td
            let headerRow = table.querySelector('thead tr');
            if (!headerRow) headerRow = table.querySelector('tr');
            if (!headerRow) continue;

            headerRow.querySelectorAll('th, td').forEach(cell => {
                headers.push(cell.innerText.trim());
            });

            if (headers.length < 2) continue;

            const rows = [];
            const bodyRows = table.querySelectorAll('tbody tr');
            const allRows = bodyRows.length > 0 ? bodyRows : table.querySelectorAll('tr:not(:first-child)');

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

        // Strategy 2: Look for data in any structured element
        return [];
    }
    """)
    return data


async def scrape_symbol(page, symbol: str) -> List[Dict[str, Any]]:
    """Scrape all financial statements for a symbol. Returns list of period dicts."""
    sa_ticker = SA_TICKER_MAP.get(symbol, symbol)
    base_url = f"https://stockanalysis.com/quote/ngx/{sa_ticker}"

    results_by_year: Dict[str, Dict[str, Any]] = {}

    def extract_year(col_name: str) -> Optional[str]:
        """Extract 4-digit year from column like 'FY 2024' or '2024'."""
        m = re.search(r'(\d{4})', col_name)
        return m.group(1) if m else None

    def get_year_columns(data_rows):
        """Get year columns from data, excluding TTM."""
        if not data_rows:
            return []
        sample = data_rows[0]
        cols = []
        for k in sample.keys():
            if k == "metric":
                continue
            if "TTM" in k:
                continue
            year = extract_year(k)
            if year:
                cols.append((k, year))
        return cols

    # ── Income Statement ───────────────────────────────────────────
    logger.info(f"{symbol}: fetching income statement...")
    is_data = await scrape_financial_table(page, f"{base_url}/financials/")
    if is_data:
        year_cols = get_year_columns(is_data)

        for col_name, year in year_cols:
            if year not in results_by_year:
                results_by_year[year] = {"period_end_date": f"{year}-12-31", "period_type": "ANNUAL"}

            for row in is_data:
                metric = row.get("metric", "").strip().lower()
                val_str = row.get(col_name, "")
                val = parse_number(val_str)

                if metric == "revenue":
                    results_by_year[year]["revenue"] = val
                elif metric in ("operating income", "operating profit", "operating expenses"):
                    if metric != "operating expenses":
                        results_by_year[year]["operating_profit"] = val
                elif metric == "net income":
                    results_by_year[year]["net_income"] = val
    else:
        logger.warning(f"{symbol}: no income statement data")

    await asyncio.sleep(1)

    # ── Balance Sheet ──────────────────────────────────────────────
    logger.info(f"{symbol}: fetching balance sheet...")
    bs_data = await scrape_financial_table(page, f"{base_url}/financials/balance-sheet/")
    if bs_data:
        year_cols = get_year_columns(bs_data)

        for col_name, year in year_cols:
            if year not in results_by_year:
                results_by_year[year] = {"period_end_date": f"{year}-12-31", "period_type": "ANNUAL"}

            for row in bs_data:
                metric = row.get("metric", "").strip().lower()
                val_str = row.get(col_name, "")
                val = parse_number(val_str)

                if metric == "total assets":
                    results_by_year[year]["total_assets"] = val
                elif metric in ("total equity", "shareholders' equity",
                                "total shareholders' equity", "stockholders' equity",
                                "total stockholders' equity"):
                    results_by_year[year]["total_equity"] = val
                elif metric == "total debt":
                    results_by_year[year]["total_debt"] = val
                elif metric in ("cash & equivalents", "cash and equivalents",
                                "cash & short-term investments",
                                "cash and short-term investments"):
                    if "cash" not in results_by_year[year]:
                        results_by_year[year]["cash"] = val
                elif metric == "shares outstanding":
                    results_by_year[year]["shares_outstanding"] = val
    else:
        logger.warning(f"{symbol}: no balance sheet data")

    await asyncio.sleep(1)

    # ── Cash Flow Statement ────────────────────────────────────────
    logger.info(f"{symbol}: fetching cash flow...")
    cf_data = await scrape_financial_table(page, f"{base_url}/financials/cash-flow-statement/")
    if cf_data:
        year_cols = get_year_columns(cf_data)

        for col_name, year in year_cols:
            if year not in results_by_year:
                results_by_year[year] = {"period_end_date": f"{year}-12-31", "period_type": "ANNUAL"}

            for row in cf_data:
                metric = row.get("metric", "").strip().lower()
                val_str = row.get(col_name, "")
                val = parse_number(val_str)

                if metric in ("operating cash flow", "cash from operations"):
                    results_by_year[year]["operating_cash_flow"] = val
                elif metric in ("capital expenditures", "capital expenditure", "capex"):
                    results_by_year[year]["capex"] = val
                elif "dividend" in metric and "paid" in metric:
                    results_by_year[year]["dividends_paid"] = val
    else:
        logger.warning(f"{symbol}: no cash flow data")

    # Sort by year descending, take latest 3
    sorted_years = sorted(results_by_year.keys(), reverse=True)[:3]
    periods = []
    for year in sorted_years:
        period = results_by_year[year]
        period["symbol"] = symbol
        # Only include if we have at least revenue or total_assets
        if period.get("revenue") is not None or period.get("total_assets") is not None:
            periods.append(period)

    return periods


def build_csv(all_periods: List[Dict[str, Any]]) -> str:
    """Build CSV from scraped periods."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "symbol", "period_end_date", "period_type",
        "revenue", "operating_profit", "net_income",
        "total_assets", "total_equity", "total_debt", "cash",
        "operating_cash_flow", "capex", "dividends_paid",
        "shares_outstanding", "source", "currency",
    ])

    def fmt(val):
        if val is None:
            return ""
        try:
            return f"{float(val):.0f}"
        except (ValueError, TypeError):
            return str(val)

    for p in all_periods:
        writer.writerow([
            p.get("symbol", ""),
            p.get("period_end_date", ""),
            p.get("period_type", "ANNUAL"),
            fmt(p.get("revenue")),
            fmt(p.get("operating_profit")),
            fmt(p.get("net_income")),
            fmt(p.get("total_assets")),
            fmt(p.get("total_equity")),
            fmt(p.get("total_debt")),
            fmt(p.get("cash")),
            fmt(p.get("operating_cash_flow")),
            fmt(p.get("capex")),
            fmt(p.get("dividends_paid")),
            fmt(p.get("shares_outstanding")),
            "stockanalysis_2025",
            "NGN",
        ])

    return output.getvalue()


async def debug_page(page, symbol: str):
    """Debug: dump page structure to understand stockanalysis.com's DOM."""
    sa_ticker = SA_TICKER_MAP.get(symbol, symbol)
    url = f"https://stockanalysis.com/quote/ngx/{sa_ticker}/financials/"
    logger.info(f"DEBUG: Loading {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except Exception as e:
        logger.error(f"  Navigation failed: {e}")
        return

    # Wait for JS render
    await asyncio.sleep(5)

    # Dump page info
    info = await page.evaluate("""
    () => {
        const result = {};
        result.title = document.title;
        result.url = window.location.href;

        // Count tables
        const tables = document.querySelectorAll('table');
        result.tableCount = tables.length;

        // Inspect each table
        result.tables = [];
        tables.forEach((table, idx) => {
            const info = { index: idx };
            // Headers
            const ths = table.querySelectorAll('th');
            info.thCount = ths.length;
            info.thTexts = Array.from(ths).slice(0, 8).map(th => th.innerText.trim());
            // Rows
            const trs = table.querySelectorAll('tr');
            info.trCount = trs.length;
            // First 3 row contents
            info.sampleRows = [];
            Array.from(trs).slice(0, 4).forEach(tr => {
                const cells = Array.from(tr.querySelectorAll('td, th')).map(c => c.innerText.trim());
                info.sampleRows.push(cells);
            });
            result.tables.push(info);
        });

        // Check for any element with financial data text
        const body = document.body.innerText;
        result.hasRevenue = body.includes('Revenue');
        result.hasNetIncome = body.includes('Net Income');
        result.hasTotalAssets = body.includes('Total Assets');

        // Check for React/Next data
        const nextData = document.getElementById('__NEXT_DATA__');
        result.hasNextData = !!nextData;
        if (nextData) {
            try {
                const parsed = JSON.parse(nextData.textContent);
                result.nextDataKeys = Object.keys(parsed.props?.pageProps || {});
            } catch(e) {
                result.nextDataError = e.message;
            }
        }

        return result;
    }
    """)

    print(f"\n  Title: {info.get('title')}")
    print(f"  URL: {info.get('url')}")
    print(f"  Tables: {info.get('tableCount')}")
    print(f"  Has Revenue: {info.get('hasRevenue')}")
    print(f"  Has Net Income: {info.get('hasNetIncome')}")
    print(f"  Has __NEXT_DATA__: {info.get('hasNextData')}")
    if info.get("nextDataKeys"):
        print(f"  __NEXT_DATA__ keys: {info['nextDataKeys']}")

    for t in info.get("tables", []):
        print(f"\n  Table {t['index']}: {t['thCount']} ths, {t['trCount']} trs")
        print(f"    Headers: {t['thTexts']}")
        for row in t.get("sampleRows", []):
            print(f"    Row: {row[:6]}")


async def main():
    print("=" * 72)
    print("SCRAPING NGX FUNDAMENTALS FROM STOCKANALYSIS.COM")
    print("=" * 72)

    # Check if --debug flag
    debug_mode = "--debug" in sys.argv

    all_periods = []
    failed = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        if debug_mode:
            # Debug mode: just inspect one symbol
            sym = sys.argv[2] if len(sys.argv) > 2 else "DANGCEM"
            await debug_page(page, sym)
            await browser.close()
            return

        for i, symbol in enumerate(SYMBOLS):
            print(f"\n[{i+1}/{len(SYMBOLS)}] {symbol}")
            try:
                periods = await scrape_symbol(page, symbol)
                if periods:
                    all_periods.extend(periods)
                    logger.info(f"  {symbol}: {len(periods)} periods scraped")
                    for p in periods:
                        rev = p.get("revenue")
                        ni = p.get("net_income")
                        logger.info(f"    {p['period_end_date']}: revenue={rev}, net_income={ni}")
                else:
                    failed.append(symbol)
                    logger.warning(f"  {symbol}: NO DATA")
            except Exception as e:
                failed.append(symbol)
                logger.error(f"  {symbol}: ERROR — {e}")

            # Rate limit
            await asyncio.sleep(2)

        await browser.close()

    # Build CSV
    print(f"\n{'='*72}")
    if all_periods:
        csv_content = build_csv(all_periods)
        csv_path = "data/fundamentals_fresh.csv"
        os.makedirs("data", exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            f.write(csv_content)

        lines = csv_content.strip().split("\n")
        row_count = len(lines) - 1
        symbols_ok = len(SYMBOLS) - len(failed)
        print(f"SUCCESS: {row_count} rows written to {csv_path}")
        print(f"Symbols scraped: {symbols_ok}/{len(SYMBOLS)}")
        if failed:
            print(f"Failed: {', '.join(failed)}")

        # ── Validation checks ──────────────────────────────────────────
        warnings = []

        # 1. Minimum row count (expect ~3 periods per symbol)
        expected_min = symbols_ok * 2
        if row_count < expected_min:
            warnings.append(f"LOW ROW COUNT: {row_count} rows < expected minimum {expected_min}")

        # 2. Check required fields populated
        symbols_with_revenue = set()
        symbols_with_net_income = set()
        for p in all_periods:
            if p.get("revenue") is not None:
                symbols_with_revenue.add(p["symbol"])
            if p.get("net_income") is not None:
                symbols_with_net_income.add(p["symbol"])
        scraped_symbols = set(p["symbol"] for p in all_periods)
        missing_rev = scraped_symbols - symbols_with_revenue
        missing_ni = scraped_symbols - symbols_with_net_income
        if missing_rev:
            warnings.append(f"MISSING REVENUE for: {', '.join(sorted(missing_rev))}")
        if missing_ni:
            warnings.append(f"MISSING NET_INCOME for: {', '.join(sorted(missing_ni))}")

        # 3. Sanity: no negative revenue
        neg_rev = [p["symbol"] for p in all_periods
                   if p.get("revenue") is not None and p["revenue"] < 0]
        if neg_rev:
            warnings.append(f"NEGATIVE REVENUE found for: {', '.join(sorted(set(neg_rev)))}")

        # 4. Failure rate
        fail_pct = len(failed) / len(SYMBOLS) * 100
        if fail_pct > 20:
            warnings.append(f"HIGH FAILURE RATE: {fail_pct:.0f}% of symbols failed")

        if warnings:
            print(f"\n⚠ VALIDATION WARNINGS ({len(warnings)}):")
            for w in warnings:
                print(f"  - {w}")
        else:
            print("\n✓ All validation checks passed")

        print(f"\nImport with:")
        print(f"  python -m app.cli.fundamentals import-csv --csv {csv_path} --source stockanalysis_2025")
    else:
        print("ERROR: No data scraped!")

    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
