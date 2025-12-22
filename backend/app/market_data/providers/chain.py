"""
Provider Chain - Multi-tier fallback data sourcing

Implements the 3-tier fallback strategy:
1. Try Tier 1 (NGX Official) first
2. Fill missing symbols with Tier 2 (Apt Securities)
3. Fill remaining with Tier 3 (Simulated) as last resort

Logs counts from each source for transparency.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from .base import (
    MarketDataProvider,
    PriceSnapshot,
    FetchResult,
    DataSource,
)

logger = logging.getLogger(__name__)


@dataclass
class SourceBreakdown:
    """Breakdown of data sources used in a fetch."""
    ngx_official: int = 0
    apt_securities: int = 0
    simulated: int = 0
    total: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'ngx_official': self.ngx_official,
            'apt_securities': self.apt_securities,
            'simulated': self.simulated,
            'total': self.total,
        }


@dataclass
class ChainFetchResult:
    """Result of a provider chain fetch operation."""
    success: bool
    snapshots: Dict[str, PriceSnapshot] = field(default_factory=dict)
    source_breakdown: SourceBreakdown = field(default_factory=SourceBreakdown)
    is_simulated: bool = False  # True if ANY data is simulated
    simulated_symbols: List[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    errors: List[str] = field(default_factory=list)
    fetch_time_ms: float = 0.0
    
    def to_meta_dict(self) -> Dict[str, Any]:
        """Return metadata for API responses."""
        return {
            'source_breakdown': self.source_breakdown.to_dict(),
            'is_simulated': self.is_simulated,
            'simulated_count': len(self.simulated_symbols),
            'simulated_symbols': self.simulated_symbols,
            'last_updated': self.last_updated.isoformat(),
            'fetch_time_ms': round(self.fetch_time_ms, 2),
        }


class CacheEntry:
    """Cache entry with TTL."""
    def __init__(self, data: Any, ttl_seconds: int = 120):
        self.data = data
        self.created_at = datetime.utcnow()
        self.ttl = timedelta(seconds=ttl_seconds)
    
    def is_valid(self) -> bool:
        return datetime.utcnow() - self.created_at < self.ttl


class InMemoryCache:
    """
    Simple in-memory cache with TTL support.
    
    Redis-compatible interface for easy future migration.
    """
    
    def __init__(self, default_ttl: int = 120):
        self._cache: Dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        entry = self._cache.get(key)
        if entry and entry.is_valid():
            return entry.data
        elif entry:
            del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache with TTL."""
        self._cache[key] = CacheEntry(value, ttl or self._default_ttl)
    
    def delete(self, key: str):
        """Delete a cache entry."""
        self._cache.pop(key, None)
    
    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()
    
    def cleanup(self):
        """Remove expired entries."""
        expired = [k for k, v in self._cache.items() if not v.is_valid()]
        for k in expired:
            del self._cache[k]


