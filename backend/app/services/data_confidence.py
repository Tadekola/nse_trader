"""
Data Confidence Scorer for Multi-Source Validation.

Compares prices from primary (ngnmarket) and secondary (kwayisi) sources
to compute a confidence score for each data point.

Design Principles:
- Primary source is NEVER overridden
- No price averaging between sources
- Agreement boosts confidence
- Large divergence penalizes/suppresses
- Missing secondary is neutral (not penalized)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from enum import Enum

from app.market_data.providers.base import PriceSnapshot

logger = logging.getLogger(__name__)


class ValidationStatus(str, Enum):
    """Status of secondary validation."""
    VALIDATED = "VALIDATED"         # Sources agree within threshold
    DIVERGENT = "DIVERGENT"         # Sources disagree significantly
    SECONDARY_MISSING = "SECONDARY_MISSING"  # No secondary data available
    SECONDARY_STALE = "SECONDARY_STALE"      # Secondary data too old
    PRIMARY_ONLY = "PRIMARY_ONLY"   # No secondary validation attempted


class ConfidenceLevel(str, Enum):
    """Overall confidence level."""
    HIGH = "HIGH"           # Multi-source validated, agreement
    MEDIUM = "MEDIUM"       # Single source or minor divergence
    LOW = "LOW"             # Significant divergence or issues
    SUPPRESSED = "SUPPRESSED"  # Data too unreliable to use


@dataclass
class ValidationResult:
    """Result of validating primary data against secondary source."""
    symbol: str
    primary_price: float
    secondary_price: Optional[float]
    
    status: ValidationStatus
    confidence_level: ConfidenceLevel
    confidence_score: float  # 0.0 to 1.0
    
    # Divergence metrics
    price_difference: Optional[float] = None
    price_difference_percent: Optional[float] = None
    
    # Timestamps
    primary_timestamp: Optional[datetime] = None
    secondary_timestamp: Optional[datetime] = None
    validated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Sources
    primary_source: str = "NGNMARKET"
    secondary_source: str = "KWAYISI"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "validation_status": self.status.value,
            "confidence_level": self.confidence_level.value,
            "confidence_score": round(self.confidence_score, 3),
            "primary_price": self.primary_price,
            "secondary_price": self.secondary_price,
            "price_difference_percent": (
                round(self.price_difference_percent, 2) 
                if self.price_difference_percent is not None else None
            ),
            "sources": {
                "primary": self.primary_source,
                "secondary": self.secondary_source if self.secondary_price else None,
            },
            "validated_at": self.validated_at.isoformat(),
        }


@dataclass
class ConfidenceConfig:
    """Configuration for confidence scoring."""
    # Divergence thresholds (as percentages)
    agreement_threshold: float = 1.0      # < 1% = agreement
    minor_divergence: float = 3.0         # 1-3% = minor divergence
    major_divergence: float = 5.0         # 3-5% = major divergence
    suppress_threshold: float = 10.0      # > 10% = suppress
    
    # Confidence score adjustments
    multi_source_bonus: float = 0.15      # Bonus for having secondary validation
    agreement_bonus: float = 0.10         # Additional bonus for agreement
    divergence_penalty: float = 0.20      # Penalty for divergence
    
    # Base confidence scores
    base_single_source: float = 0.70      # Single source confidence
    base_validated: float = 0.85          # Validated confidence
    
    # Staleness threshold (hours)
    staleness_hours: int = 24


class DataConfidenceScorer:
    """
    Scores data confidence based on multi-source validation.
    
    Usage:
        scorer = DataConfidenceScorer()
        result = scorer.validate(primary_snapshot, secondary_snapshot)
        
        if result.confidence_level == ConfidenceLevel.HIGH:
            # Use data with high confidence
        elif result.confidence_level == ConfidenceLevel.SUPPRESSED:
            # Data too unreliable
    """
    
    def __init__(self, config: Optional[ConfidenceConfig] = None):
        self.config = config or ConfidenceConfig()
        self._validation_cache: Dict[str, ValidationResult] = {}
    
    def validate(
        self,
        primary: PriceSnapshot,
        secondary: Optional[PriceSnapshot] = None,
    ) -> ValidationResult:
        """
        Validate primary data against secondary source.
        
        Args:
            primary: Primary price snapshot (ngnmarket)
            secondary: Optional secondary snapshot (kwayisi)
            
        Returns:
            ValidationResult with confidence scoring
        """
        symbol = primary.symbol
        
        # No secondary data - return primary-only result
        if secondary is None:
            return self._create_primary_only_result(primary)
        
        # Check for staleness
        if self._is_stale(secondary):
            return self._create_stale_secondary_result(primary, secondary)
        
        # Calculate price divergence
        divergence_pct = self._calculate_divergence(primary.price, secondary.price)
        
        # Determine validation status and confidence
        status, confidence_level, confidence_score = self._score_validation(
            divergence_pct
        )
        
        result = ValidationResult(
            symbol=symbol,
            primary_price=primary.price,
            secondary_price=secondary.price,
            status=status,
            confidence_level=confidence_level,
            confidence_score=confidence_score,
            price_difference=round(primary.price - secondary.price, 4),
            price_difference_percent=divergence_pct,
            primary_timestamp=primary.timestamp,
            secondary_timestamp=secondary.timestamp,
            primary_source=primary.source.value if hasattr(primary.source, 'value') else str(primary.source),
            secondary_source=secondary.source.value if hasattr(secondary.source, 'value') else str(secondary.source),
        )
        
        # Cache result
        self._validation_cache[symbol] = result
        
        return result
    
    def validate_batch(
        self,
        primary_snapshots: Dict[str, PriceSnapshot],
        secondary_snapshots: Dict[str, PriceSnapshot],
    ) -> Dict[str, ValidationResult]:
        """
        Validate a batch of snapshots.
        
        Args:
            primary_snapshots: Dict of primary snapshots by symbol
            secondary_snapshots: Dict of secondary snapshots by symbol
            
        Returns:
            Dict of ValidationResults by symbol
        """
        results = {}
        
        for symbol, primary in primary_snapshots.items():
            secondary = secondary_snapshots.get(symbol)
            results[symbol] = self.validate(primary, secondary)
        
        return results
    
    def get_aggregate_stats(
        self,
        results: Dict[str, ValidationResult]
    ) -> Dict[str, Any]:
        """
        Get aggregate statistics from validation results.
        
        Returns:
            Dict with aggregate stats for reporting
        """
        if not results:
            return {
                "total": 0,
                "validated": 0,
                "divergent": 0,
                "secondary_missing": 0,
                "validation_rate": 0.0,
                "agreement_rate": 0.0,
                "avg_confidence": 0.0,
            }
        
        total = len(results)
        validated = sum(1 for r in results.values() if r.status == ValidationStatus.VALIDATED)
        divergent = sum(1 for r in results.values() if r.status == ValidationStatus.DIVERGENT)
        secondary_missing = sum(
            1 for r in results.values() 
            if r.status in (ValidationStatus.SECONDARY_MISSING, ValidationStatus.PRIMARY_ONLY)
        )
        
        confidence_scores = [r.confidence_score for r in results.values()]
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        
        with_secondary = total - secondary_missing
        agreement_rate = validated / with_secondary if with_secondary > 0 else 0.0
        
        return {
            "total": total,
            "validated": validated,
            "divergent": divergent,
            "secondary_missing": secondary_missing,
            "validation_rate": with_secondary / total if total > 0 else 0.0,
            "agreement_rate": agreement_rate,
            "avg_confidence": round(avg_confidence, 3),
            "confidence_distribution": {
                "high": sum(1 for r in results.values() if r.confidence_level == ConfidenceLevel.HIGH),
                "medium": sum(1 for r in results.values() if r.confidence_level == ConfidenceLevel.MEDIUM),
                "low": sum(1 for r in results.values() if r.confidence_level == ConfidenceLevel.LOW),
                "suppressed": sum(1 for r in results.values() if r.confidence_level == ConfidenceLevel.SUPPRESSED),
            }
        }
    
    def _calculate_divergence(self, primary_price: float, secondary_price: float) -> float:
        """Calculate percentage divergence between prices."""
        if primary_price <= 0:
            return 0.0
        return abs(primary_price - secondary_price) / primary_price * 100
    
    def _score_validation(
        self,
        divergence_pct: float
    ) -> tuple[ValidationStatus, ConfidenceLevel, float]:
        """
        Score validation based on divergence.
        
        Returns:
            Tuple of (status, confidence_level, confidence_score)
        """
        cfg = self.config
        
        if divergence_pct <= cfg.agreement_threshold:
            # Sources agree - high confidence
            return (
                ValidationStatus.VALIDATED,
                ConfidenceLevel.HIGH,
                min(1.0, cfg.base_validated + cfg.multi_source_bonus + cfg.agreement_bonus)
            )
        
        elif divergence_pct <= cfg.minor_divergence:
            # Minor divergence - still validated but medium confidence
            return (
                ValidationStatus.VALIDATED,
                ConfidenceLevel.MEDIUM,
                cfg.base_validated + cfg.multi_source_bonus - (cfg.divergence_penalty * 0.5)
            )
        
        elif divergence_pct <= cfg.major_divergence:
            # Major divergence - divergent status, medium confidence
            return (
                ValidationStatus.DIVERGENT,
                ConfidenceLevel.MEDIUM,
                cfg.base_single_source
            )
        
        elif divergence_pct <= cfg.suppress_threshold:
            # Severe divergence - low confidence
            return (
                ValidationStatus.DIVERGENT,
                ConfidenceLevel.LOW,
                cfg.base_single_source - cfg.divergence_penalty
            )
        
        else:
            # Extreme divergence - suppress
            logger.warning(
                f"Extreme price divergence ({divergence_pct:.1f}%) - data suppressed"
            )
            return (
                ValidationStatus.DIVERGENT,
                ConfidenceLevel.SUPPRESSED,
                0.0
            )
    
    def _create_primary_only_result(self, primary: PriceSnapshot) -> ValidationResult:
        """Create result when no secondary data is available."""
        return ValidationResult(
            symbol=primary.symbol,
            primary_price=primary.price,
            secondary_price=None,
            status=ValidationStatus.PRIMARY_ONLY,
            confidence_level=ConfidenceLevel.MEDIUM,
            confidence_score=self.config.base_single_source,
            primary_timestamp=primary.timestamp,
        )
    
    def _create_stale_secondary_result(
        self,
        primary: PriceSnapshot,
        secondary: PriceSnapshot
    ) -> ValidationResult:
        """Create result when secondary data is stale."""
        return ValidationResult(
            symbol=primary.symbol,
            primary_price=primary.price,
            secondary_price=secondary.price,
            status=ValidationStatus.SECONDARY_STALE,
            confidence_level=ConfidenceLevel.MEDIUM,
            confidence_score=self.config.base_single_source,
            primary_timestamp=primary.timestamp,
            secondary_timestamp=secondary.timestamp,
        )
    
    def _is_stale(self, snapshot: PriceSnapshot) -> bool:
        """Check if snapshot is too old."""
        from datetime import timedelta
        age = datetime.now(timezone.utc) - snapshot.timestamp
        return age > timedelta(hours=self.config.staleness_hours)
    
    def get_cached_result(self, symbol: str) -> Optional[ValidationResult]:
        """Get cached validation result for a symbol."""
        return self._validation_cache.get(symbol)
    
    def clear_cache(self):
        """Clear validation cache."""
        self._validation_cache.clear()


# Singleton instance
_scorer_instance: Optional[DataConfidenceScorer] = None


def get_confidence_scorer() -> DataConfidenceScorer:
    """Get singleton confidence scorer instance."""
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = DataConfidenceScorer()
    return _scorer_instance
