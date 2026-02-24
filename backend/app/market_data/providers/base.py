"""
Base interfaces for Market Data Providers.

Defines the unified interface that all data providers must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


class DataSource(str, Enum):
    """Data source identifiers."""
    NGX_OFFICIAL = "ngx_official"
    NGX_OFFICIAL_LIST_PDF = "ngx_official_list_pdf"
    APT_SECURITIES = "apt_securities"
    KWAYISI = "kwayisi"
    SIMULATED = "simulated"
    UNKNOWN = "unknown"


@dataclass
class PriceSnapshot:
    """
    Unified price snapshot for a single stock.
    
    All providers must normalize their data to this format.
    """
    symbol: str
    price: float
    open: float
    high: float
    low: float
    close: float
    change: float
    change_percent: float
    volume: int
    value: float  # Trading value in Naira
    timestamp: datetime
    source: DataSource
    
    # Optional fields
    trades: Optional[int] = None
    previous_close: Optional[float] = None
    
    # Simulation disclosure fields (populated when source == SIMULATED)
    is_simulated: bool = False
    simulated_reason: Optional[str] = None
    simulated_inputs: Optional[Dict[str, Any]] = None  # e.g., {"market_cap": X, "shares_outstanding": Y}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        result = {
            'symbol': self.symbol,
            'price': self.price,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'change': self.change,
            'change_percent': self.change_percent,
            'volume': self.volume,
            'value': self.value,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source.value,
            'trades': self.trades,
            'previous_close': self.previous_close,
            'is_simulated': self.is_simulated,
        }
        
        # Include simulation details only when simulated
        if self.is_simulated:
            result['simulated_reason'] = self.simulated_reason
            result['simulated_inputs'] = self.simulated_inputs
            result['data_source'] = "SIMULATED"
            result['simulation_warning'] = "This price is NOT real market data. It is derived from static registry data for demonstration purposes only."
        
        return result


@dataclass
class FetchResult:
    """Result of a provider fetch operation."""
    success: bool
    snapshots: Dict[str, PriceSnapshot] = field(default_factory=dict)
    symbols_fetched: List[str] = field(default_factory=list)
    symbols_missing: List[str] = field(default_factory=list)
    error: Optional[str] = None
    fetch_time_ms: float = 0.0
    source: DataSource = DataSource.UNKNOWN


class MarketDataProvider(ABC):
    """
    Abstract base class for market data providers.
    
    All providers must implement fetch_snapshot() to return
    normalized PriceSnapshot objects.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        pass
    
    @property
    @abstractmethod
    def tier(self) -> int:
        """Provider tier (1=primary, 2=secondary, 3=fallback)."""
        pass
    
    @property
    @abstractmethod
    def source(self) -> DataSource:
        """Data source identifier."""
        pass
    
    @abstractmethod
    async def fetch_snapshot(
        self,
        symbols: List[str]
    ) -> FetchResult:
        """
        Fetch price snapshots for requested symbols.
        
        Args:
            symbols: List of stock symbols to fetch
            
        Returns:
            FetchResult with snapshots for successfully fetched symbols
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is currently available."""
        pass


class NumericParser:
    """
    Utility class for robust numeric parsing.
    
    Handles Nigerian-style formatting:
    - Currency symbols (₦, NGN)
    - Thousand separators (commas)
    - Percentage signs
    - Blank/missing values
    """
    
    @staticmethod
    def parse_price(value: Any, default: float = 0.0) -> float:
        """Parse a price value, handling various formats."""
        if value is None:
            return default
        
        if isinstance(value, (int, float)):
            return float(value)
        
        text = str(value).strip()
        if not text or text in ('-', '--', 'N/A', 'n/a', ''):
            return default
        
        # Remove currency symbols and whitespace
        text = text.replace('₦', '').replace('NGN', '').replace('N', '')
        text = text.replace(',', '').replace(' ', '').strip()
        
        try:
            return float(text)
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def parse_percent(value: Any, default: float = 0.0) -> float:
        """Parse a percentage value."""
        if value is None:
            return default
        
        if isinstance(value, (int, float)):
            return float(value)
        
        text = str(value).strip()
        if not text or text in ('-', '--', 'N/A', 'n/a', ''):
            return default
        
        # Remove percentage sign
        text = text.replace('%', '').replace(',', '').strip()
        
        # Handle parentheses for negative (accounting format)
        if text.startswith('(') and text.endswith(')'):
            text = '-' + text[1:-1]
        
        try:
            return float(text)
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def parse_volume(value: Any, default: int = 0) -> int:
        """Parse a volume value (integer)."""
        if value is None:
            return default
        
        if isinstance(value, int):
            return value
        
        if isinstance(value, float):
            return int(value)
        
        text = str(value).strip()
        if not text or text in ('-', '--', 'N/A', 'n/a', ''):
            return default
        
        # Remove commas and whitespace
        text = text.replace(',', '').replace(' ', '').strip()
        
        # Handle K/M/B suffixes
        multiplier = 1
        if text.endswith('K') or text.endswith('k'):
            multiplier = 1000
            text = text[:-1]
        elif text.endswith('M') or text.endswith('m'):
            multiplier = 1_000_000
            text = text[:-1]
        elif text.endswith('B') or text.endswith('b'):
            multiplier = 1_000_000_000
            text = text[:-1]
        
        try:
            return int(float(text) * multiplier)
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def parse_value(value: Any, default: float = 0.0) -> float:
        """Parse a trading value (typically in millions)."""
        return NumericParser.parse_price(value, default)
