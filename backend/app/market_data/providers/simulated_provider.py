"""
Simulated Data Provider (Tier 3)

Last-resort fallback that generates realistic simulated prices
based on market cap and historical patterns.

This should ONLY be used when Tier 1 and Tier 2 sources fail.
Data is clearly marked as simulated to warn users.
"""

import logging
import hashlib
import random
from datetime import datetime
from typing import Dict, List, Optional

from .base import (
    MarketDataProvider,
    PriceSnapshot,
    FetchResult,
    DataSource,
)

logger = logging.getLogger(__name__)


class SimulatedProvider(MarketDataProvider):
    """
    Tier 3 Provider: Simulated Fallback
    
    Generates realistic simulated prices when real data sources fail.
    Prices are derived from market cap / shares outstanding.
    
    WARNING: This data is NOT real. It should only be used for:
    - Development/testing
    - UI demonstration
    - Temporary fallback during outages
    
    Users MUST be warned when simulated data is being displayed.
    """
    
    def __init__(self, registry_data: Dict[str, Dict] = None):
        """
        Initialize with stock registry data.
        
        Args:
            registry_data: Dict mapping symbol -> {market_cap_billions, shares_outstanding, liquidity_tier}
        """
        self._registry = registry_data or {}
    
    @property
    def name(self) -> str:
        return "Simulated Fallback"
    
    @property
    def tier(self) -> int:
        return 3
    
    @property
    def source(self) -> DataSource:
        return DataSource.SIMULATED
    
    def is_available(self) -> bool:
        """Simulated provider is always available."""
        return True
    
    def set_registry_data(self, registry_data: Dict[str, Dict]):
        """Update registry data for simulation."""
        self._registry = registry_data
    
    async def fetch_snapshot(
        self,
        symbols: List[str]
    ) -> FetchResult:
        """
        Generate simulated price snapshots.
        
        Args:
            symbols: List of stock symbols to simulate
            
        Returns:
            FetchResult with simulated snapshots
        """
        import time
        start_time = time.time()
        
        snapshots = {}
        symbols_found = []
        symbols_missing = []
        
        for symbol in symbols:
            symbol_upper = symbol.upper()
            
            # Check if we have registry data for this symbol
            registry_info = self._registry.get(symbol_upper)
            
            if registry_info:
                snapshot = self._generate_snapshot(symbol_upper, registry_info)
                snapshots[symbol_upper] = snapshot
                symbols_found.append(symbol_upper)
            else:
                # Can't simulate without market cap data
                symbols_missing.append(symbol_upper)
                logger.debug(f"No registry data for {symbol_upper}, cannot simulate")
        
        return FetchResult(
            success=len(snapshots) > 0,
            snapshots=snapshots,
            symbols_fetched=symbols_found,
            symbols_missing=symbols_missing,
            source=self.source,
            fetch_time_ms=(time.time() - start_time) * 1000
        )
    
    def _generate_snapshot(
        self,
        symbol: str,
        registry_info: Dict
    ) -> PriceSnapshot:
        """
        Generate a realistic simulated price snapshot.
        
        Uses deterministic randomness based on symbol + time
        to ensure consistent prices within the same hour.
        """
        # Use symbol hash for consistent "random" values per stock
        seed = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)
        # Changes hourly to simulate market movement
        random.seed(seed + datetime.utcnow().hour + datetime.utcnow().day * 24)
        
        # Calculate base price from market cap
        market_cap = registry_info.get('market_cap_billions', 100) * 1e9
        shares = registry_info.get('shares_outstanding', 1e9)
        base_price = market_cap / shares if shares > 0 else 10.0
        
        # Add realistic daily variation (-3% to +3%)
        variation = random.uniform(-0.03, 0.03)
        price = round(base_price * (1 + variation), 2)
        
        # Generate OHLC data with realistic intraday range
        daily_range = price * random.uniform(0.01, 0.04)  # 1-4% daily range
        open_price = round(price + random.uniform(-daily_range/2, daily_range/2), 2)
        high = round(max(price, open_price) + random.uniform(0, daily_range/2), 2)
        low = round(min(price, open_price) - random.uniform(0, daily_range/2), 2)
        
        # Ensure OHLC consistency
        high = max(high, open_price, price)
        low = min(low, open_price, price)
        
        change = round(price - open_price, 2)
        change_percent = round((change / open_price) * 100, 2) if open_price > 0 else 0.0
        
        # Volume based on liquidity tier
        liquidity = registry_info.get('liquidity_tier', 'medium')
        volume_ranges = {
            'high': (5_000_000, 50_000_000),
            'medium': (500_000, 5_000_000),
            'low': (50_000, 500_000),
            'very_low': (10_000, 50_000)
        }
        vol_min, vol_max = volume_ranges.get(liquidity, (500_000, 5_000_000))
        volume = random.randint(vol_min, vol_max)
        
        # Calculate trading value
        value = volume * price
        
        return PriceSnapshot(
            symbol=symbol,
            price=price,
            open=open_price,
            high=high,
            low=low,
            close=price,
            change=change,
            change_percent=change_percent,
            volume=volume,
            value=value,
            timestamp=datetime.utcnow(),
            source=DataSource.SIMULATED,
            previous_close=open_price,
        )
