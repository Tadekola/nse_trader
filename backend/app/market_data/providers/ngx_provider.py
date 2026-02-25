"""
NGX Official Equities Price List Provider (Tier 1)

Fetches real market data from the Nigerian Exchange Group official website.
Data is delayed (typically 15-20 minutes) but represents actual market prices.

Source: https://ngxgroup.com/exchange/data/equities-price-list/
"""

import logging
import asyncio
from datetime import datetime, timezone
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

from app.core.http import http_fetch

from .base import (
    MarketDataProvider,
    PriceSnapshot,
    FetchResult,
    DataSource,
    NumericParser,
)

logger = logging.getLogger(__name__)


class NgxEquitiesPriceListProvider(MarketDataProvider):
    """
    Tier 1 Provider: NGX Official Equities Price List
    
    Fetches delayed real market data from the official NGX website.
    This is the most authoritative free data source available.
    
    Data characteristics:
    - Delayed 15-20 minutes during trading hours
    - Updated throughout trading day
    - Includes all listed equities
    - Official NGX source
    """
    
    # NGX data endpoints
    NGX_PRICE_LIST_URL = "https://ngxgroup.com/exchange/data/equities-price-list/"
    NGX_API_URL = "https://ngxgroup.com/exchange/data/equities-price-list/getpricedata"
    
    # Column name variations (NGX sometimes changes column headers)
    COLUMN_MAPPINGS = {
        'symbol': ['symbol', 'ticker', 'stock', 'code', 'security'],
        'open': ['open', 'opening', 'open price', 'opening price'],
        'high': ['high', 'highest', 'high price', 'day high'],
        'low': ['low', 'lowest', 'low price', 'day low'],
        'close': ['close', 'closing', 'close price', 'closing price', 'current', 'last'],
        'change': ['change', 'chg', 'price change', 'change (n)'],
        'change_percent': ['change %', '% change', 'change(%)', 'pct change', '% chg'],
        'volume': ['volume', 'vol', 'quantity', 'traded volume', 'deals volume'],
        'value': ['value', 'turnover', 'traded value', 'deals value'],
        'trades': ['trades', 'deals', 'no. of deals', 'number of deals'],
        'previous_close': ['previous', 'prev', 'prev close', 'previous close', 'ref price'],
    }
    
    def __init__(self, timeout: float = 15.0):
        self._timeout = timeout
        self._last_fetch: Optional[datetime] = None
        self._cached_data: Dict[str, PriceSnapshot] = {}
    
    @property
    def name(self) -> str:
        return "NGX Official Equities Price List"
    
    @property
    def tier(self) -> int:
        return 1
    
    @property
    def source(self) -> DataSource:
        return DataSource.NGX_OFFICIAL
    
    def is_available(self) -> bool:
        """Check if required libraries are installed."""
        return HTTPX_AVAILABLE and BS4_AVAILABLE
    
    async def fetch_snapshot(
        self,
        symbols: List[str]
    ) -> FetchResult:
        """
        Fetch price snapshots from NGX official source.
        
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
            # Fetch data from NGX
            raw_data = await self._fetch_ngx_data()
            
            if not raw_data:
                return FetchResult(
                    success=False,
                    error="Failed to fetch data from NGX",
                    source=self.source,
                    fetch_time_ms=(time.time() - start_time) * 1000
                )
            
            # Parse and filter for requested symbols
            snapshots = {}
            symbols_found = []
            symbols_missing = []
            
            for symbol in symbols_upper:
                if symbol in raw_data:
                    snapshots[symbol] = raw_data[symbol]
                    symbols_found.append(symbol)
                else:
                    symbols_missing.append(symbol)
            
            self._last_fetch = datetime.now(timezone.utc)
            
            return FetchResult(
                success=True,
                snapshots=snapshots,
                symbols_fetched=symbols_found,
                symbols_missing=symbols_missing,
                source=self.source,
                fetch_time_ms=(time.time() - start_time) * 1000
            )
            
        except Exception as e:
            logger.error(f"NGX provider error: {e}")
            return FetchResult(
                success=False,
                error=str(e),
                source=self.source,
                fetch_time_ms=(time.time() - start_time) * 1000
            )
    
    async def _fetch_ngx_data(self) -> Dict[str, PriceSnapshot]:
        """Fetch and parse NGX price list data."""
        try:
            # Try the API endpoint first (faster, structured data)
            try:
                response = await http_fetch(
                    self.NGX_API_URL,
                    timeout=self._timeout,
                    headers={
                        'Accept': 'application/json',
                        'Referer': self.NGX_PRICE_LIST_URL,
                    },
                    raise_for_status=False,
                )
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_api_response(data)
            except Exception as e:
                logger.debug(f"NGX API failed, trying HTML: {e}")
            
            # Fallback to HTML scraping
            response = await http_fetch(
                self.NGX_PRICE_LIST_URL,
                timeout=self._timeout,
                headers={'Accept': 'text/html'},
                raise_for_status=False,
            )
            
            if response.status_code != 200:
                logger.error(f"NGX HTTP error: {response.status_code}")
                return {}
            
            return self._parse_html_response(response.text)
                
        except httpx.TimeoutException:
            logger.error("NGX request timed out")
            return {}
        except Exception as e:
            logger.error(f"NGX fetch error: {e}")
            return {}
    
    def _parse_api_response(self, data: Any) -> Dict[str, PriceSnapshot]:
        """Parse JSON API response from NGX."""
        snapshots = {}
        
        try:
            # Handle various API response formats
            records = []
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict):
                records = data.get('data', data.get('records', data.get('items', [])))
            
            for record in records:
                snapshot = self._parse_record(record)
                if snapshot:
                    snapshots[snapshot.symbol] = snapshot
                    
        except Exception as e:
            logger.error(f"Error parsing NGX API response: {e}")
        
        return snapshots
    
    def _parse_html_response(self, html: str) -> Dict[str, PriceSnapshot]:
        """Parse HTML response from NGX price list page."""
        snapshots = {}
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find the price list table
            table = soup.find('table', {'id': 'price-list-table'})
            if not table:
                # Try other common table identifiers
                table = soup.find('table', class_=re.compile(r'price|equity|stock', re.I))
            if not table:
                table = soup.find('table')
            
            if not table:
                logger.error("Could not find price table in NGX HTML")
                return {}
            
            # Parse headers
            headers = []
            header_row = table.find('thead')
            if header_row:
                headers = [th.get_text(strip=True).lower() for th in header_row.find_all('th')]
            else:
                # Try first row
                first_row = table.find('tr')
                if first_row:
                    headers = [cell.get_text(strip=True).lower() for cell in first_row.find_all(['th', 'td'])]
            
            # Map columns
            column_indices = self._map_columns(headers)
            
            # Parse data rows
            tbody = table.find('tbody') or table
            for row in tbody.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) < 3:
                    continue
                
                snapshot = self._parse_table_row(cells, column_indices)
                if snapshot:
                    snapshots[snapshot.symbol] = snapshot
                    
        except Exception as e:
            logger.error(f"Error parsing NGX HTML: {e}")
        
        return snapshots
    
    def _map_columns(self, headers: List[str]) -> Dict[str, int]:
        """Map column names to indices, handling variations."""
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
    
    def _parse_record(self, record: Dict) -> Optional[PriceSnapshot]:
        """Parse a single record from API response."""
        try:
            # Try various key names for symbol
            symbol = None
            for key in ['symbol', 'ticker', 'stock', 'SYMBOL', 'Symbol']:
                if key in record:
                    symbol = str(record[key]).strip().upper()
                    break
            
            if not symbol:
                return None
            
            # Parse price fields with fallbacks
            close = NumericParser.parse_price(
                record.get('close') or record.get('closing') or 
                record.get('current') or record.get('last') or record.get('price')
            )
            
            if close <= 0:
                return None
            
            open_price = NumericParser.parse_price(
                record.get('open') or record.get('opening'), close
            )
            high = NumericParser.parse_price(
                record.get('high') or record.get('highest'), close
            )
            low = NumericParser.parse_price(
                record.get('low') or record.get('lowest'), close
            )
            change = NumericParser.parse_price(
                record.get('change') or record.get('chg'), 0.0
            )
            change_pct = NumericParser.parse_percent(
                record.get('change_percent') or record.get('change %') or 
                record.get('pctChange') or record.get('percentChange'), 0.0
            )
            volume = NumericParser.parse_volume(
                record.get('volume') or record.get('vol') or record.get('quantity')
            )
            value = NumericParser.parse_value(
                record.get('value') or record.get('turnover')
            )
            
            return PriceSnapshot(
                symbol=symbol,
                price=close,
                open=open_price,
                high=high,
                low=low,
                close=close,
                change=change,
                change_percent=change_pct,
                volume=volume,
                value=value,
                timestamp=datetime.now(timezone.utc),
                source=DataSource.NGX_OFFICIAL,
                trades=NumericParser.parse_volume(record.get('trades') or record.get('deals')),
                previous_close=NumericParser.parse_price(record.get('previous') or record.get('prev')),
            )
            
        except Exception as e:
            logger.debug(f"Error parsing record: {e}")
            return None
    
    def _parse_table_row(
        self,
        cells: List,
        column_indices: Dict[str, int]
    ) -> Optional[PriceSnapshot]:
        """Parse a single table row from HTML."""
        try:
            def get_cell_value(field: str, default: str = '') -> str:
                idx = column_indices.get(field)
                if idx is not None and idx < len(cells):
                    return cells[idx].get_text(strip=True)
                return default
            
            # Get symbol (usually first column)
            symbol_idx = column_indices.get('symbol', 0)
            symbol = cells[symbol_idx].get_text(strip=True).upper() if symbol_idx < len(cells) else ''
            
            if not symbol or len(symbol) > 15:
                return None
            
            close = NumericParser.parse_price(get_cell_value('close'))
            if close <= 0:
                # Try to get any price
                for field in ['close', 'high', 'low', 'open']:
                    close = NumericParser.parse_price(get_cell_value(field))
                    if close > 0:
                        break
            
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
                timestamp=datetime.now(timezone.utc),
                source=DataSource.NGX_OFFICIAL,
                trades=NumericParser.parse_volume(get_cell_value('trades')),
                previous_close=NumericParser.parse_price(get_cell_value('previous_close')),
            )
            
        except Exception as e:
            logger.debug(f"Error parsing table row: {e}")
            return None
