"""
Market Data Providers

3-tier production data sourcing:
- Tier 1: NGN Market (real-time NGX data from ngnmarket.com)
- Tier 2: NGX Official / Apt Securities (backup sources)
- Tier 3: Simulated (last resort fallback)
"""

from .base import MarketDataProvider, PriceSnapshot, DataSource, FetchResult, NumericParser
from .ngnmarket_provider import NgnMarketProvider
from .ngx_provider import NgxEquitiesPriceListProvider
from .apt_securities_provider import AptSecuritiesDailyPriceProvider
from .kwayisi_provider import KwayisiNGXProvider
from .simulated_provider import SimulatedProvider
from .chain import ProviderChain

__all__ = [
    'MarketDataProvider',
    'PriceSnapshot',
    'DataSource',
    'FetchResult',
    'NumericParser',
    'NgnMarketProvider',
    'NgxEquitiesPriceListProvider',
    'AptSecuritiesDailyPriceProvider',
    'KwayisiNGXProvider',
    'SimulatedProvider',
    'ProviderChain',
]
