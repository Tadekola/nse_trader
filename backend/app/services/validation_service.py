"""
Multi-Source Validation Service.

Orchestrates parallel data fetching from primary and secondary sources,
performs validation, and provides confidence-scored results.

Design:
- Primary (ngnmarket) and secondary (NGX Official) fetch in parallel
- Secondary NEVER blocks primary rendering
- Validation results enhance confidence scoring
- Respects all Phase 0-5 safeguards
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from app.market_data.providers.base import PriceSnapshot, FetchResult
from app.market_data.providers.ngnmarket_provider import NgnMarketProvider
from app.market_data.providers.ngx_provider import NgxEquitiesPriceListProvider
from app.services.confidence import (
    DataConfidenceScorer,
    ValidationResult,
    ValidationStatus,
    ConfidenceLevel,
    get_confidence_scorer,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidatedSnapshot:
    """
    Price snapshot with validation metadata.
    
    Wraps the primary snapshot with confidence information
    from secondary validation.
    """
    snapshot: PriceSnapshot
    validation: Optional[ValidationResult] = None
    
    @property
    def is_validated(self) -> bool:
        """Check if snapshot was validated against secondary source."""
        return (
            self.validation is not None and 
            self.validation.status == ValidationStatus.VALIDATED
        )
    
    @property
    def confidence_level(self) -> ConfidenceLevel:
        """Get confidence level."""
        if self.validation:
            return self.validation.confidence_level
        return ConfidenceLevel.MEDIUM
    
    @property
    def confidence_score(self) -> float:
        """Get confidence score (0.0 to 1.0)."""
        if self.validation:
            return self.validation.confidence_score
        return 0.7  # Default single-source confidence
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        result = self.snapshot.to_dict()
        
        # Add validation metadata
        result["validation"] = {
            "is_validated": self.is_validated,
            "confidence_level": self.confidence_level.value,
            "confidence_score": round(self.confidence_score, 3),
            "sources_count": 2 if self.is_validated else 1,
        }
        
        if self.validation:
            result["validation"]["status"] = self.validation.status.value
            result["validation"]["primary_source"] = self.validation.primary_source
            result["validation"]["secondary_source"] = self.validation.secondary_source
            
            if self.validation.price_difference_percent is not None:
                result["validation"]["divergence_pct"] = round(
                    self.validation.price_difference_percent, 2
                )
        
        return result


@dataclass
class ValidationServiceResult:
    """Result from validation service fetch operation."""
    snapshots: Dict[str, ValidatedSnapshot] = field(default_factory=dict)
    
    # Timing metrics
    primary_fetch_ms: float = 0.0
    secondary_fetch_ms: float = 0.0
    total_time_ms: float = 0.0
    
    # Counts
    primary_count: int = 0
    secondary_count: int = 0
    validated_count: int = 0
    divergent_count: int = 0
    
    # Errors
    primary_error: Optional[str] = None
    secondary_error: Optional[str] = None
    
    @property
    def validation_rate(self) -> float:
        """Percentage of snapshots with secondary validation."""
        if self.primary_count == 0:
            return 0.0
        return self.secondary_count / self.primary_count
    
    @property
    def agreement_rate(self) -> float:
        """Percentage of validated snapshots that agree."""
        if self.secondary_count == 0:
            return 0.0
        return self.validated_count / self.secondary_count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get validation statistics."""
        return {
            "primary_count": self.primary_count,
            "secondary_count": self.secondary_count,
            "validated_count": self.validated_count,
            "divergent_count": self.divergent_count,
            "validation_rate": round(self.validation_rate, 3),
            "agreement_rate": round(self.agreement_rate, 3),
            "timing": {
                "primary_ms": round(self.primary_fetch_ms, 1),
                "secondary_ms": round(self.secondary_fetch_ms, 1),
                "total_ms": round(self.total_time_ms, 1),
            },
            "errors": {
                "primary": self.primary_error,
                "secondary": self.secondary_error,
            }
        }


