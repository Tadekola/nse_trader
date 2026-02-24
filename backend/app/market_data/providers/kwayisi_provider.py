"""
Kwayisi AFX NGX Provider (Secondary Validation)

Fetches market data from afx.kwayisi.org/ngx as an independent validation source.
This provider is NOT used as primary data - it validates data from the primary source.

Source: https://afx.kwayisi.org/ngx/

Purpose:
- Independent validation of primary (ngnmarket.com) prices
- Boost confidence when sources agree
- Flag divergence for review
- Reduce simulation fallback

Design:
- Never overrides primary source
- No price averaging
- Respects rate limits
- Non-blocking (runs in parallel)
"""

import logging
import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

from app.core.http import http_fetch

try:
    import afrimarket as afm
    import pandas as pd
    AFRIMARKET_AVAILABLE = True
except ImportError:
    AFRIMARKET_AVAILABLE = False

from .base import (
    MarketDataProvider,
    PriceSnapshot,
    FetchResult,
    DataSource,
    NumericParser,
)
from app.data.sources.symbol_aliases import (
    get_symbol_alias_registry,
    DataProvider,
)

logger = logging.getLogger(__name__)


# Add KWAYISI to DataSource enum if not present
class KwayisiDataSource:
    """Kwayisi-specific data source identifier."""
    KWAYISI = "kwayisi"


@dataclass
class ValidationSnapshot:
    """
    Price snapshot for validation purposes.
    
    Separate from PriceSnapshot to emphasize this is for validation only,
    not primary data consumption.
    """
    symbol: str
    price: float
    change_percent: float
    volume: Optional[int]
    timestamp: datetime
    source: str = "KWAYISI"
    
    # Staleness tracking
    last_trade_date: Optional[datetime] = None
    
    def is_stale(self, max_age_hours: int = 24) -> bool:
        """Check if data is stale."""
        if self.last_trade_date:
            return (datetime.utcnow() - self.last_trade_date) > timedelta(hours=max_age_hours)
        return (datetime.utcnow() - self.timestamp) > timedelta(hours=max_age_hours)


