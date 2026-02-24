"""
NGN Market Integration Service

Provides real-time market data from ngnmarket.com including:
- Market snapshot (ASI, volume, market cap)
- Top gainers and losers (trending stocks)
- Historical ASI data for trend analysis
- Individual stock data

This service is the primary source for Nigerian market intelligence.
"""

import logging
import asyncio
import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

from app.core.http import http_fetch

logger = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    """Current market snapshot data."""
    date: str
    asi: float
    asi_change_percent: float
    deals: int
    volume: int
    value_traded: float
    equity_market_cap: float
    total_market_cap: float
    updated_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'date': self.date,
            'asi': self.asi,
            'asi_change_percent': self.asi_change_percent,
            'deals': self.deals,
            'volume': self.volume,
            'value_traded': self.value_traded,
            'equity_market_cap': self.equity_market_cap,
            'total_market_cap': self.total_market_cap,
            'updated_at': self.updated_at,
        }


@dataclass
class TrendingStock:
    """A trending stock (gainer or loser)."""
    symbol: str
    company_name: str
    sector: str
    last_close: float
    todays_close: float
    change: float
    change_percent: float
    rank: int
    updated_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'company_name': self.company_name,
            'sector': self.sector,
            'last_close': self.last_close,
            'todays_close': self.todays_close,
            'change': self.change,
            'change_percent': self.change_percent,
            'rank': self.rank,
            'updated_at': self.updated_at,
        }


@dataclass
class TrendingData:
    """Top gainers and losers."""
    date: str
    top_gainers: List[TrendingStock]
    top_losers: List[TrendingStock]
    biggest_gainer: Optional[Dict[str, Any]] = None
    biggest_loser: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'date': self.date,
            'top_gainers': [g.to_dict() for g in self.top_gainers],
            'top_losers': [l.to_dict() for l in self.top_losers],
            'biggest_gainer': self.biggest_gainer,
            'biggest_loser': self.biggest_loser,
            'summary': {
                'total_gainers': len(self.top_gainers),
                'total_losers': len(self.top_losers),
            }
        }


@dataclass
class ASIHistoryPoint:
    """Historical ASI data point."""
    date: str
    asi: float
    formatted_date: str


@dataclass
class MarketBreadth:
    """
    Estimated market breadth from trending data.
    
    **IMPORTANT: This data is ESTIMATED, not exchange-reported.**
    
    Since ngnmarket.com doesn't provide advancers/decliners count directly,
    we estimate it from the trending stocks and overall market movement.
    """
    estimated_advancers: int
    estimated_decliners: int
    estimated_unchanged: int
    breadth_ratio: float  # advancers / (advancers + decliners)
    market_sentiment: str  # 'bullish', 'bearish', 'neutral'
    confidence: float  # How confident we are in this estimate (typically 0.6)
    
    # Disclosure fields (required for transparency)
    is_estimated: bool = True
    methodology: str = "Heuristic estimation based on ASI direction, magnitude, and top gainer/loser performance asymmetry"
    warning: str = "This breadth data is NOT exchange-reported. It is estimated from available market indicators and should be used for directional guidance only."
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'advancing': self.estimated_advancers,
            'declining': self.estimated_decliners,
            'unchanged': self.estimated_unchanged,
            'ratio': round(self.breadth_ratio, 4),  # Limit precision
            'sentiment': self.market_sentiment,
            'confidence': round(self.confidence, 2),  # Limit to 2 decimals
            # Disclosure fields
            'is_estimated': self.is_estimated,
            'methodology': self.methodology,
            'warning': self.warning,
        }


