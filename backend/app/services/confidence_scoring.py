"""
Data Confidence Scoring Module for NSE Trader.

Calculates confidence scores for stock data based on:
- Price agreement across sources (NGX, TradingView)
- Volume agreement
- Timestamp freshness
- Source availability

Suppresses recommendations when data quality is insufficient.
"""
import logging
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SuppressionReason(str, Enum):
    """Reasons for suppressing a recommendation."""
    LOW_CONFIDENCE = "low_confidence"
    HIGH_PRICE_VARIANCE = "high_price_variance"
    HIGH_VOLUME_VARIANCE = "high_volume_variance"
    STALE_DATA = "stale_data"
    INSUFFICIENT_SOURCES = "insufficient_sources"
    CIRCUIT_BREAKER_ACTIVE = "circuit_breaker_active"


@dataclass
class ConfidenceScoreConfig:
    """
    Configurable thresholds for confidence scoring.
    
    Attributes:
        min_confidence_threshold: Minimum confidence (0.0-1.0) to allow recommendations
        max_price_variance_percent: Maximum allowed price variance between sources
        max_volume_variance_percent: Maximum allowed volume variance between sources
        max_data_age_minutes: Maximum age of data before it's considered stale
        price_weight: Weight for price agreement in overall score (0.0-1.0)
        volume_weight: Weight for volume agreement in overall score (0.0-1.0)
        freshness_weight: Weight for data freshness in overall score (0.0-1.0)
        source_weight: Weight for source availability in overall score (0.0-1.0)
    """
    min_confidence_threshold: float = 0.65
    max_price_variance_percent: float = 5.0
    max_volume_variance_percent: float = 20.0
    max_data_age_minutes: int = 1440  # 24h — NGX trades ~6h/day, data is stale after hours
    price_weight: float = 0.40
    volume_weight: float = 0.20
    freshness_weight: float = 0.20
    source_weight: float = 0.20
    
    def __post_init__(self):
        # Validate weights sum to 1.0
        total_weight = (
            self.price_weight + 
            self.volume_weight + 
            self.freshness_weight + 
            self.source_weight
        )
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total_weight}")


@dataclass
class ConfidenceScore:
    """
    Result of confidence scoring for a symbol.
    
    Attributes:
        symbol: Stock symbol
        overall_score: Combined confidence score (0.0-1.0)
        price_agreement_score: Score for price agreement across sources (0.0-1.0)
        volume_agreement_score: Score for volume agreement across sources (0.0-1.0)
        freshness_score: Score for data freshness (0.0-1.0)
        source_availability_score: Score for source availability (0.0-1.0)
        is_suppressed: Whether recommendation should be suppressed
        suppression_reasons: List of reasons for suppression (if any)
        human_readable_reason: Single human-readable explanation
        sources_used: List of data sources used
        price_variance_percent: Actual price variance between sources
        volume_variance_percent: Actual volume variance between sources
        data_age_seconds: Age of the oldest data point in seconds
        timestamp: When the score was calculated
    """
    symbol: str
    overall_score: float
    price_agreement_score: float
    volume_agreement_score: float
    freshness_score: float
    source_availability_score: float
    is_suppressed: bool
    suppression_reasons: List[SuppressionReason] = field(default_factory=list)
    human_readable_reason: Optional[str] = None
    sources_used: List[str] = field(default_factory=list)
    primary_source: Optional[str] = None
    secondary_source: Optional[str] = None
    price_variance_percent: float = 0.0
    volume_variance_percent: float = 0.0
    data_age_seconds: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "symbol": self.symbol,
            "confidence_score": round(self.overall_score, 4),
            "status": "SUPPRESSED" if self.is_suppressed else "ACTIVE",
            "suppression_reason": self.human_readable_reason,
            "primary_source": self.primary_source,
            "secondary_source": self.secondary_source,
            "component_scores": {
                "price_agreement": round(self.price_agreement_score, 4),
                "volume_agreement": round(self.volume_agreement_score, 4),
                "freshness": round(self.freshness_score, 4),
                "source_availability": round(self.source_availability_score, 4)
            },
            "metrics": {
                "price_variance_percent": round(self.price_variance_percent, 2),
                "volume_variance_percent": round(self.volume_variance_percent, 2),
                "data_age_seconds": round(self.data_age_seconds, 1),
                "sources_used": self.sources_used
            },
            "timestamp": self.timestamp.isoformat()
        }


