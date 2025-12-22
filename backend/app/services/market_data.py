"""
Market Data Service for NSE Trader.

Provides unified access to market data from multiple sources
with caching, validation, and fallback handling.
"""
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import pandas as pd

from app.data.sources.tradingview import TradingViewDataSource, StockData
from app.data.sources.ngx_stocks import NGXStockRegistry, Sector
from app.indicators.volume import LiquidityScoreIndicator

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


class MarketDataService:
    """
    Unified market data service.
    
    Features:
    - Multiple data source support
    - Automatic fallback
    - Caching with TTL
    - Data validation
    - Liquidity enrichment
    """
    
    def __init__(self):
        self.tradingview = TradingViewDataSource()
        self.registry = NGXStockRegistry()
        self.liquidity_indicator = LiquidityScoreIndicator()
        
        # Cache
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        self._cache_ttl = timedelta(minutes=5)
    
    def get_stock(self, symbol: str) -> MarketDataResult:
        """Get complete stock data."""
        symbol = symbol.upper()
        
        # Check cache
        cached = self._get_from_cache(f"stock:{symbol}")
        if cached:
            return MarketDataResult(
                success=True,
                data=cached,
                source="cache",
                timestamp=datetime.utcnow(),
                cached=True
            )
        
        # Get from TradingView
        tv_data = self.tradingview.get_stock_data(symbol)
        if tv_data:
            # Enrich with registry data
            registry_data = self.registry.get_stock(symbol)
            enriched = self._enrich_stock_data(tv_data, registry_data)
            
            # Cache result
            self._set_cache(f"stock:{symbol}", enriched)
            
            return MarketDataResult(
                success=True,
                data=enriched,
                source="TradingView",
                timestamp=datetime.utcnow()
            )
        
        # Fallback to registry only - add simulated price fields
        registry_data = self.registry.get_stock(symbol)
        if registry_data:
            # Use simulated prices based on market cap
            simulated = self._get_simulated_price(symbol, registry_data)
            enriched_registry = {
                **registry_data,
                **simulated,
                'source': 'Simulated',
                'timestamp': datetime.utcnow().isoformat()
            }
            return MarketDataResult(
                success=True,
                data=enriched_registry,
                source="Simulated",
                timestamp=datetime.utcnow()
            )
        
        return MarketDataResult(
            success=False,
            data=None,
            source="none",
            timestamp=datetime.utcnow(),
            error=f"Stock {symbol} not found"
        )
    
    def get_all_stocks(self) -> MarketDataResult:
        """Get data for all stocks."""
        # Check cache
        cached = self._get_from_cache("all_stocks")
        if cached:
            return MarketDataResult(
                success=True,
                data=cached,
                source="cache",
                timestamp=datetime.utcnow(),
                cached=True
            )
        
        # Get all symbols
        symbols = self.registry.get_symbols()
        
        # Fetch data for each
        stocks = []
        for symbol in symbols:
            result = self.get_stock(symbol)
            if result.success:
                stocks.append(result.data)
        
        # Cache result
        self._set_cache("all_stocks", stocks, ttl=timedelta(minutes=2))
        
        return MarketDataResult(
            success=True,
            data=stocks,
            source="TradingView+Registry",
            timestamp=datetime.utcnow()
        )
    
    def get_stocks_by_sector(self, sector: str) -> MarketDataResult:
        """Get stocks filtered by sector."""
        try:
            sector_enum = Sector(sector)
            registry_stocks = self.registry.get_by_sector(sector_enum)
            
            stocks = []
            for reg_stock in registry_stocks:
                result = self.get_stock(reg_stock['symbol'])
                if result.success:
                    stocks.append(result.data)
            
            return MarketDataResult(
                success=True,
                data=stocks,
                source="TradingView+Registry",
                timestamp=datetime.utcnow()
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
        
        stocks = []
        for reg_stock in registry_stocks:
            result = self.get_stock(reg_stock['symbol'])
            if result.success:
                stocks.append(result.data)
        
        return MarketDataResult(
            success=True,
            data=stocks,
            source="TradingView+Registry",
            timestamp=datetime.utcnow()
        )
    
    def get_technical_indicators(self, symbol: str) -> MarketDataResult:
        """Get technical indicators for a stock."""
        symbol = symbol.upper()
        
        indicators = self.tradingview.get_technical_indicators(symbol)
        if indicators:
            return MarketDataResult(
                success=True,
                data=indicators,
                source="TradingView",
                timestamp=datetime.utcnow()
            )
        
        return MarketDataResult(
            success=False,
            data=None,
            source="none",
            timestamp=datetime.utcnow(),
            error="Failed to fetch indicators"
        )
    
    def get_market_summary(self) -> MarketDataResult:
        """Get overall market summary."""
        # Check cache
        cached = self._get_from_cache("market_summary")
        if cached:
            return MarketDataResult(
                success=True,
                data=cached,
                source="cache",
                timestamp=datetime.utcnow(),
                cached=True
            )
        
        # Get ASI data
        asi_data = self.tradingview.get_stock_data("NGX30")
        
        # Get all stocks for breadth calculation
        all_stocks_result = self.get_all_stocks()
        stocks = all_stocks_result.data if all_stocks_result.success else []
        
        # Calculate breadth
        advancing = sum(1 for s in stocks if s.get('change_percent', 0) > 0)
        declining = sum(1 for s in stocks if s.get('change_percent', 0) < 0)
        unchanged = len(stocks) - advancing - declining
        
        # Calculate totals
        total_volume = sum(s.get('volume', 0) for s in stocks)
        total_value = sum(s.get('volume', 0) * s.get('price', 0) for s in stocks)
        
        summary = {
            'asi': {
                'value': asi_data.price if asi_data else 0,
                'change': asi_data.change if asi_data else 0,
                'change_percent': asi_data.change_percent if asi_data else 0
            },
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
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Cache result
        self._set_cache("market_summary", summary, ttl=timedelta(minutes=1))
        
        return MarketDataResult(
            success=True,
            data=summary,
            source="TradingView+Calculated",
            timestamp=datetime.utcnow()
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
    
    def _enrich_stock_data(
        self,
        tv_data: StockData,
        registry_data: Optional[Dict]
    ) -> Dict[str, Any]:
        """Enrich TradingView data with registry data."""
        enriched = {
            'symbol': tv_data.symbol,
            'name': tv_data.name,
            'price': tv_data.price,
            'open': tv_data.open,
            'high': tv_data.high,
            'low': tv_data.low,
            'close': tv_data.close,
            'change': tv_data.change,
            'change_percent': tv_data.change_percent,
            'volume': tv_data.volume,
            'market_cap': tv_data.market_cap,
            'pe_ratio': tv_data.pe_ratio,
            'eps': tv_data.eps,
            'dividend_yield': tv_data.dividend_yield,
            'recommendation': tv_data.recommendation,
            'buy_signals': tv_data.buy_signals,
            'sell_signals': tv_data.sell_signals,
            'neutral_signals': tv_data.neutral_signals,
            'source': 'TradingView',
            'timestamp': tv_data.timestamp.isoformat()
        }
        
        if registry_data:
            enriched['sector'] = registry_data.get('sector', {})
            if hasattr(enriched['sector'], 'value'):
                enriched['sector'] = enriched['sector'].value
            enriched['liquidity_tier'] = registry_data.get('liquidity_tier', 'unknown')
            enriched['shares_outstanding'] = registry_data.get('shares_outstanding')
            
            # Use registry market cap if TradingView doesn't have it
            if not enriched['market_cap'] and registry_data.get('market_cap_billions'):
                enriched['market_cap'] = registry_data['market_cap_billions'] * 1e9
        
        return enriched
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.utcnow() - timestamp < self._cache_ttl:
                return value
            del self._cache[key]
        return None
    
    def _set_cache(
        self,
        key: str,
        value: Any,
        ttl: Optional[timedelta] = None
    ):
        """Set value in cache."""
        self._cache[key] = (value, datetime.utcnow())
    
    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()
    
    def _get_simulated_price(self, symbol: str, registry_data: Dict) -> Dict[str, Any]:
        """
        Generate realistic simulated prices based on market cap and sector.
        
        This provides fallback data when TradingView is rate-limited.
        Prices are derived from market cap / shares outstanding.
        """
        import random
        import hashlib
        
        # Use symbol hash for consistent "random" values per stock
        seed = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)
        random.seed(seed + datetime.utcnow().hour)  # Changes hourly
        
        # Calculate base price from market cap
        market_cap = registry_data.get('market_cap_billions', 100) * 1e9
        shares = registry_data.get('shares_outstanding', 1e9)
        base_price = market_cap / shares if shares > 0 else 10.0
        
        # Add realistic variation (-3% to +3%)
        variation = random.uniform(-0.03, 0.03)
        price = round(base_price * (1 + variation), 2)
        
        # Generate OHLC data
        daily_range = price * random.uniform(0.01, 0.04)  # 1-4% daily range
        open_price = round(price + random.uniform(-daily_range/2, daily_range/2), 2)
        high = round(max(price, open_price) + random.uniform(0, daily_range/2), 2)
        low = round(min(price, open_price) - random.uniform(0, daily_range/2), 2)
        
        change = round(price - open_price, 2)
        change_percent = round((change / open_price) * 100, 2) if open_price > 0 else 0.0
        
        # Volume based on liquidity tier
        liquidity = registry_data.get('liquidity_tier', 'medium')
        base_volume = {
            'high': random.randint(5_000_000, 50_000_000),
            'medium': random.randint(500_000, 5_000_000),
            'low': random.randint(50_000, 500_000),
            'very_low': random.randint(10_000, 50_000)
        }.get(liquidity, 500_000)
        
        return {
            'price': price,
            'open': open_price,
            'high': high,
            'low': low,
            'close': price,
            'change': change,
            'change_percent': change_percent,
            'volume': base_volume
        }
