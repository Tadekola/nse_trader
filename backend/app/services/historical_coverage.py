"""
Historical Data Coverage Module for NSE Trader (Phase 2).

Provides capability assessment for technical indicator computation:
- Tracks available OHLCV history per symbol
- Defines required sessions for each indicator
- Gates indicator computation based on data sufficiency
- Triggers NO_TRADE when insufficient history exists

This ensures technical indicators are only computed with sufficient data,
preventing misleading signals based on incomplete information.
"""
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class IndicatorType(str, Enum):
    """Technical indicator types with their required history."""
    RSI_14 = "RSI_14"
    SMA_20 = "SMA_20"
    SMA_50 = "SMA_50"
    SMA_200 = "SMA_200"
    EMA_12 = "EMA_12"
    EMA_26 = "EMA_26"
    EMA_50 = "EMA_50"
    BOLLINGER_20 = "BOLLINGER_20"
    MACD = "MACD"  # Requires 26 sessions (slow EMA)
    STOCHASTIC = "STOCHASTIC"  # Requires 14 sessions
    ADX = "ADX"  # Requires 14 sessions
    ATR = "ATR"  # Requires 14 sessions
    OBV = "OBV"  # Requires 2+ sessions
    VOLUME_RATIO = "VOLUME_RATIO"  # Requires 20 sessions


# Required sessions for each indicator
INDICATOR_REQUIREMENTS: Dict[IndicatorType, int] = {
    IndicatorType.RSI_14: 15,  # 14 periods + 1 for calculation
    IndicatorType.SMA_20: 20,
    IndicatorType.SMA_50: 50,
    IndicatorType.SMA_200: 200,
    IndicatorType.EMA_12: 12,
    IndicatorType.EMA_26: 26,
    IndicatorType.EMA_50: 50,
    IndicatorType.BOLLINGER_20: 20,
    IndicatorType.MACD: 26,  # Uses 26-period slow EMA
    IndicatorType.STOCHASTIC: 14,
    IndicatorType.ADX: 28,  # 14 * 2 for smoothing
    IndicatorType.ATR: 14,
    IndicatorType.OBV: 2,
    IndicatorType.VOLUME_RATIO: 20,
}

# Indicators required for a valid recommendation
REQUIRED_FOR_RECOMMENDATION: Set[IndicatorType] = {
    IndicatorType.RSI_14,
    IndicatorType.SMA_50,
    IndicatorType.MACD,
    IndicatorType.BOLLINGER_20,
}

# Minimum sessions required for any recommendation
MINIMUM_SESSIONS_FOR_RECOMMENDATION = 50


# Default staleness threshold (days)
DEFAULT_STALENESS_THRESHOLD_DAYS = 5


@dataclass
class HistoricalCoverage:
    """
    Historical data coverage assessment for a symbol.
    
    Determines whether sufficient OHLCV data exists for technical analysis.
    Phase 3 hardening: includes staleness detection.
    """
    symbol: str
    sessions_available: int
    required_sessions: int  # For full indicator suite
    is_sufficient: bool
    missing_sessions: int
    last_updated: datetime
    source: str
    
    # Per-indicator availability
    indicator_availability: Dict[str, bool] = field(default_factory=dict)
    indicator_requirements: Dict[str, int] = field(default_factory=dict)
    
    # Warnings and notes
    warnings: List[str] = field(default_factory=list)
    
    # Phase 3 hardening: staleness detection
    is_stale: bool = False
    stale_reason: Optional[str] = None
    ingestion_status: Optional[str] = None
    last_error: Optional[str] = None
    records_rejected_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "symbol": self.symbol,
            "sessions_available": self.sessions_available,
            "required_sessions": self.required_sessions,
            "is_sufficient": self.is_sufficient,
            "missing_sessions": self.missing_sessions,
            "last_updated": self.last_updated.isoformat(),
            "source": self.source,
            "indicator_availability": self.indicator_availability,
            "indicator_requirements": self.indicator_requirements,
            "warnings": self.warnings,
            # Phase 3 hardening fields
            "is_stale": self.is_stale,
            "stale_reason": self.stale_reason,
            "ingestion_status": self.ingestion_status,
            "last_error": self.last_error,
            "records_rejected_count": self.records_rejected_count,
        }
    
    def can_compute(self, indicator: IndicatorType) -> bool:
        """Check if a specific indicator can be computed."""
        required = INDICATOR_REQUIREMENTS.get(indicator, 0)
        return self.sessions_available >= required
    
    def get_computable_indicators(self) -> List[IndicatorType]:
        """Get list of indicators that can be computed."""
        return [
            ind for ind in IndicatorType
            if self.can_compute(ind)
        ]
    
    def get_missing_indicators(self) -> List[IndicatorType]:
        """Get list of indicators that cannot be computed."""
        return [
            ind for ind in IndicatorType
            if not self.can_compute(ind)
        ]
    
    def has_required_for_recommendation(self) -> bool:
        """Check if all required indicators for recommendation can be computed."""
        return all(
            self.can_compute(ind)
            for ind in REQUIRED_FOR_RECOMMENDATION
        )


