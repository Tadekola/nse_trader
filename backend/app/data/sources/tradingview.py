"""
TradingView Data Source for NSE Trader.

Fetches real market data from TradingView for Nigerian stocks.
Replaces all simulated/random data with actual market information.
"""
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import pandas as pd

try:
    from tradingview_ta import TA_Handler, Interval
    TRADINGVIEW_AVAILABLE = True
except ImportError:
    TRADINGVIEW_AVAILABLE = False
    TA_Handler = None
    Interval = None

logger = logging.getLogger(__name__)


@dataclass
class StockData:
    """Stock data from TradingView."""
    symbol: str
    name: str
    exchange: str
    
    # Price data
    price: float
    open: float
    high: float
    low: float
    close: float
    change: float
    change_percent: float
    volume: int
    
    # Fundamental data
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    dividend_yield: Optional[float] = None
    
    # Technical summary
    recommendation: Optional[str] = None
    buy_signals: int = 0
    sell_signals: int = 0
    neutral_signals: int = 0
    
    # Metadata
    timestamp: datetime = None
    source: str = "TradingView"
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class TradingViewDataSource:
    """
    Data source that fetches real stock data from TradingView.
    
    Supports:
    - Real-time price data
    - Technical analysis summary
    - Multiple timeframes
    """
    
    EXCHANGE = "NSENG"
    SCREENER = "nigeria"
    
    # Interval mappings
    INTERVALS = {
        '1m': Interval.INTERVAL_1_MINUTE if Interval else None,
        '5m': Interval.INTERVAL_5_MINUTES if Interval else None,
        '15m': Interval.INTERVAL_15_MINUTES if Interval else None,
        '1h': Interval.INTERVAL_1_HOUR if Interval else None,
        '4h': Interval.INTERVAL_4_HOURS if Interval else None,
        '1d': Interval.INTERVAL_1_DAY if Interval else None,
        '1w': Interval.INTERVAL_1_WEEK if Interval else None,
        '1M': Interval.INTERVAL_1_MONTH if Interval else None,
    }
    
    def __init__(self):
        self._cache: Dict[str, tuple[StockData, datetime]] = {}
        self._cache_ttl = timedelta(minutes=1)
        
        if not TRADINGVIEW_AVAILABLE:
            logger.warning("TradingView TA library not available. Install with: pip install tradingview-ta")
    
    def is_available(self) -> bool:
        """Check if TradingView data source is available."""
        return TRADINGVIEW_AVAILABLE
    
    def get_stock_data(
        self,
        symbol: str,
        interval: str = '1d'
    ) -> Optional[StockData]:
        """
        Fetch current stock data from TradingView.
        
        Args:
            symbol: Stock ticker symbol (e.g., 'DANGCEM', 'MTNN')
            interval: Time interval for analysis
        
        Returns:
            StockData or None if fetch fails
        """
        if not TRADINGVIEW_AVAILABLE:
            logger.error("TradingView library not available")
            return None
        
        # Check cache
        cache_key = f"{symbol}:{interval}"
        if cache_key in self._cache:
            cached_data, cached_time = self._cache[cache_key]
            if datetime.utcnow() - cached_time < self._cache_ttl:
                return cached_data
        
        try:
            interval_obj = self.INTERVALS.get(interval, Interval.INTERVAL_1_DAY)
            
            handler = TA_Handler(
                symbol=symbol,
                exchange=self.EXCHANGE,
                screener=self.SCREENER,
                interval=interval_obj
            )
            
            analysis = handler.get_analysis()
            
            if not analysis:
                logger.warning(f"No analysis data for {symbol}")
                return None
            
            indicators = analysis.indicators
            summary = analysis.summary
            
            # Extract data
            stock_data = StockData(
                symbol=symbol,
                name=self._get_company_name(symbol),
                exchange=self.EXCHANGE,
                price=indicators.get('close', 0),
                open=indicators.get('open', 0),
                high=indicators.get('high', 0),
                low=indicators.get('low', 0),
                close=indicators.get('close', 0),
                change=indicators.get('change', 0),
                change_percent=self._calculate_change_percent(
                    indicators.get('close', 0),
                    indicators.get('open', 0)
                ),
                volume=int(indicators.get('volume', 0)),
                market_cap=indicators.get('market_cap_basic'),
                pe_ratio=indicators.get('price_earnings_ttm'),
                eps=indicators.get('earnings_per_share_basic_ttm'),
                dividend_yield=indicators.get('dividend_yield_recent'),
                recommendation=summary.get('RECOMMENDATION'),
                buy_signals=summary.get('BUY', 0),
                sell_signals=summary.get('SELL', 0),
                neutral_signals=summary.get('NEUTRAL', 0)
            )
            
            # Cache the result
            self._cache[cache_key] = (stock_data, datetime.utcnow())
            
            return stock_data
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None
    
    def get_technical_indicators(
        self,
        symbol: str,
        interval: str = '1d'
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed technical indicators from TradingView.
        
        Returns all available indicators for advanced analysis.
        """
        if not TRADINGVIEW_AVAILABLE:
            return None
        
        try:
            interval_obj = self.INTERVALS.get(interval, Interval.INTERVAL_1_DAY)
            
            handler = TA_Handler(
                symbol=symbol,
                exchange=self.EXCHANGE,
                screener=self.SCREENER,
                interval=interval_obj
            )
            
            analysis = handler.get_analysis()
            
            if not analysis:
                return None
            
            indicators = analysis.indicators
            
            # Extract key technical indicators
            return {
                # Moving Averages
                'sma_10': indicators.get('SMA10'),
                'sma_20': indicators.get('SMA20'),
                'sma_50': indicators.get('SMA50'),
                'sma_100': indicators.get('SMA100'),
                'sma_200': indicators.get('SMA200'),
                'ema_10': indicators.get('EMA10'),
                'ema_20': indicators.get('EMA20'),
                'ema_50': indicators.get('EMA50'),
                'ema_100': indicators.get('EMA100'),
                'ema_200': indicators.get('EMA200'),
                
                # Momentum
                'rsi': indicators.get('RSI'),
                'rsi_7': indicators.get('RSI[1]'),
                'stoch_k': indicators.get('Stoch.K'),
                'stoch_d': indicators.get('Stoch.D'),
                'cci': indicators.get('CCI20'),
                'mom': indicators.get('Mom'),
                
                # MACD
                'macd_line': indicators.get('MACD.macd'),
                'macd_signal': indicators.get('MACD.signal'),
                
                # Volatility
                'atr': indicators.get('ATR'),
                'bb_upper': indicators.get('BB.upper'),
                'bb_middle': indicators.get('BB.middle'),
                'bb_lower': indicators.get('BB.lower'),
                
                # Volume
                'volume': indicators.get('volume'),
                'volume_avg': indicators.get('average_volume_10d_calc'),
                
                # Trend
                'adx': indicators.get('ADX'),
                'plus_di': indicators.get('ADX+DI'),
                'minus_di': indicators.get('ADX-DI'),
                
                # Price data
                'open': indicators.get('open'),
                'high': indicators.get('high'),
                'low': indicators.get('low'),
                'close': indicators.get('close'),
                'change': indicators.get('change'),
                
                # Pivot points
                'pivot': indicators.get('Pivot.M.Classic.Middle'),
                'pivot_s1': indicators.get('Pivot.M.Classic.S1'),
                'pivot_s2': indicators.get('Pivot.M.Classic.S2'),
                'pivot_r1': indicators.get('Pivot.M.Classic.R1'),
                'pivot_r2': indicators.get('Pivot.M.Classic.R2'),
            }
            
        except Exception as e:
            logger.error(f"Error fetching indicators for {symbol}: {e}")
            return None
    
    def get_analysis_summary(
        self,
        symbol: str,
        interval: str = '1d'
    ) -> Optional[Dict[str, Any]]:
        """Get TradingView's analysis summary (buy/sell/neutral counts)."""
        if not TRADINGVIEW_AVAILABLE:
            return None
        
        try:
            interval_obj = self.INTERVALS.get(interval, Interval.INTERVAL_1_DAY)
            
            handler = TA_Handler(
                symbol=symbol,
                exchange=self.EXCHANGE,
                screener=self.SCREENER,
                interval=interval_obj
            )
            
            analysis = handler.get_analysis()
            
            if not analysis:
                return None
            
            return {
                'recommendation': analysis.summary.get('RECOMMENDATION'),
                'buy': analysis.summary.get('BUY', 0),
                'sell': analysis.summary.get('SELL', 0),
                'neutral': analysis.summary.get('NEUTRAL', 0),
                'oscillators': analysis.oscillators,
                'moving_averages': analysis.moving_averages
            }
            
        except Exception as e:
            logger.error(f"Error fetching analysis for {symbol}: {e}")
            return None
    
    def get_multiple_stocks(
        self,
        symbols: List[str],
        interval: str = '1d'
    ) -> Dict[str, Optional[StockData]]:
        """Fetch data for multiple stocks."""
        results = {}
        for symbol in symbols:
            results[symbol] = self.get_stock_data(symbol, interval)
        return results
    
    def build_ohlcv_dataframe(
        self,
        symbol: str,
        days: int = 30
    ) -> Optional[pd.DataFrame]:
        """
        Build a DataFrame with OHLCV data.
        
        Note: TradingView TA library only provides current data, not historical.
        For historical data, we would need a different source.
        This method provides current snapshot suitable for indicator calculation.
        """
        data = self.get_stock_data(symbol)
        if data is None:
            return None
        
        # Single row for current data
        df = pd.DataFrame([{
            'Open': data.open,
            'High': data.high,
            'Low': data.low,
            'Close': data.close,
            'Volume': data.volume
        }], index=[datetime.utcnow()])
        
        return df
    
    def _calculate_change_percent(self, close: float, open_price: float) -> float:
        """Calculate percentage change."""
        if open_price == 0:
            return 0.0
        return ((close - open_price) / open_price) * 100
    
    def _get_company_name(self, symbol: str) -> str:
        """Get company name from symbol."""
        # This would ideally come from a database or the NGX registry
        from app.data.sources.ngx_stocks import NGXStockRegistry
        registry = NGXStockRegistry()
        stock_info = registry.get_stock(symbol)
        return stock_info.get('name', symbol) if stock_info else symbol
    
    def clear_cache(self):
        """Clear the data cache."""
        self._cache.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'cached_symbols': len(self._cache),
            'symbols': list(self._cache.keys())
        }