class ProviderChain:
    """
    Multi-tier provider chain with fallback logic.
    
    Strategy:
    1. Try Tier 1 provider (NGX Official)
    2. For missing symbols, try Tier 2 (Apt Securities)
    3. For still-missing symbols, use Tier 3 (Simulated)
    
    Caching:
    - Tier 1 and Tier 2 results cached with configurable TTL
    - Tier 3 (simulated) is never cached
    
    Transparency:
    - Returns source breakdown for every fetch
    - Flags when ANY simulated data is used
    """
    
    def __init__(
        self,
        providers: List[MarketDataProvider],
        cache_ttl: int = 120,  # 2 minutes default
        enable_cache: bool = True,
    ):
        """
        Initialize provider chain.
        
        Args:
            providers: List of providers in priority order (Tier 1 first)
            cache_ttl: Cache TTL in seconds
            enable_cache: Whether to enable caching
        """
        # Sort providers by tier
        self._providers = sorted(providers, key=lambda p: p.tier)
        self._cache = InMemoryCache(default_ttl=cache_ttl) if enable_cache else None
        self._cache_ttl = cache_ttl
    
    async def fetch_snapshot(
        self,
        symbols: List[str],
        use_cache: bool = True
    ) -> ChainFetchResult:
        """
        Fetch price snapshots using tiered fallback strategy.
        
        Args:
            symbols: List of stock symbols to fetch
            use_cache: Whether to use cached results
            
        Returns:
            ChainFetchResult with snapshots and source breakdown
        """
        import time
        start_time = time.time()
        
        symbols_upper = [s.upper() for s in symbols]
        all_snapshots: Dict[str, PriceSnapshot] = {}
        remaining_symbols = set(symbols_upper)
        errors: List[str] = []
        
        # Source counters
        source_counts = {
            DataSource.NGX_OFFICIAL: 0,
            DataSource.APT_SECURITIES: 0,
            DataSource.SIMULATED: 0,
        }
        
        # Check cache first
        if use_cache and self._cache:
            cached_symbols = []
            for symbol in list(remaining_symbols):
                cached = self._cache.get(f"snapshot:{symbol}")
                if cached:
                    all_snapshots[symbol] = cached
                    cached_symbols.append(symbol)
                    remaining_symbols.remove(symbol)
                    source_counts[cached.source] = source_counts.get(cached.source, 0) + 1
            
            if cached_symbols:
                logger.debug(f"Cache hit for {len(cached_symbols)} symbols")
        
        # Try each provider in order
        for provider in self._providers:
            if not remaining_symbols:
                break
            
            if not provider.is_available():
                logger.warning(f"Provider {provider.name} not available, skipping")
                continue
            
            try:
                logger.info(f"Fetching {len(remaining_symbols)} symbols from {provider.name}")
                result = await provider.fetch_snapshot(list(remaining_symbols))
                
                if result.success and result.snapshots:
                    for symbol, snapshot in result.snapshots.items():
                        all_snapshots[symbol] = snapshot
                        remaining_symbols.discard(symbol)
                        source_counts[snapshot.source] = source_counts.get(snapshot.source, 0) + 1
                        
                        # Cache non-simulated results
                        if self._cache and snapshot.source != DataSource.SIMULATED:
                            self._cache.set(f"snapshot:{symbol}", snapshot, self._cache_ttl)
                    
                    logger.info(f"{provider.name}: fetched {len(result.snapshots)} symbols")
                
                if result.error:
                    errors.append(f"{provider.name}: {result.error}")
                    
            except Exception as e:
                logger.error(f"Provider {provider.name} failed: {e}")
                errors.append(f"{provider.name}: {str(e)}")
        
        # Build source breakdown
        breakdown = SourceBreakdown(
            ngx_official=source_counts.get(DataSource.NGX_OFFICIAL, 0),
            apt_securities=source_counts.get(DataSource.APT_SECURITIES, 0),
            simulated=source_counts.get(DataSource.SIMULATED, 0),
            total=len(all_snapshots),
        )
        
        # Identify simulated symbols
        simulated_symbols = [
            s for s, snap in all_snapshots.items()
            if snap.source == DataSource.SIMULATED
        ]
        
        fetch_time = (time.time() - start_time) * 1000
        
        # Log summary
        logger.info(
            f"ProviderChain: {breakdown.total} total "
            f"(NGX: {breakdown.ngx_official}, "
            f"Apt: {breakdown.apt_securities}, "
            f"Simulated: {breakdown.simulated}) "
            f"in {fetch_time:.0f}ms"
        )
        
        if simulated_symbols:
            logger.warning(f"Simulated data for: {', '.join(simulated_symbols[:10])}{'...' if len(simulated_symbols) > 10 else ''}")
        
        return ChainFetchResult(
            success=len(all_snapshots) > 0,
            snapshots=all_snapshots,
            source_breakdown=breakdown,
            is_simulated=len(simulated_symbols) > 0,
            simulated_symbols=simulated_symbols,
            last_updated=datetime.utcnow(),
            errors=errors,
            fetch_time_ms=fetch_time,
        )
    
    def clear_cache(self):
        """Clear the provider chain cache."""
        if self._cache:
            self._cache.clear()
    
    def get_provider_status(self) -> List[Dict[str, Any]]:
        """Get status of all providers."""
        return [
            {
                'name': p.name,
                'tier': p.tier,
                'source': p.source.value,
                'available': p.is_available(),
            }
            for p in self._providers
        ]