@dataclass
class IndicatorCoverage:
    """
    Per-indicator coverage information for API responses.
    """
    indicator_name: str
    is_available: bool
    required_sessions: int
    sessions_available: int
    missing_sessions: int
    reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "indicator_name": self.indicator_name,
            "is_available": self.is_available,
            "required_sessions": self.required_sessions,
            "sessions_available": self.sessions_available,
            "missing_sessions": self.missing_sessions,
            "reason": self.reason,
        }


class HistoricalCoverageService:
    """
    Service for assessing historical data coverage.
    
    Phase 3 Update: Now integrates with HistoricalOHLCVStorage
    to report actual ingested session counts.
    
    Falls back to _KNOWN_HISTORY for testing/overrides.
    """
    
    # Symbols with known historical data availability (for testing/overrides)
    _KNOWN_HISTORY: Dict[str, int] = {}
    
    def __init__(self):
        """Initialize the service."""
        self._cache: Dict[str, HistoricalCoverage] = {}
        self._cache_ttl_seconds = 300  # 5 minutes
        self._storage = None  # Lazy-loaded to avoid circular imports
    
    def _get_storage(self):
        """Get storage instance (lazy-loaded)."""
        if self._storage is None:
            try:
                from app.data.historical.storage import get_historical_storage
                self._storage = get_historical_storage()
            except ImportError:
                logger.warning("Historical storage not available")
                self._storage = False  # Mark as unavailable
        return self._storage if self._storage else None
    
    def get_coverage(self, symbol: str) -> HistoricalCoverage:
        """
        Get historical coverage for a symbol.
        
        Args:
            symbol: Stock symbol to check
            
        Returns:
            HistoricalCoverage with availability assessment
        """
        symbol = symbol.upper()
        
        # Phase 3: First check actual storage for ingested data
        sessions_available = 0
        storage = self._get_storage()
        
        if storage:
            sessions_available = storage.get_sessions_available(symbol)
        
        # Fall back to _KNOWN_HISTORY for testing/overrides
        if sessions_available == 0 and symbol in self._KNOWN_HISTORY:
            sessions_available = self._KNOWN_HISTORY[symbol]
        
        # Determine required sessions (for full indicator suite)
        required_sessions = MINIMUM_SESSIONS_FOR_RECOMMENDATION
        
        # Calculate missing sessions
        missing_sessions = max(0, required_sessions - sessions_available)
        
        # Check sufficiency
        is_sufficient = sessions_available >= required_sessions
        
        # Build indicator availability map
        indicator_availability = {}
        indicator_requirements = {}
        warnings = []
        
        for indicator in IndicatorType:
            required = INDICATOR_REQUIREMENTS[indicator]
            available = sessions_available >= required
            indicator_availability[indicator.value] = available
            indicator_requirements[indicator.value] = required
            
            if not available and indicator in REQUIRED_FOR_RECOMMENDATION:
                warnings.append(
                    f"{indicator.value} requires {required} sessions; only {sessions_available} available"
                )
        
        # Add source information (Phase 3 updated)
        if sessions_available == 0:
            source = "NO_HISTORICAL_DATA"
            warnings.append(
                "Historical OHLCV data not available. "
                "Run historical ingestion to enable indicator computation."
            )
        elif storage and storage.get_sessions_available(symbol) > 0:
            source = "NGNMARKET_HISTORICAL"
        else:
            source = "TESTING_OVERRIDE"
        
        # Phase 3 hardening: get staleness and status info from storage
        is_stale = False
        stale_reason = None
        ingestion_status = None
        last_error = None
        records_rejected_count = 0
        
        if storage:
            metadata = storage.get_metadata(symbol)
            if metadata:
                is_stale = metadata.is_stale(DEFAULT_STALENESS_THRESHOLD_DAYS)
                stale_reason = metadata.get_stale_reason(DEFAULT_STALENESS_THRESHOLD_DAYS)
                ingestion_status = metadata.ingestion_status.value if metadata.ingestion_status else None
                last_error = metadata.last_error
                records_rejected_count = metadata.records_rejected_count
                
                if is_stale:
                    warnings.append(f"Data is stale: {stale_reason}")
                if last_error:
                    warnings.append(f"Last ingestion error: {last_error}")
        
        return HistoricalCoverage(
            symbol=symbol,
            sessions_available=sessions_available,
            required_sessions=required_sessions,
            is_sufficient=is_sufficient,
            missing_sessions=missing_sessions,
            last_updated=datetime.now(timezone.utc),
            source=source,
            indicator_availability=indicator_availability,
            indicator_requirements=indicator_requirements,
            warnings=warnings,
            # Phase 3 hardening fields
            is_stale=is_stale,
            stale_reason=stale_reason,
            ingestion_status=ingestion_status,
            last_error=last_error,
            records_rejected_count=records_rejected_count,
        )
    
    def get_indicator_coverage(
        self, 
        symbol: str, 
        indicator: IndicatorType
    ) -> IndicatorCoverage:
        """
        Get coverage for a specific indicator.
        
        Args:
            symbol: Stock symbol
            indicator: Indicator to check
            
        Returns:
            IndicatorCoverage with availability details
        """
        coverage = self.get_coverage(symbol)
        required = INDICATOR_REQUIREMENTS[indicator]
        available = coverage.sessions_available >= required
        missing = max(0, required - coverage.sessions_available)
        
        reason = None
        if not available:
            reason = f"Requires {required} sessions; only {coverage.sessions_available} available"
        
        return IndicatorCoverage(
            indicator_name=indicator.value,
            is_available=available,
            required_sessions=required,
            sessions_available=coverage.sessions_available,
            missing_sessions=missing,
            reason=reason,
        )
    
    def can_generate_recommendation(self, symbol: str) -> tuple[bool, str]:
        """
        Check if a valid recommendation can be generated.
        
        Returns:
            tuple of (can_generate, reason)
        """
        coverage = self.get_coverage(symbol)
        
        if not coverage.has_required_for_recommendation():
            missing = [
                ind.value for ind in REQUIRED_FOR_RECOMMENDATION
                if not coverage.can_compute(ind)
            ]
            reason = (
                f"INSUFFICIENT_HISTORY: Cannot compute required indicators "
                f"({', '.join(missing)}). "
                f"Requires {coverage.required_sessions} sessions; "
                f"only {coverage.sessions_available} available."
            )
            return False, reason
        
        return True, "Sufficient history for recommendation"
    
    def set_known_history(self, symbol: str, sessions: int) -> None:
        """
        Set known historical data availability for a symbol.
        
        Used for testing and when historical data is ingested.
        """
        self._KNOWN_HISTORY[symbol.upper()] = sessions
        # Clear cache
        if symbol.upper() in self._cache:
            del self._cache[symbol.upper()]
    
    def get_all_indicator_requirements(self) -> Dict[str, int]:
        """Get all indicator requirements as a dictionary."""
        return {
            ind.value: req 
            for ind, req in INDICATOR_REQUIREMENTS.items()
        }


# Singleton instance
_service_instance: Optional[HistoricalCoverageService] = None


def get_historical_coverage_service() -> HistoricalCoverageService:
    """Get the singleton historical coverage service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = HistoricalCoverageService()
    return _service_instance


# Convenience functions
def check_indicator_coverage(symbol: str) -> HistoricalCoverage:
    """Check historical coverage for a symbol."""
    return get_historical_coverage_service().get_coverage(symbol)


def can_compute_indicator(symbol: str, indicator: IndicatorType) -> bool:
    """Check if a specific indicator can be computed for a symbol."""
    coverage = get_historical_coverage_service().get_coverage(symbol)
    return coverage.can_compute(indicator)


def get_insufficient_history_reason(symbol: str) -> str:
    """Get explanation for insufficient history."""
    coverage = get_historical_coverage_service().get_coverage(symbol)
    
    if coverage.is_sufficient:
        return "Sufficient history available"
    
    return (
        f"Requires {coverage.required_sessions} sessions; "
        f"only {coverage.sessions_available} available. "
        f"Missing: {', '.join(ind.value for ind in coverage.get_missing_indicators()[:5])}"
        f"{'...' if len(coverage.get_missing_indicators()) > 5 else ''}"
    )
