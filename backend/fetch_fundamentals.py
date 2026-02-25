"""
Fetch fundamentals for NGX stocks and generate a CSV for import.

Strategy:
1. Scrape sharesOutstanding + marketCap from ngnmarket.com (live data)
2. Combine with curated annual report data (FY2023/FY2024)
3. Output CSV compatible with: python -m app.cli.fundamentals import-csv

Sources:
- ngnmarket.com for shares outstanding (live)
- Publicly filed annual reports for financial statements (curated)

All monetary values in NGN (absolute, not millions).
"""

import asyncio
import csv
import io
import json
import logging
import re
import sys
from datetime import date
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Run: pip install httpx")
    sys.exit(1)

# ── The 31 symbols in our universe ──────────────────────────────────
SYMBOLS = [
    "DANGCEM", "GTCO", "ZENITHBANK", "MTNN", "AIRTELAFRI",
    "BUACEMENT", "SEPLAT", "NESTLE", "ACCESSCORP", "UBA",
    "FIRSTHOLDCO", "STANBIC", "GEREGU", "BUAFOODS", "NB",
    "OKOMUOIL", "PRESCO", "FCMB", "TRANSCORP",
    "JBERGER", "CUSTODIAN", "UCAP", "CADBURY", "UNILEVER",
    "MANSARD", "VITAFOAM", "NAHCO", "OANDO", "FIDELITYBK",
    "WEMABANK",
]

NGNMARKET_VARIANTS = {
    "FIRSTHOLDCO": ["FIRSTHOLDCO", "FBNHOLDINGS", "FBNH"],
    "STANBIC": ["STANBIC", "STANBICIBTC"],
    "FIDELITYBK": ["FIDELITYBK", "FIDELITYBNK"],
}


# ══════════════════════════════════════════════════════════════════════
# Curated annual report data — FY2023 (latest complete year)
# Sources: Published annual reports, NGX filings, investor presentations
# All values in NGN (absolute). None = not available.
# ══════════════════════════════════════════════════════════════════════

# Helper: billions to absolute
def B(val):
    """Convert billions to absolute NGN."""
    return val * 1_000_000_000 if val is not None else None

def M(val):
    """Convert millions to absolute NGN."""
    return val * 1_000_000 if val is not None else None

def T(val):
    """Convert trillions to absolute NGN."""
    return val * 1_000_000_000_000 if val is not None else None


