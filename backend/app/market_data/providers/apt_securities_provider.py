"""
Apt Securities Daily Price Provider (Tier 2)

Secondary free data source for Nigerian stock prices.
Fetches daily price data from Apt Securities broker website.

Source: https://aptsecurities.com/ngx-daily-price-list/
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import re

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

from .base import (
    MarketDataProvider,
    PriceSnapshot,
    FetchResult,
    DataSource,
    NumericParser,
)

logger = logging.getLogger(__name__)


class AptSecuritiesDailyPriceProvider(MarketDataProvider):
    """
    Tier 2 Provider: Apt Securities Daily Price List
    
    Secondary free data source for NGX stock prices.
    Useful as fallback when NGX official source is unavailable.
    
    Data characteristics:
    - Daily end-of-day prices
    - Updated after market close
    - Free public access
    - Broker-aggregated data
    """
    
    APT_URL = "https://aptsecurities.com/ngx-daily-price-list/"
    
    # Alternative URLs to try
    ALTERNATIVE_URLS = [
        "https://aptsecurities.com/market-data/",
        "https://aptsecurities.com/stock-prices/",
    ]
    
    # Column name variations
    COLUMN_MAPPINGS = {
        'symbol': ['symbol', 'ticker', 'stock', 'security', 'name'],
        'open': ['open', 'opening', 'open price'],
        'high': ['high', 'highest', 'high price'],
        'low': ['low', 'lowest', 'low price'],
        'close': ['close', 'closing', 'close price', 'current', 'price'],
        'change': ['change', 'chg', 'price change'],
        'change_percent': ['change %', '% change', 'change(%)', '% chg'],
        'volume': ['volume', 'vol', 'quantity', 'traded vol'],
        'value': ['value', 'turnover'],
    }
    
    def __init__(self, timeout: float = 2.0):
        self._timeout = timeout
        self._last_fetch: Optional[datetime] = None
    
    @property
    def name(self) -> str:
        return "Apt Securities Daily Price List"
    
    @property
    def tier(self) -> int:
        return 2
    
    @property
    def source(self) -> DataSource:
        return DataSource.APT_SECURITIES
    
    def is_available(self) -> bool:
        """Check if required libraries are installed."""
        return HTTPX_AVAILABLE and BS4_AVAILABLE
    
    async def fetch_snapshot(
        self,
        symbols: List[str]
    ) -> FetchResult:
        """
        Fetch price snapshots from Apt Securities.
        
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
                error="Required libraries not available (httpx, beautifulsoup4)",
                source=self.source
            )
        
        symbols_upper = [s.upper() for s in symbols]
        
        try:
            # Fetch data from Apt Securities
            raw_data = await self._fetch_apt_data()
            
            if not raw_data:
                return FetchResult(
                    success=False,
                    error="Failed to fetch data from Apt Securities",
                    source=self.source,
                    fetch_time_ms=(time.time() - start_time) * 1000
                )
            
            # Filter for requested symbols
            snapshots = {}
            symbols_found = []
            symbols_missing = []
            
            for symbol in symbols_upper:
                if symbol in raw_data:
                    snapshots[symbol] = raw_data[symbol]
                    symbols_found.append(symbol)
                else:
                    symbols_missing.append(symbol)
            
            self._last_fetch = datetime.utcnow()
            
            return FetchResult(
                success=True,
                snapshots=snapshots,
                symbols_fetched=symbols_found,
                symbols_missing=symbols_missing,
                source=self.source,
                fetch_time_ms=(time.time() - start_time) * 1000
            )
            
        except Exception as e:
            logger.error(f"Apt Securities provider error: {e}")
            return FetchResult(
                success=False,
                error=str(e),
                source=self.source,
                fetch_time_ms=(time.time() - start_time) * 1000
            )
    
    async def _fetch_apt_data(self) -> Dict[str, PriceSnapshot]:
        """Fetch and parse Apt Securities price data."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # Try primary URL
                urls_to_try = [self.APT_URL] + self.ALTERNATIVE_URLS
                
                for url in urls_to_try:
                    try:
                        response = await client.get(
                            url,
                            headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                                'Accept': 'text/html',
                            },
                            follow_redirects=True
                        )
                        
                        if response.status_code == 200:
                            data = self._parse_html_response(response.text)
                            if data:
                                logger.info(f"Apt Securities: fetched {len(data)} stocks from {url}")
                                return data
                    except Exception as e:
                        logger.debug(f"Apt Securities URL {url} failed: {e}")
                        continue
                
                return {}
                
        except httpx.TimeoutException:
            logger.error("Apt Securities request timed out")
            return {}
        except Exception as e:
            logger.error(f"Apt Securities fetch error: {e}")
            return {}
    
    def _parse_html_response(self, html: str) -> Dict[str, PriceSnapshot]:
        """Parse HTML response from Apt Securities."""
        snapshots = {}
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find price table - try various selectors
            table = None
            for selector in [
                {'class_': re.compile(r'price|stock|equity', re.I)},
                {'id': re.compile(r'price|stock|equity', re.I)},
                {},  # Any table
            ]:
                tables = soup.find_all('table', selector)
                for t in tables:
                    # Check if it looks like a stock price table
                    headers = t.find_all('th')
                    header_text = ' '.join(h.get_text(strip=True).lower() for h in headers)
                    if any(kw in header_text for kw in ['symbol', 'stock', 'price', 'close', 'open']):
                        table = t
                        break
                if table:
                    break
            
            if not table:
                logger.debug("No suitable price table found in Apt Securities HTML")
                return {}
            
            # Parse headers
            headers = []
            header_row = table.find('thead')
            if header_row:
                headers = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
            else:
                first_row = table.find('tr')
                if first_row:
                    headers = [cell.get_text(strip=True).lower() for cell in first_row.find_all(['th', 'td'])]
            
            # Map columns
            column_indices = self._map_columns(headers)
            
            # Parse data rows
            tbody = table.find('tbody') or table
            for row in tbody.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) < 2:
                    continue
                
                snapshot = self._parse_table_row(cells, column_indices)
                if snapshot:
                    snapshots[snapshot.symbol] = snapshot
                    
        except Exception as e:
            logger.error(f"Error parsing Apt Securities HTML: {e}")
        
        return snapshots
    
    def _map_columns(self, headers: List[str]) -> Dict[str, int]:
        """Map column names to indices."""
        indices = {}
        
        for field, variations in self.COLUMN_MAPPINGS.items():
            for i, header in enumerate(headers):
                header_clean = header.lower().strip()
                for variation in variations:
                    if variation in header_clean or header_clean in variation:
                        indices[field] = i
                        break
                if field in indices:
                    break
        
        return indices
    
    def _parse_table_row(
        self,
        cells: List,
        column_indices: Dict[str, int]
    ) -> Optional[PriceSnapshot]:
        """Parse a single table row."""
        try:
            def get_cell_value(field: str, default: str = '') -> str:
                idx = column_indices.get(field)
                if idx is not None and idx < len(cells):
                    return cells[idx].get_text(strip=True)
                return default
            
            # Get symbol
            symbol_idx = column_indices.get('symbol', 0)
            symbol = cells[symbol_idx].get_text(strip=True).upper() if symbol_idx < len(cells) else ''
            
            # Clean symbol (remove any extra text)
            symbol = re.sub(r'\s+.*$', '', symbol)  # Remove anything after whitespace
            symbol = re.sub(r'[^A-Z0-9]', '', symbol)  # Keep only alphanumeric
            
            if not symbol or len(symbol) > 15 or len(symbol) < 2:
                return None
            
            close = NumericParser.parse_price(get_cell_value('close'))
            if close <= 0:
                return None
            
            return PriceSnapshot(
                symbol=symbol,
                price=close,
                open=NumericParser.parse_price(get_cell_value('open'), close),
                high=NumericParser.parse_price(get_cell_value('high'), close),
                low=NumericParser.parse_price(get_cell_value('low'), close),
                close=close,
                change=NumericParser.parse_price(get_cell_value('change'), 0.0),
                change_percent=NumericParser.parse_percent(get_cell_value('change_percent'), 0.0),
                volume=NumericParser.parse_volume(get_cell_value('volume')),
                value=NumericParser.parse_value(get_cell_value('value')),
                timestamp=datetime.utcnow(),
                source=DataSource.APT_SECURITIES,
            )
            
        except Exception as e:
            logger.debug(f"Error parsing Apt Securities row: {e}")
            return None
