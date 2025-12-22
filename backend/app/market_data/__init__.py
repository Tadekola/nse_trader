"""
Market Data Module

Production-grade 3-tier data sourcing pipeline:
- Tier 1: NGX Official Equities Price List
- Tier 2: Apt Securities Daily Price List  
- Tier 3: Simulated fallback (last resort)
"""

from .providers import (
    MarketDataProvider,
    PriceSnapshot,
    ProviderChain,
    NgxEquitiesPriceListProvider,
    AptSecuritiesDailyPriceProvider,
    SimulatedProvider,
)

__all__ = [
    'MarketDataProvider',
    'PriceSnapshot',
    'ProviderChain',
    'NgxEquitiesPriceListProvider',
    'AptSecuritiesDailyPriceProvider',
    'SimulatedProvider',
]
