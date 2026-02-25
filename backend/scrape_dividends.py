"""
Scrape NGX dividend history from stockanalysis.com using Playwright.

Outputs a CSV in corporate_actions format ready for:
    python -m app.cli.corporate_actions import-csv --file data/dividends_ngx.csv

CSV columns: symbol,action_type,ex_date,record_date,payment_date,amount,ratio_from,ratio_to,currency,source,confidence,notes
"""

import asyncio
import csv
import logging
import os
import re
import sys
from datetime import date
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: playwright required. Run: pip install playwright && python -m playwright install chromium")
    sys.exit(1)

# Same universe as fundamentals scraper
SYMBOLS = [
    "DANGCEM", "GTCO", "ZENITHBANK", "MTNN", "AIRTELAFRI",
    "BUACEMENT", "SEPLAT", "NESTLE", "ACCESSCORP", "UBA",
    "FIRSTHOLDCO", "STANBIC", "GEREGU", "BUAFOODS", "NB",
    "OKOMUOIL", "PRESCO", "FCMB", "TRANSCORP",
    "JBERGER", "CUSTODIAN", "UCAP", "CADBURY", "UNILEVER",
    "MANSARD", "VITAFOAM", "NAHCO", "OANDO", "FIDELITYBK",
    "WEMABANK",
]

SA_TICKER_MAP = {
    "FIRSTHOLDCO": "FBNH",
}

OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "data", "dividends_ngx.csv")


def parse_date(date_str: str) -> Optional[str]:
    """Parse date string from stockanalysis.com into YYYY-MM-DD."""
    if not date_str or date_str.strip() in ("", "-", "N/A", "n/a"):
        return None
    date_str = date_str.strip()
    # Try various formats: "Jun 15, 2024", "2024-06-15", "06/15/2024"
    import datetime as dt
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            d = dt.datetime.strptime(date_str, fmt)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    logger.warning("Could not parse date: '%s'", date_str)
    return None


def parse_amount(amount_str: str) -> Optional[float]:
    """Parse dividend amount from stockanalysis.com."""
    if not amount_str or amount_str.strip() in ("", "-", "N/A"):
        return None
    s = amount_str.strip().replace(",", "").replace("₦", "").replace("NGN", "").strip()
    # Handle parentheses for negative
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        logger.warning("Could not parse amount: '%s'", amount_str)
        return None


async def scrape_dividends(symbol: str, sa_ticker: str) -> List[Dict[str, Any]]:
    """Scrape dividend history for a single symbol."""
    url = f"https://stockanalysis.com/quote/ngx/{sa_ticker}/dividend/"
    dividends = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)  # Wait for JS rendering

            # Look for dividend history table
            # stockanalysis.com typically shows: Ex-Dividend Date, Amount, Record Date, Pay Date
            rows = await page.query_selector_all("table tbody tr")

            if not rows:
                logger.info("%s (%s): No dividend table found", symbol, sa_ticker)
                await browser.close()
                return dividends

            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) < 2:
                    continue

                cell_texts = []
                for cell in cells:
                    text = await cell.inner_text()
                    cell_texts.append(text.strip())

                # Try to extract ex-date and amount from available columns
                # Common layouts:
                # [ex_date, amount, record_date, pay_date, type]
                # [ex_date, cash_amount, declaration_date, record_date, pay_date]
                ex_date_str = cell_texts[0] if len(cell_texts) > 0 else None
                amount_str = cell_texts[1] if len(cell_texts) > 1 else None

                ex_date = parse_date(ex_date_str)
                amount = parse_amount(amount_str)

                if not ex_date or not amount or amount <= 0:
                    continue

                record_date = parse_date(cell_texts[2]) if len(cell_texts) > 2 else None
                pay_date = parse_date(cell_texts[3]) if len(cell_texts) > 3 else None

                dividends.append({
                    "symbol": symbol,
                    "action_type": "CASH_DIVIDEND",
                    "ex_date": ex_date,
                    "record_date": record_date or "",
                    "payment_date": pay_date or "",
                    "amount": amount,
                    "ratio_from": "",
                    "ratio_to": "",
                    "currency": "NGN",
                    "source": "stockanalysis_2025",
                    "confidence": "MEDIUM",
                    "notes": f"Scraped from stockanalysis.com/quote/ngx/{sa_ticker}/dividend/",
                })

            logger.info("%s (%s): Found %d dividends", symbol, sa_ticker, len(dividends))

        except Exception as e:
            logger.error("%s (%s): Error scraping dividends: %s", symbol, sa_ticker, e)
        finally:
            await browser.close()

    return dividends


async def main():
    all_dividends = []

    for symbol in SYMBOLS:
        sa_ticker = SA_TICKER_MAP.get(symbol, symbol)
        logger.info("Scraping dividends for %s (SA: %s)...", symbol, sa_ticker)
        divs = await scrape_dividends(symbol, sa_ticker)
        all_dividends.extend(divs)
        await asyncio.sleep(1)  # Rate limiting

    # Write CSV
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    fieldnames = [
        "symbol", "action_type", "ex_date", "record_date", "payment_date",
        "amount", "ratio_from", "ratio_to", "currency", "source", "confidence", "notes"
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        # Sort by symbol, then ex_date
        all_dividends.sort(key=lambda d: (d["symbol"], d["ex_date"]))
        writer.writerows(all_dividends)

    logger.info("Written %d dividend records to %s", len(all_dividends), OUTPUT_CSV)
    print(f"\nTotal: {len(all_dividends)} dividends for {len(set(d['symbol'] for d in all_dividends))} symbols")
    print(f"Output: {OUTPUT_CSV}")
    print(f"\nImport with:")
    print(f"  python -m app.cli.corporate_actions import-csv --file {OUTPUT_CSV}")


if __name__ == "__main__":
    asyncio.run(main())