class ValidationService:
    """
    Service for fetching and validating market data from multiple sources.
    
    Usage:
        service = ValidationService()
        result = await service.fetch_validated(["GTCO", "ZENITHBANK"])
        
        for symbol, validated in result.snapshots.items():
            print(f"{symbol}: {validated.confidence_level}")
    """
    
    def __init__(
        self,
        primary_provider: Optional[NgnMarketProvider] = None,
        secondary_provider: Optional[NgxEquitiesPriceListProvider] = None,
        confidence_scorer: Optional[DataConfidenceScorer] = None,
    ):
        self._primary = primary_provider or NgnMarketProvider()
        self._secondary = secondary_provider or NgxEquitiesPriceListProvider()
        self._scorer = confidence_scorer or get_confidence_scorer()
        
        # Caching
        self._last_result: Optional[ValidationServiceResult] = None
        self._last_fetch_time: Optional[datetime] = None
    
    async def fetch_validated(
        self,
        symbols: List[str],
        skip_secondary: bool = False,
    ) -> ValidationServiceResult:
        """
        Fetch and validate data for symbols.
        
        Args:
            symbols: List of stock symbols
            skip_secondary: If True, skip secondary validation
            
        Returns:
            ValidationServiceResult with validated snapshots
        """
        import time
        start_time = time.time()
        
        result = ValidationServiceResult()
        
        # Fetch from both sources in parallel
        if skip_secondary:
            primary_result = await self._primary.fetch_snapshot(symbols)
            secondary_result = FetchResult(success=False, source=self._secondary.source)
        else:
            primary_task = self._primary.fetch_snapshot(symbols)
            secondary_task = self._fetch_secondary_safe(symbols)
            
            primary_result, secondary_result = await asyncio.gather(
                primary_task,
                secondary_task,
            )
        
        result.primary_fetch_ms = primary_result.fetch_time_ms
        result.secondary_fetch_ms = secondary_result.fetch_time_ms if secondary_result else 0
        
        # Process primary results
        if not primary_result.success:
            result.primary_error = primary_result.error
            result.total_time_ms = (time.time() - start_time) * 1000
            return result
        
        result.primary_count = len(primary_result.snapshots)
        
        # Process secondary results
        secondary_snapshots = {}
        if secondary_result and secondary_result.success:
            secondary_snapshots = secondary_result.snapshots
            result.secondary_count = len(secondary_snapshots)
        elif secondary_result:
            result.secondary_error = secondary_result.error
        
        # Validate and create validated snapshots
        for symbol, primary_snapshot in primary_result.snapshots.items():
            secondary_snapshot = secondary_snapshots.get(symbol)
            
            # Validate
            validation = self._scorer.validate(primary_snapshot, secondary_snapshot)
            
            # Create validated snapshot
            validated = ValidatedSnapshot(
                snapshot=primary_snapshot,
                validation=validation,
            )
            
            result.snapshots[symbol] = validated
            
            # Update counts
            if validation.status == ValidationStatus.VALIDATED:
                result.validated_count += 1
            elif validation.status == ValidationStatus.DIVERGENT:
                result.divergent_count += 1
        
        result.total_time_ms = (time.time() - start_time) * 1000
        
        # Cache result
        self._last_result = result
        self._last_fetch_time = datetime.now(timezone.utc)
        
        # Log summary
        logger.info(
            f"Validation: {result.validated_count}/{result.primary_count} validated, "
            f"{result.divergent_count} divergent, "
            f"secondary coverage: {result.validation_rate:.1%}"
        )
        
        return result

    def fetch_validated_sync(
        self,
        symbols: List[str],
        skip_secondary: bool = False,
    ) -> ValidationServiceResult:
        """Synchronous wrapper for fetch_validated."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, 
                        self.fetch_validated(symbols, skip_secondary)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.fetch_validated(symbols, skip_secondary)
                )
        except RuntimeError:
            return asyncio.run(self.fetch_validated(symbols, skip_secondary))
    
    async def _fetch_secondary_safe(self, symbols: List[str]) -> Optional[FetchResult]:
        """
        Fetch from secondary source with error handling.
        
        Secondary failures should NEVER block primary data.
        """
        try:
            return await self._secondary.fetch_snapshot(symbols)
        except Exception as e:
            logger.warning(f"Secondary fetch failed (non-blocking): {e}")
            return FetchResult(
                success=False,
                error=str(e),
                source=self._secondary.source,
            )
    
    async def fetch_primary_only(self, symbols: List[str]) -> FetchResult:
        """
        Fetch from primary source only (for fast path).
        """
        return await self._primary.fetch_snapshot(symbols)
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """
        Get summary of last validation operation.
        """
        if not self._last_result:
            return {
                "available": False,
                "message": "No validation data available",
            }
        
        return {
            "available": True,
            "last_fetch": self._last_fetch_time.isoformat() if self._last_fetch_time else None,
            "stats": self._last_result.get_stats(),
        }
    
    def get_sources_count(self) -> int:
        """Get number of active data sources."""
        return len(self.get_active_sources())

    def get_active_sources(self) -> List[str]:
        """Get list of active data source names."""
        sources = [self._primary.name]
        if self._secondary.is_available():
            sources.append(self._secondary.name)
        return sources


# Singleton instance
_service_instance: Optional[ValidationService] = None


def get_validation_service() -> ValidationService:
    """Get singleton validation service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ValidationService()
    return _service_instance