class KwayisiNGXProvider(MarketDataProvider):
    """
    Secondary Validation Provider: Kwayisi AFX NGX
    
    Fetches data from afx.kwayisi.org/ngx as an independent validation source.
    
    Methods:
    1. Primary: Use afrimarket python library
    2. Fallback: Web scraping via httpx
    
    Source: https://afx.kwayisi.org/ngx/
    """
    
    BASE_URL = "https://afx.kwayisi.org/ngx"
    STOCK_URL = "https://afx.kwayisi.org/ngx/{symbol}.html"
    
    # Rate limiting: Be respectful to the free service
    MIN_REQUEST_INTERVAL_MS = 200  # 200ms between requests
    MAX_CONCURRENT = 5  # Max parallel requests
    
    def __init__(self, timeout: float = 15.0):
        """
        Initialize provider.
        
        Args:
            timeout: Request timeout in seconds
        """
        self._timeout = timeout
        self._last_request_time: Optional[datetime] = None
        self._request_count = 0
    
    @property
    def name(self) -> str:
        return "Kwayisi AFX"
    
    @property
    def tier(self) -> int:
        return 2  # Secondary tier - validation only
    
    @property
    def source(self) -> DataSource:
        return DataSource.KWAYISI
    
    @property
    def source_name(self) -> str:
        return "KWAYISI"
    
    def is_available(self) -> bool:
        """Check if required libraries are installed."""
        return HTTPX_AVAILABLE or AFRIMARKET_AVAILABLE
    
    async def fetch_snapshot(
        self,
        symbols: List[str]
    ) -> FetchResult:
        """
        Fetch price snapshots from Kwayisi AFX.
        
        Args:
            symbols: List of stock symbols to fetch
            
        Returns:
            FetchResult with snapshots for found symbols
        """
        # Try library first if available
        if AFRIMARKET_AVAILABLE:
            try:
                return await self._fetch_via_library(symbols)
            except Exception as e:
                logger.warning(f"Kwayisi (Library) failed: {e}. Falling back to scraping.")
        
        # Fallback to scraping
        if HTTPX_AVAILABLE:
            return await self._fetch_via_scraping(symbols)
            
        return FetchResult(
            success=False,
            error="No available method (httpx or afrimarket missing)",
            source=self.source
        )

    async def _fetch_via_library(self, symbols: List[str]) -> FetchResult:
        """Fetch data using afrimarket library."""
        import time
        start_time = time.time()
        
        loop = asyncio.get_running_loop()
        
        def _run_library_fetch():
            if 'Nigerian Stock Exchange' not in afm.markets:
                raise ValueError("NGX not found in afrimarket")
            ngx = afm.Exchange(market=afm.markets['Nigerian Stock Exchange'])
            # This returns a DataFrame
            return ngx.get_listed_companies()

        try:
            # Run blocking call in executor
            df = await loop.run_in_executor(None, _run_library_fetch)
            
            snapshots = {}
            symbols_found = []
            symbols_missing = []
            
            # Create lookup map for requested symbols
            requested_map = {s.upper(): s for s in symbols}
            
            if not df.empty:
                for _, row in df.iterrows():
                    ticker = str(row.get('Ticker', '')).upper()
                    
                    # Check if this ticker matches any requested symbol (direct or alias)
                    # For now, simple direct match on symbol/ticker
                    if ticker in requested_map:
                        requested_symbol = requested_map[ticker]
                        
                        price = NumericParser.parse_price(row.get('Price', 0))
                        change = NumericParser.parse_price(row.get('Change', 0))
                        volume = NumericParser.parse_volume(row.get('Volume', 0))
                        name = str(row.get('Name', ''))
                        
                        # Calculate open/prev_close if possible
                        # Change = Price - PrevClose => PrevClose = Price - Change
                        prev_close = price - change if price > 0 else None
                        
                        change_percent = 0.0
                        if prev_close and prev_close > 0:
                            change_percent = (change / prev_close) * 100
                        
                        snapshot = PriceSnapshot(
                            symbol=requested_symbol,
                            price=price,
                            open=price,  # Not available
                            high=price,  # Not available
                            low=price,   # Not available
                            close=price,
                            change=change,
                            change_percent=round(change_percent, 2),
                            volume=volume,
                            value=0.0,
                            timestamp=datetime.utcnow(),
                            source=self.source,
                            previous_close=prev_close
                        )
                        
                        snapshots[requested_symbol] = snapshot
                        symbols_found.append(requested_symbol)
            
            # Identify missing symbols
            for s in symbols:
                if s.upper() not in snapshots:
                    symbols_missing.append(s)
            
            fetch_time = (time.time() - start_time) * 1000
            logger.info(f"Kwayisi (Library): fetched {len(snapshots)}/{len(symbols)} symbols in {fetch_time:.0f}ms")
            
            return FetchResult(
                success=True,
                snapshots=snapshots,
                symbols_fetched=symbols_found,
                symbols_missing=symbols_missing,
                source=self.source,
                fetch_time_ms=fetch_time
            )
            
        except Exception as e:
            logger.error(f"Error in afrimarket fetch: {e}")
            raise e

    async def _fetch_via_scraping(
        self,
        symbols: List[str]
    ) -> FetchResult:
        """
        Fetch price snapshots from Kwayisi AFX via scraping (Original implementation).
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
        
        # Fetch symbols with rate limiting
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)
        
        async def fetch_single(symbol: str) -> Optional[PriceSnapshot]:
            async with semaphore:
                # Rate limiting
                await self._rate_limit()
                try:
                    return await self._fetch_stock_data(symbol)
                except Exception as e:
                    logger.debug(f"Kwayisi: Error fetching {symbol}: {e}")
                    return None
        
        # Fetch all symbols concurrently (within rate limits)
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
        
        fetch_time = (time.time() - start_time) * 1000
        
        logger.info(f"Kwayisi (Scraping): fetched {len(snapshots)}/{len(symbols)} symbols in {fetch_time:.0f}ms")
        
        return FetchResult(
            success=len(snapshots) > 0,
            snapshots=snapshots,
            symbols_fetched=symbols_found,
            symbols_missing=symbols_missing,
            source=self.source,
            fetch_time_ms=fetch_time,
            error="; ".join(errors[:5]) if errors else None
        )
    
    async def fetch_validation_snapshots(
        self,
        symbols: List[str]
    ) -> Dict[str, ValidationSnapshot]:
        """
        Fetch validation snapshots (lighter weight than full snapshots).
        
        Returns:
            Dict mapping symbol to ValidationSnapshot
        """
        result = await self.fetch_snapshot(symbols)
        
        validation_snapshots = {}
        for symbol, snapshot in result.snapshots.items():
            validation_snapshots[symbol] = ValidationSnapshot(
                symbol=symbol,
                price=snapshot.price,
                change_percent=snapshot.change_percent,
                volume=snapshot.volume,
                timestamp=snapshot.timestamp,
                source="KWAYISI",
            )
        
        return validation_snapshots
    
    async def _rate_limit(self):
        """Apply rate limiting between requests."""
        if self._last_request_time:
            elapsed = (datetime.utcnow() - self._last_request_time).total_seconds() * 1000
            if elapsed < self.MIN_REQUEST_INTERVAL_MS:
                await asyncio.sleep((self.MIN_REQUEST_INTERVAL_MS - elapsed) / 1000)
        self._last_request_time = datetime.utcnow()
        self._request_count += 1
    
    async def _fetch_stock_data(self, symbol: str) -> Optional[PriceSnapshot]:
        """Fetch data for a single stock from Kwayisi AFX."""
        # Map symbol using centralized SymbolAliasRegistry
        registry = get_symbol_alias_registry()
        
        # Kwayisi uses lowercase symbols in URLs
        mapped_symbol = symbol.lower()
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
        
        return self._parse_html(symbol, response.text)
    
    def _parse_html(self, symbol: str, html: str) -> Optional[PriceSnapshot]:
        """Parse stock data from Kwayisi HTML page."""
        try:
            # Extract current price
            # Pattern: "The current share price of ... is NGN XX.XX"
            price_match = re.search(
                r'current share price[^N]*NGN\s*([\d,]+\.?\d*)',
                html,
                re.IGNORECASE
            )
            
            if not price_match:
                # Alternative pattern: "NGN XX.XX per share"
                price_match = re.search(
                    r'at\s+([\d,]+\.?\d*)\s*NGN\s*per\s*share',
                    html,
                    re.IGNORECASE
                )
            
            if not price_match:
                logger.debug(f"Kwayisi: No price found for {symbol}")
                return None
            
            price = NumericParser.parse_price(price_match.group(1))
            if price <= 0:
                return None
            
            # Extract change percent
            # Pattern: "recording a X.X% gain/loss"
            change_match = re.search(
                r'recording\s+a\s+([\d.]+)%\s*(gain|loss)',
                html,
                re.IGNORECASE
            )
            
            change_percent = 0.0
            if change_match:
                change_percent = float(change_match.group(1))
                if change_match.group(2).lower() == 'loss':
                    change_percent = -change_percent
            
            # Extract previous close
            # Pattern: "previous closing price of XX.XX NGN"
            prev_close_match = re.search(
                r'previous\s+closing\s+price\s+of\s+([\d,]+\.?\d*)\s*NGN',
                html,
                re.IGNORECASE
            )
            
            prev_close = None
            if prev_close_match:
                prev_close = NumericParser.parse_price(prev_close_match.group(1))
            
            # Extract volume (if available)
            # Pattern: "average of XX million traded shares"
            volume_match = re.search(
                r'average\s+of\s+([\d.]+)\s*(million|thousand)?\s*traded\s*shares',
                html,
                re.IGNORECASE
            )
            
            volume = 0
            if volume_match:
                vol_num = float(volume_match.group(1))
                multiplier = volume_match.group(2)
                if multiplier and multiplier.lower() == 'million':
                    volume = int(vol_num * 1_000_000)
                elif multiplier and multiplier.lower() == 'thousand':
                    volume = int(vol_num * 1_000)
                else:
                    volume = int(vol_num)
            
            # Calculate change from previous close
            change = 0.0
            if prev_close and prev_close > 0:
                change = price - prev_close
            elif change_percent != 0:
                # Estimate change from percent
                change = price * (change_percent / 100) / (1 + change_percent / 100)
            
            return PriceSnapshot(
                symbol=symbol,
                price=price,
                open=price,  # Not available from Kwayisi
                high=price,  # Not available
                low=price,   # Not available
                close=price,
                change=round(change, 2),
                change_percent=change_percent,
                volume=volume,
                value=0.0,  # Not available
                timestamp=datetime.utcnow(),
                source=DataSource.UNKNOWN,  # Custom source
                previous_close=prev_close,
            )
            
        except Exception as e:
            logger.debug(f"Kwayisi: Error parsing {symbol}: {e}")
            return None


# Singleton instance
_provider_instance: Optional[KwayisiNGXProvider] = None


def get_kwayisi_provider() -> KwayisiNGXProvider:
    """Get singleton Kwayisi provider instance."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = KwayisiNGXProvider()
    return _provider_instance