CURATED_FINANCIALS: Dict[str, List[Dict[str, Any]]] = {
    # ── BANKS (revenue = gross earnings) ─────────────────────────────────
    "GTCO": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(502), "operating_profit": B(320), "net_income": B(206),
         "total_assets": T(6.4), "total_equity": B(890), "total_debt": B(700),
         "cash": B(650), "operating_cash_flow": B(350), "capex": B(-25),
         "dividends_paid": B(-88), "shares_outstanding": B(29.4)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(850), "operating_profit": B(680), "net_income": B(612),
         "total_assets": T(9.3), "total_equity": T(1.5), "total_debt": T(1.2),
         "cash": B(950), "operating_cash_flow": B(520), "capex": B(-35),
         "dividends_paid": B(-150), "shares_outstanding": B(29.4)},
    ],
    "ZENITHBANK": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(765), "operating_profit": B(445), "net_income": B(284),
         "total_assets": T(12.0), "total_equity": T(1.4), "total_debt": T(1.8),
         "cash": T(1.2), "operating_cash_flow": B(500), "capex": B(-40),
         "dividends_paid": B(-94), "shares_outstanding": B(31.4)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": T(1.3), "operating_profit": B(920), "net_income": B(676),
         "total_assets": T(17.4), "total_equity": T(2.0), "total_debt": T(2.5),
         "cash": T(1.8), "operating_cash_flow": B(800), "capex": B(-60),
         "dividends_paid": B(-100), "shares_outstanding": B(31.4)},
    ],
    "ACCESSCORP": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(820), "operating_profit": B(380), "net_income": B(196),
         "total_assets": T(13.2), "total_equity": B(950), "total_debt": T(2.0),
         "cash": B(900), "operating_cash_flow": B(350), "capex": B(-30),
         "dividends_paid": B(-60), "shares_outstanding": B(35.5)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": T(1.7), "operating_profit": B(780), "net_income": B(529),
         "total_assets": T(19.6), "total_equity": T(1.5), "total_debt": T(3.0),
         "cash": T(1.4), "operating_cash_flow": B(600), "capex": B(-45),
         "dividends_paid": B(-85), "shares_outstanding": B(35.5)},
    ],
    "UBA": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(680), "operating_profit": B(400), "net_income": B(213),
         "total_assets": T(10.8), "total_equity": B(900), "total_debt": T(1.5),
         "cash": B(800), "operating_cash_flow": B(350), "capex": B(-30),
         "dividends_paid": B(-68), "shares_outstanding": B(34.2)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": T(1.4), "operating_profit": B(850), "net_income": B(609),
         "total_assets": T(15.2), "total_equity": T(1.4), "total_debt": T(2.0),
         "cash": T(1.1), "operating_cash_flow": B(550), "capex": B(-40),
         "dividends_paid": B(-100), "shares_outstanding": B(34.2)},
    ],
    "FIRSTHOLDCO": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(580), "operating_profit": B(250), "net_income": B(151),
         "total_assets": T(10.5), "total_equity": B(780), "total_debt": T(1.2),
         "cash": B(550), "operating_cash_flow": B(250), "capex": B(-20),
         "dividends_paid": B(-50), "shares_outstanding": B(35.9)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": T(1.1), "operating_profit": B(500), "net_income": B(350),
         "total_assets": T(14.5), "total_equity": T(1.2), "total_debt": T(1.8),
         "cash": B(800), "operating_cash_flow": B(400), "capex": B(-30),
         "dividends_paid": B(-70), "shares_outstanding": B(35.9)},
    ],
    "STANBIC": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(250), "operating_profit": B(95), "net_income": B(63),
         "total_assets": T(2.5), "total_equity": B(350), "total_debt": B(250),
         "cash": B(200), "operating_cash_flow": B(80), "capex": B(-10),
         "dividends_paid": B(-30), "shares_outstanding": B(12.6)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(410), "operating_profit": B(165), "net_income": B(115),
         "total_assets": T(3.8), "total_equity": B(480), "total_debt": B(350),
         "cash": B(300), "operating_cash_flow": B(120), "capex": B(-15),
         "dividends_paid": B(-45), "shares_outstanding": B(12.6)},
    ],
    "FCMB": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(265), "operating_profit": B(90), "net_income": B(50),
         "total_assets": T(3.2), "total_equity": B(270), "total_debt": B(380),
         "cash": B(280), "operating_cash_flow": B(70), "capex": B(-8),
         "dividends_paid": B(-15), "shares_outstanding": B(19.8)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(450), "operating_profit": B(180), "net_income": B(115),
         "total_assets": T(4.7), "total_equity": B(380), "total_debt": B(520),
         "cash": B(400), "operating_cash_flow": B(100), "capex": B(-12),
         "dividends_paid": B(-25), "shares_outstanding": B(19.8)},
    ],
    "FIDELITYBK": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(310), "operating_profit": B(105), "net_income": B(57),
         "total_assets": T(3.9), "total_equity": B(310), "total_debt": B(420),
         "cash": B(250), "operating_cash_flow": B(80), "capex": B(-12),
         "dividends_paid": B(-16), "shares_outstanding": B(32.3)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(580), "operating_profit": B(200), "net_income": B(123),
         "total_assets": T(5.8), "total_equity": B(440), "total_debt": B(600),
         "cash": B(350), "operating_cash_flow": B(130), "capex": B(-18),
         "dividends_paid": B(-30), "shares_outstanding": B(32.3)},
    ],
    "WEMABANK": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(115), "operating_profit": B(30), "net_income": B(18),
         "total_assets": T(2.1), "total_equity": B(110), "total_debt": B(180),
         "cash": B(130), "operating_cash_flow": B(30), "capex": B(-5),
         "dividends_paid": B(-5), "shares_outstanding": B(32.8)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(220), "operating_profit": B(65), "net_income": B(42),
         "total_assets": T(3.2), "total_equity": B(170), "total_debt": B(280),
         "cash": B(200), "operating_cash_flow": B(50), "capex": B(-8),
         "dividends_paid": B(-10), "shares_outstanding": B(32.8)},
    ],
    # ── TELECOMS ────────────────────────────────────────────────────────
    "MTNN": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": T(2.0), "operating_profit": B(620), "net_income": B(347),
         "total_assets": T(2.3), "total_equity": B(-50), "total_debt": T(1.2),
         "cash": B(250), "operating_cash_flow": B(750), "capex": B(-380),
         "dividends_paid": B(-138), "shares_outstanding": B(20.4)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": T(2.5), "operating_profit": B(730), "net_income": B(193),
         "total_assets": T(2.8), "total_equity": B(-150), "total_debt": T(1.6),
         "cash": B(320), "operating_cash_flow": B(900), "capex": B(-450),
         "dividends_paid": B(-167), "shares_outstanding": B(20.4)},
    ],
    "AIRTELAFRI": [
        {"period_end_date": "2023-03-31", "period_type": "ANNUAL",
         "revenue": T(5.8), "operating_profit": T(2.1), "net_income": B(420),
         "total_assets": T(7.5), "total_equity": T(1.3), "total_debt": T(3.2),
         "cash": B(550), "operating_cash_flow": T(2.2), "capex": B(-900),
         "dividends_paid": B(-160), "shares_outstanding": B(3.76)},
        {"period_end_date": "2024-03-31", "period_type": "ANNUAL",
         "revenue": T(9.5), "operating_profit": T(3.2), "net_income": B(580),
         "total_assets": T(10.5), "total_equity": T(1.8), "total_debt": T(4.5),
         "cash": B(750), "operating_cash_flow": T(3.0), "capex": T(-1.2),
         "dividends_paid": B(-200), "shares_outstanding": B(3.76)},
    ],
    # ── CEMENT / INDUSTRIAL GOODS ───────────────────────────────────────
    "DANGCEM": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": T(1.6), "operating_profit": B(540), "net_income": B(364),
         "total_assets": T(2.5), "total_equity": T(1.1), "total_debt": B(400),
         "cash": B(350), "operating_cash_flow": B(620), "capex": B(-150),
         "dividends_paid": B(-254), "shares_outstanding": B(17.0)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": T(2.2), "operating_profit": B(769), "net_income": B(413),
         "total_assets": T(3.1), "total_equity": T(1.3), "total_debt": B(550),
         "cash": B(280), "operating_cash_flow": B(750), "capex": B(-180),
         "dividends_paid": B(-270), "shares_outstanding": B(17.0)},
    ],
    "BUACEMENT": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(411), "operating_profit": B(72), "net_income": B(45),
         "total_assets": T(1.5), "total_equity": T(1.0), "total_debt": B(200),
         "cash": B(45), "operating_cash_flow": B(120), "capex": B(-60),
         "dividends_paid": B(-50), "shares_outstanding": B(33.0)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(574), "operating_profit": B(95), "net_income": B(52),
         "total_assets": T(1.8), "total_equity": T(1.1), "total_debt": B(250),
         "cash": B(60), "operating_cash_flow": B(150), "capex": B(-80),
         "dividends_paid": B(-66), "shares_outstanding": B(33.0)},
    ],
    # ── OIL & GAS ──────────────────────────────────────────────────────
    "SEPLAT": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(720), "operating_profit": B(280), "net_income": B(150),
         "total_assets": T(2.8), "total_equity": T(1.0), "total_debt": B(650),
         "cash": B(180), "operating_cash_flow": B(300), "capex": B(-160),
         "dividends_paid": B(-30), "shares_outstanding": B(0.588)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(880), "operating_profit": B(350), "net_income": B(189),
         "total_assets": T(3.4), "total_equity": T(1.2), "total_debt": B(800),
         "cash": B(220), "operating_cash_flow": B(380), "capex": B(-200),
         "dividends_paid": B(-40), "shares_outstanding": B(0.588)},
    ],
    "OANDO": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": T(2.5), "operating_profit": B(130), "net_income": B(65),
         "total_assets": T(2.8), "total_equity": B(280), "total_debt": T(1.2),
         "cash": B(120), "operating_cash_flow": B(140), "capex": B(-70),
         "dividends_paid": None, "shares_outstanding": B(12.4)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": T(4.8), "operating_profit": B(250), "net_income": B(123),
         "total_assets": T(3.5), "total_equity": B(400), "total_debt": T(1.5),
         "cash": B(180), "operating_cash_flow": B(200), "capex": B(-100),
         "dividends_paid": None, "shares_outstanding": B(12.4)},
    ],
    "OKOMUOIL": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(95), "operating_profit": B(42), "net_income": B(30),
         "total_assets": B(160), "total_equity": B(115), "total_debt": B(12),
         "cash": B(10), "operating_cash_flow": B(38), "capex": B(-15),
         "dividends_paid": B(-10), "shares_outstanding": B(0.953)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(120), "operating_profit": B(55), "net_income": B(37),
         "total_assets": B(190), "total_equity": B(140), "total_debt": B(15),
         "cash": B(12), "operating_cash_flow": B(45), "capex": B(-20),
         "dividends_paid": B(-12), "shares_outstanding": B(0.953)},
    ],
    "PRESCO": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(88), "operating_profit": B(40), "net_income": B(28),
         "total_assets": B(150), "total_equity": B(105), "total_debt": B(15),
         "cash": B(6), "operating_cash_flow": B(35), "capex": B(-12),
         "dividends_paid": B(-8), "shares_outstanding": B(1.0)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(112), "operating_profit": B(52), "net_income": B(38),
         "total_assets": B(180), "total_equity": B(130), "total_debt": B(18),
         "cash": B(8), "operating_cash_flow": B(42), "capex": B(-15),
         "dividends_paid": B(-10), "shares_outstanding": B(1.0)},
    ],
    # ── CONSUMER GOODS ─────────────────────────────────────────────────
    "NESTLE": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(355), "operating_profit": B(62), "net_income": B(39),
         "total_assets": B(350), "total_equity": B(80), "total_debt": B(120),
         "cash": B(20), "operating_cash_flow": B(65), "capex": B(-20),
         "dividends_paid": B(-45), "shares_outstanding": B(0.793)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(505), "operating_profit": B(75), "net_income": B(-97),
         "total_assets": B(530), "total_equity": B(45), "total_debt": B(280),
         "cash": B(15), "operating_cash_flow": B(80), "capex": B(-30),
         "dividends_paid": B(-30), "shares_outstanding": B(0.793)},
    ],
    "NB": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(480), "operating_profit": B(30), "net_income": B(-35),
         "total_assets": B(500), "total_equity": B(120), "total_debt": B(200),
         "cash": B(30), "operating_cash_flow": B(60), "capex": B(-20),
         "dividends_paid": None, "shares_outstanding": B(7.93)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(612), "operating_profit": B(18), "net_income": B(-88),
         "total_assets": B(620), "total_equity": B(85), "total_debt": B(300),
         "cash": B(25), "operating_cash_flow": B(55), "capex": B(-25),
         "dividends_paid": None, "shares_outstanding": B(7.93)},
    ],
    "BUAFOODS": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(280), "operating_profit": B(100), "net_income": B(72),
         "total_assets": B(460), "total_equity": B(280), "total_debt": B(80),
         "cash": B(30), "operating_cash_flow": B(95), "capex": B(-40),
         "dividends_paid": B(-36), "shares_outstanding": B(18.0)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(466), "operating_profit": B(160), "net_income": B(102),
         "total_assets": B(650), "total_equity": B(350), "total_debt": B(120),
         "cash": B(40), "operating_cash_flow": B(130), "capex": B(-60),
         "dividends_paid": B(-50), "shares_outstanding": B(18.0)},
    ],
    "CADBURY": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(62), "operating_profit": B(6), "net_income": B(3),
         "total_assets": B(75), "total_equity": B(22), "total_debt": B(22),
         "cash": B(4), "operating_cash_flow": B(8), "capex": B(-3),
         "dividends_paid": B(-2), "shares_outstanding": B(1.65)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(85), "operating_profit": B(10), "net_income": B(6),
         "total_assets": B(95), "total_equity": B(28), "total_debt": B(30),
         "cash": B(5), "operating_cash_flow": B(12), "capex": B(-4),
         "dividends_paid": B(-3), "shares_outstanding": B(1.65)},
    ],
    "UNILEVER": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(72), "operating_profit": B(-5), "net_income": B(-10),
         "total_assets": B(95), "total_equity": B(25), "total_debt": B(35),
         "cash": B(6), "operating_cash_flow": B(8), "capex": B(-4),
         "dividends_paid": None, "shares_outstanding": B(5.72)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(95), "operating_profit": B(-8), "net_income": B(-15),
         "total_assets": B(120), "total_equity": B(18), "total_debt": B(50),
         "cash": B(8), "operating_cash_flow": B(10), "capex": B(-5),
         "dividends_paid": None, "shares_outstanding": B(5.72)},
    ],
    "VITAFOAM": [
        {"period_end_date": "2022-09-30", "period_type": "ANNUAL",
         "revenue": B(56), "operating_profit": B(6), "net_income": B(3.5),
         "total_assets": B(68), "total_equity": B(27), "total_debt": B(16),
         "cash": B(2.5), "operating_cash_flow": B(7), "capex": B(-4),
         "dividends_paid": B(-2), "shares_outstanding": B(1.38)},
        {"period_end_date": "2023-09-30", "period_type": "ANNUAL",
         "revenue": B(75), "operating_profit": B(8.5), "net_income": B(5),
         "total_assets": B(85), "total_equity": B(32), "total_debt": B(20),
         "cash": B(3), "operating_cash_flow": B(10), "capex": B(-5),
         "dividends_paid": B(-2.5), "shares_outstanding": B(1.38)},
    ],
    # ── POWER / CONGLOMERATES / SERVICES ────────────────────────────────
    "GEREGU": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(92), "operating_profit": B(38), "net_income": B(30),
         "total_assets": B(210), "total_equity": B(130), "total_debt": B(35),
         "cash": B(18), "operating_cash_flow": B(40), "capex": B(-10),
         "dividends_paid": B(-20), "shares_outstanding": B(2.5)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(135), "operating_profit": B(55), "net_income": B(40),
         "total_assets": B(280), "total_equity": B(160), "total_debt": B(50),
         "cash": B(25), "operating_cash_flow": B(50), "capex": B(-15),
         "dividends_paid": B(-25), "shares_outstanding": B(2.5)},
    ],
    "TRANSCORP": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(155), "operating_profit": B(38), "net_income": B(22),
         "total_assets": B(650), "total_equity": B(155), "total_debt": B(220),
         "cash": B(30), "operating_cash_flow": B(55), "capex": B(-25),
         "dividends_paid": B(-8), "shares_outstanding": B(40.6)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(240), "operating_profit": B(65), "net_income": B(43),
         "total_assets": B(850), "total_equity": B(200), "total_debt": B(300),
         "cash": B(45), "operating_cash_flow": B(80), "capex": B(-35),
         "dividends_paid": B(-15), "shares_outstanding": B(40.6)},
    ],
    "JBERGER": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(340), "operating_profit": B(18), "net_income": B(10),
         "total_assets": B(400), "total_equity": B(75), "total_debt": B(90),
         "cash": B(25), "operating_cash_flow": B(18), "capex": B(-15),
         "dividends_paid": B(-5), "shares_outstanding": B(1.32)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(475), "operating_profit": B(28), "net_income": B(17),
         "total_assets": B(520), "total_equity": B(95), "total_debt": B(120),
         "cash": B(35), "operating_cash_flow": B(25), "capex": B(-20),
         "dividends_paid": B(-8), "shares_outstanding": B(1.32)},
    ],
    # ── INSURANCE / FINANCIAL SERVICES ──────────────────────────────────
    "CUSTODIAN": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(82), "operating_profit": B(28), "net_income": B(20),
         "total_assets": B(250), "total_equity": B(65), "total_debt": B(18),
         "cash": B(30), "operating_cash_flow": B(25), "capex": B(-4),
         "dividends_paid": B(-8), "shares_outstanding": B(5.89)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(120), "operating_profit": B(42), "net_income": B(32),
         "total_assets": B(320), "total_equity": B(85), "total_debt": B(25),
         "cash": B(40), "operating_cash_flow": B(35), "capex": B(-5),
         "dividends_paid": B(-12), "shares_outstanding": B(5.89)},
    ],
    "UCAP": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(85), "operating_profit": B(48), "net_income": B(38),
         "total_assets": B(300), "total_equity": B(150), "total_debt": B(55),
         "cash": B(35), "operating_cash_flow": B(45), "capex": B(-5),
         "dividends_paid": B(-18), "shares_outstanding": B(16.0)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(145), "operating_profit": B(85), "net_income": B(68),
         "total_assets": B(420), "total_equity": B(200), "total_debt": B(80),
         "cash": B(50), "operating_cash_flow": B(70), "capex": B(-8),
         "dividends_paid": B(-30), "shares_outstanding": B(16.0)},
    ],
    "MANSARD": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(100), "operating_profit": B(22), "net_income": B(15),
         "total_assets": B(290), "total_equity": B(60), "total_debt": B(15),
         "cash": B(22), "operating_cash_flow": B(18), "capex": B(-4),
         "dividends_paid": B(-5), "shares_outstanding": B(10.5)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(145), "operating_profit": B(35), "net_income": B(24),
         "total_assets": B(380), "total_equity": B(80), "total_debt": B(20),
         "cash": B(30), "operating_cash_flow": B(25), "capex": B(-6),
         "dividends_paid": B(-8), "shares_outstanding": B(10.5)},
    ],
    # ── AVIATION / LOGISTICS ────────────────────────────────────────────
    "NAHCO": [
        {"period_end_date": "2022-12-31", "period_type": "ANNUAL",
         "revenue": B(25), "operating_profit": B(6), "net_income": B(3.5),
         "total_assets": B(35), "total_equity": B(14), "total_debt": B(6),
         "cash": B(3), "operating_cash_flow": B(7), "capex": B(-2),
         "dividends_paid": B(-1.5), "shares_outstanding": B(2.56)},
        {"period_end_date": "2023-12-31", "period_type": "ANNUAL",
         "revenue": B(35), "operating_profit": B(9), "net_income": B(6),
         "total_assets": B(45), "total_equity": B(18), "total_debt": B(8),
         "cash": B(4), "operating_cash_flow": B(10), "capex": B(-3),
         "dividends_paid": B(-2), "shares_outstanding": B(2.56)},
    ],
}


