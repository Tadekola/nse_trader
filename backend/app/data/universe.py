"""
Symbol Universe Configuration for NSE Trader.

Defines the top-20 most liquid NGX symbols that form
the core trading universe. These symbols MUST have
≥60 sessions of OHLCV history before the platform
can generate recommendations (G4 gate).

Config-driven: override via SYMBOL_UNIVERSE env var
(comma-separated list).
"""

import os
from typing import List

# Top-20 NGX symbols by liquidity and market cap.
# This list is the minimum viable universe for P0.
DEFAULT_UNIVERSE: List[str] = [
    "DANGCEM",    # Dangote Cement
    "GTCO",       # Guaranty Trust Holding
    "MTNN",       # MTN Nigeria
    "AIRTELAFRI", # Airtel Africa
    "BUACEMENT",  # BUA Cement
    "ZENITHBANK", # Zenith Bank
    "ACCESSCORP", # Access Holdings
    "BUAFOODS",   # BUA Foods
    "GEREGU",     # Geregu Power
    "SEPLAT",     # Seplat Energy
    "FBNH",       # FBN Holdings
    "NESTLE",     # Nestle Nigeria
    "UBA",        # United Bank for Africa
    "STANBIC",    # Stanbic IBTC Holdings
    "OANDO",      # Oando
    "FLOURMILL",  # Flour Mills
    "TRANSCORP",  # Transnational Corp
    "WAPCO",      # Lafarge Africa
    "PRESCO",     # Presco
    "TOTALENERG", # TotalEnergies Marketing
]


def get_symbol_universe() -> List[str]:
    """
    Get the active symbol universe.

    Can be overridden via SYMBOL_UNIVERSE env var (comma-separated).
    """
    env_override = os.getenv("SYMBOL_UNIVERSE")
    if env_override:
        return [s.strip().upper() for s in env_override.split(",") if s.strip()]
    return list(DEFAULT_UNIVERSE)