class NgnMarketService:
    """
    Service for fetching market data from ngnmarket.com.
    
    Provides:
    - Real-time market snapshot
    - Top gainers and losers
    - Historical ASI data
    - Estimated market breadth
    """
    
    BASE_URL = "https://www.ngnmarket.com"
    
    def __init__(self, timeout: float = 15.0, cache_ttl: int = 120):
        """
        Initialize the service.
        
        Args:
            timeout: Request timeout in seconds
            cache_ttl: Cache TTL in seconds (default 2 minutes)
        """
        self._timeout = timeout
        self._cache_ttl = timedelta(seconds=cache_ttl)
        
        # Cache
        self._snapshot_cache: Optional[Tuple[MarketSnapshot, datetime]] = None
        self._trending_cache: Optional[Tuple[TrendingData, datetime]] = None
        self._asi_history_cache: Optional[Tuple[List[ASIHistoryPoint], datetime]] = None
    
    def is_available(self) -> bool:
        """Check if service is available."""
        return HTTPX_AVAILABLE
    
    async def get_market_snapshot(self, use_cache: bool = True) -> Optional[MarketSnapshot]:
        """
        Get current market snapshot.
        
        Returns ASI, volume, value traded, market cap, etc.
        """
        # Check cache
        if use_cache and self._snapshot_cache:
            cached, cached_at = self._snapshot_cache
            if datetime.utcnow() - cached_at < self._cache_ttl:
                return cached
        
        try:
            data = await self._fetch_page_data("/")
            if not data:
                return None
            
            ss_snapshot = data.get('ssSnapshot', {}).get('data', {})
            if not ss_snapshot:
                return None
            
            snapshot = MarketSnapshot(
                date=ss_snapshot.get('date', ''),
                asi=self._parse_float(ss_snapshot.get('asi')),
                asi_change_percent=self._parse_float(ss_snapshot.get('asiChangePercent')),
                deals=self._parse_int(ss_snapshot.get('deals')),
                volume=self._parse_int(ss_snapshot.get('volume')),
                value_traded=self._parse_float(ss_snapshot.get('valueTraded')),
                equity_market_cap=self._parse_float(ss_snapshot.get('marketCap', {}).get('equity')),
                total_market_cap=self._parse_float(ss_snapshot.get('marketCap', {}).get('total')),
                updated_at=ss_snapshot.get('updatedAt', ''),
            )
            
            self._snapshot_cache = (snapshot, datetime.utcnow())
            return snapshot
            
        except Exception as e:
            import traceback
            logger.error(f"Error fetching market snapshot: {e}\n{traceback.format_exc()}")
            return None
    
    async def get_trending_stocks(self, use_cache: bool = True) -> Optional[TrendingData]:
        """
        Get top gainers and losers.
        
        Returns real-time trending stocks with prices and changes.
        """
        # Check cache
        if use_cache and self._trending_cache:
            cached, cached_at = self._trending_cache
            if datetime.utcnow() - cached_at < self._cache_ttl:
                return cached
        
        try:
            data = await self._fetch_page_data("/trending")
            if not data:
                return None
            
            ss_movers = data.get('ssMovers', {})
            if not ss_movers.get('success'):
                return None
            
            movers_data = ss_movers.get('data', {})
            summary = ss_movers.get('summary', {})
            
            # Parse gainers
            top_gainers = []
            for g in movers_data.get('topGainers', []):
                top_gainers.append(TrendingStock(
                    symbol=g.get('symbol', ''),
                    company_name=g.get('companyName', ''),
                    sector=g.get('sector', ''),
                    last_close=self._parse_float(g.get('lastClose')),
                    todays_close=self._parse_float(g.get('todaysClose')),
                    change=self._parse_float(g.get('change')),
                    change_percent=self._parse_float(g.get('changePercent')),
                    rank=self._parse_int(g.get('rank')),
                    updated_at=g.get('updatedAt', ''),
                ))
            
            # Parse losers
            top_losers = []
            for l in movers_data.get('topLosers', []):
                top_losers.append(TrendingStock(
                    symbol=l.get('symbol', ''),
                    company_name=l.get('companyName', ''),
                    sector=l.get('sector', ''),
                    last_close=self._parse_float(l.get('lastClose')),
                    todays_close=self._parse_float(l.get('todaysClose')),
                    change=self._parse_float(l.get('change')),
                    change_percent=self._parse_float(l.get('changePercent')),
                    rank=self._parse_int(l.get('rank')),
                    updated_at=l.get('updatedAt', ''),
                ))
            
            trending = TrendingData(
                date=ss_movers.get('date', ''),
                top_gainers=top_gainers,
                top_losers=top_losers,
                biggest_gainer=summary.get('biggestGainer'),
                biggest_loser=summary.get('biggestLoser'),
            )
            
            self._trending_cache = (trending, datetime.utcnow())
            return trending
            
        except Exception as e:
            logger.error(f"Error fetching trending stocks: {e}")
            return None
    
    async def get_asi_history(self, use_cache: bool = True) -> List[ASIHistoryPoint]:
        """
        Get historical ASI data (last 30 days).
        
        Useful for trend analysis and volatility calculation.
        """
        # Check cache
        if use_cache and self._asi_history_cache:
            cached, cached_at = self._asi_history_cache
            if datetime.utcnow() - cached_at < self._cache_ttl:
                return cached
        
        try:
            data = await self._fetch_page_data("/market-snapshot")
            if not data:
                return []
            
            ss_dates = data.get('ssDates', [])
            history = []
            
            for point in ss_dates:
                history.append(ASIHistoryPoint(
                    date=point.get('date', ''),
                    asi=self._parse_float(point.get('asi')),
                    formatted_date=point.get('formattedDate', ''),
                ))
            
            self._asi_history_cache = (history, datetime.utcnow())
            return history
            
        except Exception as e:
            logger.error(f"Error fetching ASI history: {e}")
            return []
    
    async def estimate_market_breadth(self) -> Optional[MarketBreadth]:
        """
        Estimate market breadth from available data.
        
        Since ngnmarket.com doesn't provide advancers/decliners count,
        we estimate it using:
        - ASI change direction and magnitude
        - Top gainers vs losers performance
        - Overall market sentiment
        """
        try:
            snapshot = await self.get_market_snapshot()
            trending = await self.get_trending_stocks()
            
            if not snapshot or not trending:
                return None
            
            # Analyze ASI movement
            asi_change = snapshot.asi_change_percent
            
            # Analyze gainers vs losers strength
            avg_gainer_change = 0.0
            avg_loser_change = 0.0
            
            if trending.top_gainers:
                avg_gainer_change = sum(g.change_percent for g in trending.top_gainers) / len(trending.top_gainers)
            if trending.top_losers:
                avg_loser_change = sum(abs(l.change_percent) for l in trending.top_losers) / len(trending.top_losers)
            
            # Estimate breadth based on ASI and trending stocks
            # This is a heuristic approach since we don't have actual counts
            
            # Base estimate on ASI direction
            if asi_change > 0.5:
                # Strong up day - more advancers
                estimated_advancers = 60
                estimated_decliners = 30
                estimated_unchanged = 10
            elif asi_change > 0:
                # Mild up day
                estimated_advancers = 50
                estimated_decliners = 40
                estimated_unchanged = 10
            elif asi_change > -0.5:
                # Mild down day
                estimated_advancers = 40
                estimated_decliners = 50
                estimated_unchanged = 10
            else:
                # Strong down day - more decliners
                estimated_advancers = 30
                estimated_decliners = 60
                estimated_unchanged = 10
            
            # Adjust based on gainer/loser strength asymmetry
            if avg_gainer_change > avg_loser_change * 1.5:
                estimated_advancers += 10
                estimated_decliners -= 10
            elif avg_loser_change > avg_gainer_change * 1.5:
                estimated_advancers -= 10
                estimated_decliners += 10
            
            # Calculate ratio
            total = estimated_advancers + estimated_decliners
            breadth_ratio = estimated_advancers / total if total > 0 else 0.5
            
            # Determine sentiment
            if breadth_ratio > 0.6:
                sentiment = 'bullish'
            elif breadth_ratio < 0.4:
                sentiment = 'bearish'
            else:
                sentiment = 'neutral'
            
            # Confidence is lower because this is estimated
            confidence = 0.6  # 60% confidence in our estimate
            
            return MarketBreadth(
                estimated_advancers=estimated_advancers,
                estimated_decliners=estimated_decliners,
                estimated_unchanged=estimated_unchanged,
                breadth_ratio=breadth_ratio,
                market_sentiment=sentiment,
                confidence=confidence,
            )
            
        except Exception as e:
            logger.error(f"Error estimating market breadth: {e}")
            return None
    
    async def get_market_data_for_regime(self) -> Dict[str, Any]:
        """
        Get all market data needed for regime detection.
        
        Returns a consolidated view of:
        - Current ASI and change
        - Historical ASI for trend calculation
        - Estimated breadth
        - Volume and value traded
        """
        try:
            # Fetch all data concurrently
            snapshot, trending, asi_history = await asyncio.gather(
                self.get_market_snapshot(),
                self.get_trending_stocks(),
                self.get_asi_history(),
            )
            
            breadth = await self.estimate_market_breadth()
            
            # Calculate ASI trend from history
            asi_trend = self._calculate_asi_trend(asi_history)
            asi_volatility = self._calculate_asi_volatility(asi_history)
            
            return {
                'snapshot': snapshot.to_dict() if snapshot else None,
                'trending': trending.to_dict() if trending else None,
                'breadth': breadth.to_dict() if breadth else None,
                'asi_trend': asi_trend,
                'asi_volatility': asi_volatility,
                'asi_history': [{'date': p.date, 'asi': p.asi} for p in (asi_history or [])[:10]],
                'timestamp': datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Error getting market data for regime: {e}")
            return {}
    
    def _calculate_asi_trend(self, history: List[ASIHistoryPoint]) -> Dict[str, Any]:
        """Calculate ASI trend from historical data."""
        if not history or len(history) < 2:
            return {'direction': 'unknown', 'strength': 0, 'days': 0}
        
        # Get recent values (most recent first)
        recent = history[:5]
        if len(recent) < 2:
            return {'direction': 'unknown', 'strength': 0, 'days': 0}
        
        # Calculate trend direction
        current = recent[0].asi
        previous = recent[-1].asi
        
        if previous == 0:
            return {'direction': 'unknown', 'strength': 0, 'days': len(recent)}
        
        change_percent = ((current - previous) / previous) * 100
        
        if change_percent > 1:
            direction = 'up'
            strength = min(change_percent / 5, 1.0)  # Normalize to 0-1
        elif change_percent < -1:
            direction = 'down'
            strength = min(abs(change_percent) / 5, 1.0)
        else:
            direction = 'flat'
            strength = 0.2
        
        return {
            'direction': direction,
            'strength': round(strength, 2),
            'change_percent': round(change_percent, 2),
            'days': len(recent),
        }
    
    def _calculate_asi_volatility(self, history: List[ASIHistoryPoint]) -> Dict[str, Any]:
        """Calculate ASI volatility from historical data."""
        if not history or len(history) < 3:
            return {'level': 'unknown', 'daily_range_percent': 0}
        
        # Calculate daily changes
        changes = []
        for i in range(len(history) - 1):
            if history[i+1].asi > 0:
                daily_change = abs((history[i].asi - history[i+1].asi) / history[i+1].asi) * 100
                changes.append(daily_change)
        
        if not changes:
            return {'level': 'unknown', 'daily_range_percent': 0}
        
        avg_change = sum(changes) / len(changes)
        
        # Classify volatility
        if avg_change > 2:
            level = 'high'
        elif avg_change > 1:
            level = 'moderate'
        else:
            level = 'low'
        
        return {
            'level': level,
            'daily_range_percent': round(avg_change, 2),
            'max_daily_change': round(max(changes), 2) if changes else 0,
        }
    
    async def _fetch_page_data(self, path: str) -> Optional[Dict[str, Any]]:
        """Fetch and parse __NEXT_DATA__ from a page."""
        if not HTTPX_AVAILABLE:
            logger.error("httpx not available")
            return None
        
        url = f"{self.BASE_URL}{path}"
        
        response = await http_fetch(
            url,
            timeout=self._timeout,
            raise_for_status=False,
        )
        
        if response.status_code != 200:
            logger.error(f"HTTP {response.status_code} from {url}")
            return None
        
        # Extract __NEXT_DATA__
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            response.text,
            re.DOTALL
        )
        
        if not match:
            logger.error(f"No __NEXT_DATA__ found in {url}")
            return None
        
        try:
            data = json.loads(match.group(1))
            return data.get('props', {}).get('pageProps', {})
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
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
    
    def clear_cache(self):
        """Clear all cached data."""
        self._snapshot_cache = None
        self._trending_cache = None
        self._asi_history_cache = None


# Singleton instance
_ngnmarket_service: Optional[NgnMarketService] = None


def get_ngnmarket_service() -> NgnMarketService:
    """Get the singleton NgnMarketService instance."""
    global _ngnmarket_service
    if _ngnmarket_service is None:
        _ngnmarket_service = NgnMarketService()
    return _ngnmarket_service
