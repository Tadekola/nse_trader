"""
NGN Market Data Provider (Tier 0)

Fetches real market data from ngnmarket.com - a reliable Nigerian stock data aggregator.
Data is real-time/near real-time from the Nigerian Exchange.

Source: https://www.ngnmarket.com/

Phase 1: Now uses centralized SymbolAliasRegistry for symbol mapping.
"""

import logging
import asyncio
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

from app.core.http import http_fetch

from .base import (
    MarketDataProvider,
    PriceSnapshot,
    FetchResult,
    DataSource,
)
from app.data.sources.symbol_aliases import (
    get_symbol_alias_registry,
    DataProvider,
)

logger = logging.getLogger(__name__)


class NgnMarketProvider(MarketDataProvider):
    """
    Tier 1 Provider: NGN Market
    
    Fetches real market data from ngnmarket.com.
    This source aggregates data from NGX and provides reliable pricing.
    
    Data characteristics:
    - Real-time/near real-time during trading hours
    - Covers all NGX listed equities
    - Includes OHLC, volume, market cap
    - Reliable free data source
    """
    
    BASE_URL = "https://www.ngnmarket.com"
    STOCK_URL = "https://www.ngnmarket.com/stocks/{symbol}"
    
    # Legacy symbol mappings - NOW REPLACED by SymbolAliasRegistry
    # Kept for reference only - actual mappings are in symbol_aliases.py
    _LEGACY_MAPPINGS = {
        'FBNH': 'FBNHOLDINGS',
        'FLOURMILL': 'FLOURMILLS', 
        'ARDOVA': 'ARDOVAPLC',
    }
    
    def __init__(self, timeout: float = 10.0, max_concurrent: int = 10):
        """
        Initialize provider.
        
        Args:
            timeout: Request timeout in seconds
            max_concurrent: Max concurrent requests for batch fetching
        """
        self._timeout = timeout
        self._max_concurrent = max_concurrent
        self._last_fetch: Optional[datetime] = None
    
    @property
    def name(self) -> str:
        return "NGN Market"
    
    @property
    def tier(self) -> int:
        return 0  # Highest priority - real data from ngnmarket.com
    
    @property
    def source(self) -> DataSource:
        return DataSource.NGX_OFFICIAL  # Treat as official since it's real NGX data
    
    def is_available(self) -> bool:
        """Check if required libraries are installed."""
        return HTTPX_AVAILABLE
    
    async def fetch_snapshot(
        self,
        symbols: List[str]
    ) -> FetchResult:
        """
        Fetch price snapshots from NGN Market.
        
        Args:
            symbols: List of stock symbols to fetch
            
        Returns:
            FetchResult with snapshots for found symbols
        """
        import time
        start_time = time.time()
        
        if not self.is_available():
            return FetchResult(
                success=False,
                error="httpx library not available",
                source=self.source
            )
        
        symbols_upper = [s.upper() for s in symbols]
        snapshots = {}
        symbols_found = []
        symbols_missing = []
        errors = []
        
        # Fetch symbols concurrently with rate limiting
        semaphore = asyncio.Semaphore(self._max_concurrent)
        
        async def fetch_single(symbol: str) -> Optional[PriceSnapshot]:
            async with semaphore:
                try:
                    return await self._fetch_stock_data(symbol)
                except Exception as e:
                    logger.debug(f"Error fetching {symbol}: {e}")
                    return None
        
        # Fetch all symbols concurrently
        tasks = [fetch_single(symbol) for symbol in symbols_upper]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for symbol, result in zip(symbols_upper, results):
            if isinstance(result, Exception):
                symbols_missing.append(symbol)
                errors.append(f"{symbol}: {str(result)}")
            elif result is not None:
                snapshots[symbol] = result
                symbols_found.append(symbol)
            else:
                symbols_missing.append(symbol)
        
        self._last_fetch = datetime.utcnow()
        fetch_time = (time.time() - start_time) * 1000
        
        logger.info(f"NGN Market: fetched {len(snapshots)}/{len(symbols)} symbols in {fetch_time:.0f}ms")
        
        return FetchResult(
            success=len(snapshots) > 0,
            snapshots=snapshots,
            symbols_fetched=symbols_found,
            symbols_missing=symbols_missing,
            source=self.source,
            fetch_time_ms=fetch_time,
            error="; ".join(errors[:5]) if errors else None
        )
    
    async def _fetch_stock_data(self, symbol: str) -> Optional[PriceSnapshot]:
        """Fetch data for a single stock from NGN Market."""
        # Map symbol using centralized SymbolAliasRegistry (Phase 1)
        registry = get_symbol_alias_registry()
        mapped_symbol = registry.get_provider_symbol(symbol, DataProvider.NGNMARKET)
        url = self.STOCK_URL.format(symbol=mapped_symbol)
        
        response = await http_fetch(
            url,
            timeout=self._timeout,
            raise_for_status=False,
        )
        
        if response.status_code == 404:
            return None
        
        if response.status_code >= 400:
            return None
        
        # Extract __NEXT_DATA__ JSON from the page
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            response.text,
            re.DOTALL
        )
        
        if not match:
            logger.debug(f"No __NEXT_DATA__ found for {symbol}")
            return None
        
        try:
            data = json.loads(match.group(1))
            company = data.get('props', {}).get('pageProps', {}).get('ssCompany', {})
            
            if not company:
                return None
            
            # Use original symbol in the snapshot, not the mapped one
            snapshot = self._parse_company_data(company)
            if snapshot:
                snapshot.symbol = symbol  # Override with original symbol
            return snapshot
            
        except json.JSONDecodeError as e:
            logger.debug(f"JSON decode error for {symbol}: {e}")
            return None
    
    def _parse_company_data(self, company: Dict[str, Any]) -> Optional[PriceSnapshot]:
        """Parse company data from NGN Market response."""
        try:
            symbol = company.get('symbol', '').upper()
            if not symbol:
                return None
            
            # Parse price fields
            current_price = self._parse_float(company.get('currentPrice'), 0)
            if current_price <= 0:
                return None
            
            open_price = self._parse_float(company.get('openPrice'), current_price)
            high = self._parse_float(company.get('dayHigh'), current_price)
            low = self._parse_float(company.get('dayLow'), current_price)
            prev_close = self._parse_float(company.get('prevClose'), current_price)
            
            change = self._parse_float(company.get('priceChange'), 0)
            change_percent = self._parse_float(company.get('priceChangePercent'), 0)
            
            volume = self._parse_int(company.get('volume'), 0)
            value = self._parse_float(company.get('valueTraded'), 0)
            
            return PriceSnapshot(
                symbol=symbol,
                price=current_price,
                open=open_price,
                high=high,
                low=low,
                close=current_price,
                change=change,
                change_percent=change_percent,
                volume=volume,
                value=value,
                timestamp=datetime.utcnow(),
                source=DataSource.NGX_OFFICIAL,
                previous_close=prev_close,
            )
            
        except Exception as e:
            logger.debug(f"Error parsing company data: {e}")
            return None
    
    @staticmethod
    def _parse_float(value: Any, default: float = 0.0) -> float:
        """Parse a value to float."""
        if value is None:
            return default
        try:
            if isinstance(value, str):
                value = value.replace(',', '').strip()
            return float(value)
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def _parse_int(value: Any, default: int = 0) -> int:
        """Parse a value to int."""
        if value is None:
            return default
        try:
            if isinstance(value, str):
                value = value.replace(',', '').strip()
            return int(float(value))
        except (ValueError, TypeError):
            return default