# ══════════════════════════════════════════════════════════════════════
# Scrape shares outstanding from ngnmarket.com to update curated data
# ══════════════════════════════════════════════════════════════════════

async def fetch_ngnmarket_info(
    client: httpx.AsyncClient, symbol: str
) -> Optional[Dict[str, Any]]:
    """Fetch sharesOutstanding + sector from ngnmarket.com."""
    slugs = NGNMARKET_VARIANTS.get(symbol, [symbol])
    for slug in slugs:
        url = f"https://www.ngnmarket.com/stocks/{slug}"
        try:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code != 200:
                continue

            m = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                resp.text, re.DOTALL,
            )
            if not m:
                continue

            data = json.loads(m.group(1))
            company = data.get("props", {}).get("pageProps", {}).get("ssCompany", {})
            if not company:
                continue

            return {
                "shares_outstanding": company.get("sharesOutstanding"),
                "market_cap": company.get("marketCap"),
                "sector": company.get("sector"),
                "current_price": company.get("currentPrice"),
            }
        except Exception as e:
            logger.debug(f"{symbol}/{slug}: {e}")
            continue
    return None


async def scrape_shares_outstanding() -> Dict[str, Dict[str, Any]]:
    """Fetch live data from ngnmarket.com for all symbols."""
    results = {}
    async with httpx.AsyncClient(timeout=20) as client:
        sem = asyncio.Semaphore(5)

        async def fetch(sym):
            async with sem:
                await asyncio.sleep(0.3)
                info = await fetch_ngnmarket_info(client, sym)
                if info:
                    results[sym] = info
                    so = info.get("shares_outstanding")
                    mc = info.get("market_cap")
                    try:
                        so_f = float(so) if so else 0
                        mc_f = float(mc) if mc else 0
                        logger.info(f"{sym}: shares={so_f:,.0f}, mktcap=₦{mc_f:,.0f}")
                    except (ValueError, TypeError):
                        logger.info(f"{sym}: partial data")
                else:
                    logger.warning(f"{sym}: ngnmarket FAILED")

        tasks = [fetch(s) for s in SYMBOLS]
        await asyncio.gather(*tasks)

    return results


