"""
Market Data Service v2 for NSE Trader.

Production-grade 3-tier data sourcing:
- Tier 1: NGX Official Equities Price List
- Tier 2: Apt Securities Daily Price List
- Tier 3: Simulated fallback (last resort)

This replaces the TradingView-dependent implementation.
"""

import logging
import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from app.data.sources.ngx_stocks import NGXStockRegistry, Sector
from app.market_data.providers import (
    ProviderChain,
    NgxEquitiesPriceListProvider,
    AptSecuritiesDailyPriceProvider,
    SimulatedProvider,
    PriceSnapshot,
    DataSource,
)
from app.market_data.providers.chain import ChainFetchResult

logger = logging.getLogger(__name__)


@dataclass
class MarketDataResult:
    """Result from market data fetch."""
    success: bool
    data: Optional[Any]
    source: str
    timestamp: datetime
    cached: bool = False
    error: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


class MarketDataServiceV2:
    """
    Unified market data service with 3-tier provider chain.
    
    Features:
    - NGX Official data (Tier 1)
    - Apt Securities fallback (Tier 2)
    - Simulated fallback (Tier 3 - last resort)
    - Transparent source tracking
    - Caching with TTL
    """
    
    def __init__(self, cache_ttl: int = 120):
        """
        Initialize the market data service.
        
        Args:
            cache_ttl: Cache TTL in seconds (default 2 minutes)
        """
        self.registry = NGXStockRegistry()
        
        # Build registry data for simulated provider
        registry_data = {}
        for stock in self.registry.get_all_stocks():
            registry_data[stock['symbol']] = stock
        
        # Initialize providers
        self._ngx_provider = NgxEquitiesPriceListProvider()
        self._apt_provider = AptSecuritiesDailyPriceProvider()
        self._simulated_provider = SimulatedProvider(registry_data)
        
        # Create provider chain
        self._provider_chain = ProviderChain(
            providers=[
                self._ngx_provider,
                self._apt_provider,
                self._simulated_provider,
            ],
            cache_ttl=cache_ttl,
            enable_cache=True,
        )
        
        # Internal cache for enriched data
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        self._cache_ttl = timedelta(seconds=cache_ttl)
        
        # Last fetch result metadata
        self._last_fetch_meta: Optional[Dict] = None
    
    async def get_all_stocks_async(self) -> MarketDataResult:
        """
        Get data for all stocks in the universe.
        
        Returns enriched stock data with source breakdown metadata.
        """
        # Get all symbols from registry
        symbols = self.registry.get_symbols()
        
        # Fetch from provider chain
        result = await self._provider_chain.fetch_snapshot(symbols)
        
        if not result.success:
            return MarketDataResult(
                success=False,
                data=None,
                source="none",
                timestamp=datetime.utcnow(),
                error="Failed to fetch market data",
                meta=result.to_meta_dict()
            )
        
        # Enrich snapshots with registry data
        enriched_stocks = []
        for symbol in symbols:
            snapshot = result.snapshots.get(symbol)
            registry_info = self.registry.get_stock(symbol)
            
            if snapshot and registry_info:
                enriched = self._enrich_snapshot(snapshot, registry_info)
                enriched_stocks.append(enriched)
        
        # Store metadata for API access
        self._last_fetch_meta = result.to_meta_dict()
        
        return MarketDataResult(
            success=True,
            data=enriched_stocks,
            source=self._determine_primary_source(result),
            timestamp=datetime.utcnow(),
            meta=result.to_meta_dict()
        )
    
    def get_all_stocks(self) -> MarketDataResult:
        """Synchronous wrapper for get_all_stocks_async."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, create a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.get_all_stocks_async())
                    return future.result()
            else:
                return loop.run_until_complete(self.get_all_stocks_async())
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.get_all_stocks_async())
    
    async def get_stock_async(self, symbol: str) -> MarketDataResult:
        """Get data for a specific stock."""
        symbol = symbol.upper()
        
        # Fetch from provider chain
        result = await self._provider_chain.fetch_snapshot([symbol])
        
        snapshot = result.snapshots.get(symbol)
        if not snapshot:
            return MarketDataResult(
                success=False,
                data=None,
                source="none",
                timestamp=datetime.utcnow(),
                error=f"Stock {symbol} not found",
                meta=result.to_meta_dict()
            )
        
        # Enrich with registry data
        registry_info = self.registry.get_stock(symbol)
        enriched = self._enrich_snapshot(snapshot, registry_info) if registry_info else snapshot.to_dict()
        
        return MarketDataResult(
            success=True,
            data=enriched,
            source=snapshot.source.value,
            timestamp=datetime.utcnow(),
            meta=result.to_meta_dict()
        )
    
    def get_stock(self, symbol: str) -> MarketDataResult:
        """Synchronous wrapper for get_stock_async."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.get_stock_async(symbol))
                    return future.result()
            else:
                return loop.run_until_complete(self.get_stock_async(symbol))
        except RuntimeError:
            return asyncio.run(self.get_stock_async(symbol))
    
    def get_stocks_by_sector(self, sector: str) -> MarketDataResult:
        """Get stocks filtered by sector."""
        try:
            sector_enum = Sector(sector)
            registry_stocks = self.registry.get_by_sector(sector_enum)
            symbols = [s['symbol'] for s in registry_stocks]
            
            result = asyncio.run(self._provider_chain.fetch_snapshot(symbols))
            
            enriched_stocks = []
            for stock in registry_stocks:
                snapshot = result.snapshots.get(stock['symbol'])
                if snapshot:
                    enriched = self._enrich_snapshot(snapshot, stock)
                    enriched_stocks.append(enriched)
            
            return MarketDataResult(
                success=True,
                data=enriched_stocks,
                source=self._determine_primary_source(result),
                timestamp=datetime.utcnow(),
                meta=result.to_meta_dict()
            )
        except ValueError:
            return MarketDataResult(
                success=False,
                data=None,
                source="none",
                timestamp=datetime.utcnow(),
                error=f"Invalid sector: {sector}"
            )
    
    def get_high_liquidity_stocks(self) -> MarketDataResult:
        """Get only high liquidity stocks."""
        registry_stocks = self.registry.get_high_liquidity_stocks()
        symbols = [s['symbol'] for s in registry_stocks]
        
        result = asyncio.run(self._provider_chain.fetch_snapshot(symbols))
        
        enriched_stocks = []
        for stock in registry_stocks:
            snapshot = result.snapshots.get(stock['symbol'])
            if snapshot:
                enriched = self._enrich_snapshot(snapshot, stock)
                enriched_stocks.append(enriched)
        
        return MarketDataResult(
            success=True,
            data=enriched_stocks,
            source=self._determine_primary_source(result),
            timestamp=datetime.utcnow(),
            meta=result.to_meta_dict()
        )
    
    def get_market_summary(self) -> MarketDataResult:
        """Get overall market summary."""
        all_stocks_result = self.get_all_stocks()
        stocks = all_stocks_result.data if all_stocks_result.success else []
        
        # Calculate breadth
        advancing = sum(1 for s in stocks if s.get('change_percent', 0) > 0)
        declining = sum(1 for s in stocks if s.get('change_percent', 0) < 0)
        unchanged = len(stocks) - advancing - declining
        
        # Calculate totals
        total_volume = sum(s.get('volume', 0) for s in stocks)
        total_value = sum(s.get('value', 0) for s in stocks)
        
        summary = {
            'breadth': {
                'advancing': advancing,
                'declining': declining,
                'unchanged': unchanged,
                'ratio': advancing / (advancing + declining) if (advancing + declining) > 0 else 0.5
            },
            'volume': {
                'total_volume': total_volume,
                'total_value': total_value
            },
            'stock_count': len(stocks),
            'timestamp': datetime.utcnow().isoformat(),
            'data_meta': all_stocks_result.meta
        }
        
        return MarketDataResult(
            success=True,
            data=summary,
            source=all_stocks_result.source,
            timestamp=datetime.utcnow(),
            meta=all_stocks_result.meta
        )
    
    def search_stocks(self, query: str) -> MarketDataResult:
        """Search stocks by symbol or name."""
        results = self.registry.search(query)
        return MarketDataResult(
            success=True,
            data=results,
            source="Registry",
            timestamp=datetime.utcnow()
        )
    
    def get_sectors(self) -> MarketDataResult:
        """Get list of sectors."""
        sectors = self.registry.get_sectors()
        return MarketDataResult(
            success=True,
            data=sectors,
            source="Registry",
            timestamp=datetime.utcnow()
        )
    
    def get_technical_indicators(self, symbol: str) -> MarketDataResult:
        """
        Get technical indicators for a stock.
        
        Note: Without TradingView, we compute basic indicators locally.
        """
        # For now, return basic data - full indicators would require historical data
        result = self.get_stock(symbol)
        if not result.success:
            return result
        
        stock = result.data
        indicators = {
            'price': stock.get('price', 0),
            'change': stock.get('change', 0),
            'change_percent': stock.get('change_percent', 0),
            'volume': stock.get('volume', 0),
            'high': stock.get('high', 0),
            'low': stock.get('low', 0),
            'open': stock.get('open', 0),
            'close': stock.get('close', 0),
            'note': 'Full technical indicators require historical data integration'
        }
        
        return MarketDataResult(
            success=True,
            data=indicators,
            source=result.source,
            timestamp=datetime.utcnow(),
            meta=result.meta
        )
    
    def get_provider_status(self) -> List[Dict[str, Any]]:
        """Get status of all data providers."""
        return self._provider_chain.get_provider_status()
    
    def get_last_fetch_meta(self) -> Optional[Dict]:
        """Get metadata from the last fetch operation."""
        return self._last_fetch_meta
    
    def clear_cache(self):
        """Clear all cached data."""
        self._provider_chain.clear_cache()
        self._cache.clear()
    
    def _enrich_snapshot(
        self,
        snapshot: PriceSnapshot,
        registry_info: Dict
    ) -> Dict[str, Any]:
        """Enrich price snapshot with registry data."""
        enriched = snapshot.to_dict()
        
        # Add registry fields
        enriched['name'] = registry_info.get('name', snapshot.symbol)
        enriched['sector'] = registry_info.get('sector', {})
        if hasattr(enriched['sector'], 'value'):
            enriched['sector'] = enriched['sector'].value
        enriched['liquidity_tier'] = registry_info.get('liquidity_tier', 'unknown')
        enriched['market_cap_billions'] = registry_info.get('market_cap_billions')
        enriched['shares_outstanding'] = registry_info.get('shares_outstanding')
        enriched['is_active'] = registry_info.get('is_active', True)
        
        # Calculate market cap if not present
        if enriched.get('market_cap_billions') and not enriched.get('market_cap'):
            enriched['market_cap'] = enriched['market_cap_billions'] * 1e9
        
        return enriched
    
    def _determine_primary_source(self, result: ChainFetchResult) -> str:
        """Determine the primary data source from a chain result."""
        breakdown = result.source_breakdown
        if breakdown.ngx_official > 0:
            return "ngx_official"
        elif breakdown.apt_securities > 0:
            return "apt_securities"
        elif breakdown.simulated > 0:
            return "simulated"
        return "unknown"


# Create singleton instance
_market_data_service: Optional[MarketDataServiceV2] = None


def get_market_data_service() -> MarketDataServiceV2:
    """Get or create the market data service singleton."""
    global _market_data_service
    if _market_data_service is None:
        _market_data_service = MarketDataServiceV2()
    return _market_data_service