class DataConfidenceScorer:
    """
    Calculates data confidence scores for stock symbols.
    
    Evaluates data quality from multiple sources and determines
    whether recommendations should be suppressed due to
    insufficient data confidence.
    """
    
    # Known data sources with their reliability weights
    SOURCE_RELIABILITY = {
        "NGX": 0.95,           # Official exchange - highest reliability
        "ngx_official": 0.95,  # Alias for NGX
        "TradingView": 0.90,   # Reputable third-party
        "kwayisi": 0.90,       # Kwayisi AFX - Reliable secondary source
        "Simulated": 0.50,     # Simulated/fallback data - low reliability
        "simulated": 0.50,     # Lowercase alias
        "cache": 0.85,         # Cached data - good but may be stale
        "Registry": 0.80       # Static registry data
    }
    
    def __init__(self, config: Optional[ConfidenceScoreConfig] = None):
        """
        Initialize the confidence scorer.
        
        Args:
            config: Configuration for thresholds. Uses defaults if not provided.
        """
        self.config = config or ConfidenceScoreConfig()
        self._cache: Dict[str, Tuple[ConfidenceScore, datetime]] = {}
        self._cache_ttl = timedelta(minutes=5)
    
    def calculate_confidence(
        self,
        symbol: str,
        source_data: List[Dict[str, Any]],
        circuit_breaker_active: bool = False
    ) -> ConfidenceScore:
        """
        Calculate confidence score for a symbol based on multiple source data.
        
        Args:
            symbol: Stock symbol
            source_data: List of data from different sources, each containing:
                - source: Name of the data source
                - price: Current price
                - volume: Trading volume
                - timestamp: Data timestamp (ISO format or datetime)
            circuit_breaker_active: Whether circuit breaker is active for this symbol
        
        Returns:
            ConfidenceScore with all metrics and suppression decision
        """
        symbol = symbol.upper()
        suppression_reasons: List[SuppressionReason] = []
        
        # Handle circuit breaker
        if circuit_breaker_active:
            return self._create_suppressed_score(
                symbol=symbol,
                reason=SuppressionReason.CIRCUIT_BREAKER_ACTIVE,
                human_reason=f"Circuit breaker is active for {symbol}. Trading halted due to extreme volatility."
            )
        
        # Check source availability
        if not source_data or len(source_data) == 0:
            return self._create_suppressed_score(
                symbol=symbol,
                reason=SuppressionReason.INSUFFICIENT_SOURCES,
                human_reason=f"No data sources available for {symbol}."
            )
        
        # Extract source names
        sources_used = [d.get("source", "unknown") for d in source_data]
        
        # Calculate component scores
        price_score, price_variance = self._calculate_price_agreement(source_data)
        volume_score, volume_variance = self._calculate_volume_agreement(source_data)
        freshness_score, data_age = self._calculate_freshness(source_data)
        source_score = self._calculate_source_availability(source_data)
        
        # Calculate weighted overall score
        overall_score = (
            price_score * self.config.price_weight +
            volume_score * self.config.volume_weight +
            freshness_score * self.config.freshness_weight +
            source_score * self.config.source_weight
        )
        
        # Check for suppression conditions
        human_reasons = []
        
        # Check confidence threshold
        if overall_score < self.config.min_confidence_threshold:
            suppression_reasons.append(SuppressionReason.LOW_CONFIDENCE)
            human_reasons.append(
                f"Overall confidence ({overall_score:.1%}) is below minimum threshold ({self.config.min_confidence_threshold:.1%})"
            )
        
        # Check price variance
        if price_variance > self.config.max_price_variance_percent:
            suppression_reasons.append(SuppressionReason.HIGH_PRICE_VARIANCE)
            human_reasons.append(
                f"Price variance ({price_variance:.1f}%) exceeds maximum allowed ({self.config.max_price_variance_percent:.1f}%)"
            )
        
        # Check volume variance
        if volume_variance > self.config.max_volume_variance_percent:
            suppression_reasons.append(SuppressionReason.HIGH_VOLUME_VARIANCE)
            human_reasons.append(
                f"Volume variance ({volume_variance:.1f}%) exceeds maximum allowed ({self.config.max_volume_variance_percent:.1f}%)"
            )
        
        # Check data freshness
        if data_age > self.config.max_data_age_minutes * 60:
            suppression_reasons.append(SuppressionReason.STALE_DATA)
            human_reasons.append(
                f"Data is stale ({data_age/60:.0f} minutes old, max {self.config.max_data_age_minutes} minutes)"
            )
        
        # Check source availability (single low-reliability source)
        if len(source_data) == 1 and source_score < 0.6:
            suppression_reasons.append(SuppressionReason.INSUFFICIENT_SOURCES)
            human_reasons.append(
                f"Only one low-reliability source available ({sources_used[0]})"
            )
        
        is_suppressed = len(suppression_reasons) > 0
        human_readable = "; ".join(human_reasons) if human_reasons else None
        
        score = ConfidenceScore(
            symbol=symbol,
            overall_score=overall_score,
            price_agreement_score=price_score,
            volume_agreement_score=volume_score,
            freshness_score=freshness_score,
            source_availability_score=source_score,
            is_suppressed=is_suppressed,
            suppression_reasons=suppression_reasons,
            human_readable_reason=human_readable,
            sources_used=sources_used,
            price_variance_percent=price_variance,
            volume_variance_percent=volume_variance,
            data_age_seconds=data_age
        )
        
        # Log suppression events
        if is_suppressed:
            logger.warning(
                f"Recommendation suppressed for {symbol}: {human_readable}"
            )
        
        return score
    
    def calculate_from_single_source(
        self,
        symbol: str,
        stock_data: Dict[str, Any],
        circuit_breaker_active: bool = False
    ) -> ConfidenceScore:
        """
        Calculate confidence from a single stock data dict.
        
        Convenience method that extracts source information from 
        a standard stock data dictionary.
        
        Args:
            symbol: Stock symbol
            stock_data: Stock data dictionary with source info
            circuit_breaker_active: Whether circuit breaker is active
        
        Returns:
            ConfidenceScore
        """
        # Build source data list from stock_data
        source_data = []
        
        # Primary source
        primary_source = {
            "source": stock_data.get("source", "unknown"),
            "price": stock_data.get("price", 0),
            "volume": stock_data.get("volume", 0),
            "timestamp": stock_data.get("timestamp", datetime.now(timezone.utc).isoformat())
        }
        source_data.append(primary_source)
        
        # Check for additional source data in discrepancies or validation
        if "discrepancies" in stock_data:
            for field_disc in stock_data["discrepancies"]:
                if isinstance(field_disc, dict) and "values" in field_disc:
                    for src, val in field_disc["values"].items():
                        if src != primary_source["source"]:
                            source_data.append({
                                "source": src,
                                "price": val if field_disc.get("field") == "price" else primary_source["price"],
                                "volume": val if field_disc.get("field") == "volume" else primary_source["volume"],
                                "timestamp": primary_source["timestamp"]
                            })
        
        # Check for validation results with multiple source prices
        if "validation_results" in stock_data:
            vr = stock_data["validation_results"]
            if "ngx_price" in vr:
                source_data.append({
                    "source": "NGX",
                    "price": vr["ngx_price"],
                    "volume": primary_source["volume"],
                    "timestamp": primary_source["timestamp"]
                })
            if "tv_price" in vr:
                source_data.append({
                    "source": "TradingView",
                    "price": vr["tv_price"],
                    "volume": primary_source["volume"],
                    "timestamp": primary_source["timestamp"]
                })
        
        return self.calculate_confidence(
            symbol=symbol,
            source_data=source_data,
            circuit_breaker_active=circuit_breaker_active
        )
    
    def _calculate_price_agreement(
        self,
        source_data: List[Dict[str, Any]]
    ) -> Tuple[float, float]:
        """
        Calculate price agreement score across sources.
        
        Returns:
            Tuple of (agreement_score 0.0-1.0, variance_percent)
        """
        prices = [
            d.get("price", 0) 
            for d in source_data 
            if d.get("price") and d.get("price") > 0
        ]
        
        if len(prices) == 0:
            return 0.0, 100.0
        
        if len(prices) == 1:
            # Single source - moderate confidence
            source = source_data[0].get("source", "unknown")
            reliability = self.SOURCE_RELIABILITY.get(source, 0.5)
            return reliability, 0.0
        
        # Calculate variance
        avg_price = sum(prices) / len(prices)
        max_diff = max(abs(p - avg_price) for p in prices)
        variance_percent = (max_diff / avg_price * 100) if avg_price > 0 else 100.0
        
        # Score: 1.0 at 0% variance, decays exponentially
        # Score of 0.75 at 5% variance, 0.5 at ~10% variance
        score = max(0.0, 1.0 - (variance_percent / self.config.max_price_variance_percent) ** 0.5)
        
        return score, variance_percent
    
    def _calculate_volume_agreement(
        self,
        source_data: List[Dict[str, Any]]
    ) -> Tuple[float, float]:
        """
        Calculate volume agreement score across sources.
        
        Returns:
            Tuple of (agreement_score 0.0-1.0, variance_percent)
        """
        volumes = [
            d.get("volume", 0) 
            for d in source_data 
            if d.get("volume") and d.get("volume") > 0
        ]
        
        if len(volumes) == 0:
            return 0.5, 0.0  # No volume data - neutral score
        
        if len(volumes) == 1:
            # Single source - moderate confidence
            return 0.8, 0.0
        
        # Calculate variance
        avg_volume = sum(volumes) / len(volumes)
        max_diff = max(abs(v - avg_volume) for v in volumes)
        variance_percent = (max_diff / avg_volume * 100) if avg_volume > 0 else 100.0
        
        # Score: more tolerant than price (volume naturally varies more)
        score = max(0.0, 1.0 - (variance_percent / self.config.max_volume_variance_percent) ** 0.5)
        
        return score, variance_percent
    
    def _calculate_freshness(
        self,
        source_data: List[Dict[str, Any]]
    ) -> Tuple[float, float]:
        """
        Calculate data freshness score.
        
        Returns:
            Tuple of (freshness_score 0.0-1.0, oldest_data_age_seconds)
        """
        now = datetime.now(timezone.utc)
        ages = []
        
        for data in source_data:
            ts = data.get("timestamp")
            if ts is None:
                ages.append(self.config.max_data_age_minutes * 60)  # Assume stale if no timestamp
                continue
            
            if isinstance(ts, str):
                try:
                    # Handle ISO format timestamps
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00").replace("+00:00", ""))
                except ValueError:
                    ages.append(self.config.max_data_age_minutes * 60)
                    continue
            
            # Ensure both datetimes are tz-aware for subtraction
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_seconds = (now - ts).total_seconds()
            ages.append(max(0, age_seconds))
        
        if not ages:
            return 0.5, self.config.max_data_age_minutes * 60
        
        oldest_age = max(ages)
        max_age_seconds = self.config.max_data_age_minutes * 60
        
        # Score: 1.0 for fresh data, decays linearly to 0 at max_age
        score = max(0.0, 1.0 - (oldest_age / max_age_seconds))
        
        return score, oldest_age
    
    def _calculate_source_availability(
        self,
        source_data: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate source availability score based on number and reliability of sources.
        
        Returns:
            Score from 0.0-1.0
        """
        if not source_data:
            return 0.0
        
        # Get reliability-weighted score
        total_reliability = 0.0
        for data in source_data:
            source = data.get("source", "unknown")
            reliability = self.SOURCE_RELIABILITY.get(source, 0.5)
            total_reliability += reliability
        
        # Normalize: 1 source with 1.0 reliability = 0.7, 2+ high-reliability sources = 1.0
        base_score = min(1.0, total_reliability / 1.5)
        
        # Bonus for multiple sources
        if len(source_data) >= 2:
            base_score = min(1.0, base_score + 0.15)
        
        return base_score
    
    def _create_suppressed_score(
        self,
        symbol: str,
        reason: SuppressionReason,
        human_reason: str
    ) -> ConfidenceScore:
        """Create a suppressed score with a single critical reason."""
        return ConfidenceScore(
            symbol=symbol,
            overall_score=0.0,
            price_agreement_score=0.0,
            volume_agreement_score=0.0,
            freshness_score=0.0,
            source_availability_score=0.0,
            is_suppressed=True,
            suppression_reasons=[reason],
            human_readable_reason=human_reason,
            sources_used=[],
            price_variance_percent=0.0,
            volume_variance_percent=0.0,
            data_age_seconds=0.0
        )
    
    def update_config(self, **kwargs) -> None:
        """
        Update configuration parameters.
        
        Args:
            **kwargs: Parameters to update (must be valid ConfidenceScoreConfig fields)
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
            else:
                raise ValueError(f"Unknown config parameter: {key}")
        
        # Re-validate weights
        self.config.__post_init__()


# Singleton instance for easy access
_scorer_instance: Optional[DataConfidenceScorer] = None


def get_confidence_scorer(config: Optional[ConfidenceScoreConfig] = None) -> DataConfidenceScorer:
    """
    Get the singleton confidence scorer instance.
    
    Args:
        config: Optional configuration. Only used on first call.
    
    Returns:
        DataConfidenceScorer instance
    """
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = DataConfidenceScorer(config)
    return _scorer_instance