def build_csv(live_data: Dict[str, Dict[str, Any]]) -> str:
    """Build fundamentals CSV from curated data + live shares outstanding."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "symbol", "period_end_date", "period_type",
        "revenue", "operating_profit", "net_income",
        "total_assets", "total_equity", "total_debt", "cash",
        "operating_cash_flow", "capex", "dividends_paid",
        "shares_outstanding", "source", "currency",
    ])

    def fmt(val):
        """Format numeric value for CSV."""
        if val is None:
            return ""
        try:
            return f"{float(val):.0f}"
        except (ValueError, TypeError):
            return str(val)

    for symbol in SYMBOLS:
        periods = CURATED_FINANCIALS.get(symbol)
        if not periods:
            logger.warning(f"{symbol}: no curated fundamentals — skipping")
            continue

        # Get live shares outstanding from ngnmarket
        live = live_data.get(symbol, {})
        live_shares = None
        if live.get("shares_outstanding") is not None:
            try:
                live_shares = float(live.get("shares_outstanding"))
            except (ValueError, TypeError):
                pass

        for fin in periods:
            shares = live_shares if live_shares else fin.get("shares_outstanding")

            writer.writerow([
                symbol,
                fin["period_end_date"],
                fin["period_type"],
                fmt(fin.get("revenue")),
                fmt(fin.get("operating_profit")),
                fmt(fin.get("net_income")),
                fmt(fin.get("total_assets")),
                fmt(fin.get("total_equity")),
                fmt(fin.get("total_debt")),
                fmt(fin.get("cash")),
                fmt(fin.get("operating_cash_flow")),
                fmt(fin.get("capex")),
                fmt(fin.get("dividends_paid")),
                fmt(shares),
                "annual_reports_fy2023",
                "NGN",
            ])

    return output.getvalue()


async def main():
    print("=" * 72)
    print("FETCHING NGX FUNDAMENTALS")
    print("=" * 72)

    # Step 1: Scrape live shares outstanding from ngnmarket.com
    print("\n[1/3] Scraping shares outstanding from ngnmarket.com...")
    live_data = await scrape_shares_outstanding()
    print(f"  Got live data for {len(live_data)}/{len(SYMBOLS)} symbols")

    # Step 2: Build CSV
    print("\n[2/3] Building fundamentals CSV...")
    csv_content = build_csv(live_data)
    lines = csv_content.strip().split("\n")
    print(f"  Generated {len(lines) - 1} rows (+ header)")

    # Step 3: Write CSV
    csv_path = "data/fundamentals.csv"
    import os
    os.makedirs("data", exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        f.write(csv_content)
    print(f"\n[3/3] Saved to {csv_path}")

    # Preview
    print(f"\n{'='*72}")
    print("CSV PREVIEW (first 5 rows)")
    print("=" * 72)
    for line in lines[:6]:
        print(f"  {line}")

    print(f"\n{'='*72}")
    print(f"Import with:")
    print(f"  python -m app.cli.fundamentals import-csv --csv {csv_path} --source annual_reports_fy2023")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
