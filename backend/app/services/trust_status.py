"""
Trust Status Service for NSE Trader (Phase 5).

Provides centralized, machine-readable and user-facing status indicators
for system health, data integrity, and operational readiness.

This service aggregates status from multiple subsystems to provide
a single source of truth for system trustworthiness.

Key Principles:
- Transparency over completeness
- Proactive limitation disclosure
- No hidden degradation
- Audit-clean presentation
"""
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class DataIntegrityLevel(str, Enum):
    """
    Overall data integrity classification.
    
    HIGH: All data sources operational, no stale data, no simulation
    MEDIUM: Minor issues (some stale data, partial coverage)
    DEGRADED: Significant issues affecting reliability
    """
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    DEGRADED = "DEGRADED"


class PerformanceReadiness(str, Enum):
    """Performance tracking system readiness."""
    READY = "READY"
    PARTIALLY_READY = "PARTIALLY_READY"
    NOT_READY = "NOT_READY"


@dataclass
class TrustStatus:
    """
    Aggregated system trust and health status.
    
    This is the single source of truth for system trustworthiness,
    intended for both programmatic consumption and user display.
    """
    # Core integrity indicators
    data_integrity: DataIntegrityLevel
    performance_readiness: PerformanceReadiness
    simulation_rate: float  # 0.0 = no simulation, 1.0 = all simulated
    stale_data_present: bool
    
    # Coverage summary
    symbols_with_history: int
    symbols_ready_for_trading: int
    total_historical_sessions: int
    
    # Timing information
    last_successful_ingestion: Optional[date]
    status_computed_at: datetime
    
    # Multi-source validation (Phase 6)
    validation_sources_count: int = 1
    validation_active: bool = False
    validation_agreement_rate: float = 0.0
    active_sources: List[str] = field(default_factory=list)
    
    # Human-readable notes for UI display
    notes: List[str] = field(default_factory=list)
    
    # Detailed breakdown for debugging/audit
    subsystem_status: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "data_integrity": self.data_integrity.value,
            "performance_readiness": self.performance_readiness.value,
            "simulation_rate": round(self.simulation_rate, 4),
            "stale_data_present": self.stale_data_present,
            "coverage": {
                "symbols_with_history": self.symbols_with_history,
                "symbols_ready_for_trading": self.symbols_ready_for_trading,
                "total_historical_sessions": self.total_historical_sessions,
            },
            "validation": {
                "sources_count": self.validation_sources_count,
                "active": self.validation_active,
                "agreement_rate": round(self.validation_agreement_rate, 3),
                "active_sources": self.active_sources,
            },
            "last_ingestion": self.last_successful_ingestion.isoformat() if self.last_successful_ingestion else None,
            "status_computed_at": self.status_computed_at.isoformat(),
            "notes": self.notes,
            "subsystem_status": self.subsystem_status,
        }
    
    def get_banner_message(self) -> str:
        """Get a user-facing banner message summarizing system status."""
        if self.data_integrity == DataIntegrityLevel.HIGH:
            if self.performance_readiness == PerformanceReadiness.READY:
                return "LIVE DATA – PERFORMANCE METRICS AVAILABLE"
            elif self.performance_readiness == PerformanceReadiness.PARTIALLY_READY:
                return "LIVE DATA – PERFORMANCE METRICS MATURING"
            else:
                return "LIVE DATA – INSUFFICIENT HISTORY FOR PERFORMANCE TRACKING"
        elif self.data_integrity == DataIntegrityLevel.MEDIUM:
            return "LIVE DATA – SOME LIMITATIONS APPLY (SEE NOTES)"
        else:
            return "DEGRADED DATA QUALITY – PROCEED WITH CAUTION"
    
    def get_integrity_explanation(self) -> str:
        """Get human-readable explanation of data integrity level."""
        explanations = {
            DataIntegrityLevel.HIGH: (
                "All data sources are operational. Historical data is fresh and validated. "
                "No simulated or estimated values are being used."
            ),
            DataIntegrityLevel.MEDIUM: (
                "Data is generally reliable but some limitations exist. "
                "Check notes for specific issues that may affect analysis."
            ),
            DataIntegrityLevel.DEGRADED: (
                "Significant data quality issues detected. "
                "Results may not be reliable. Review subsystem status for details."
            ),
        }
        return explanations.get(self.data_integrity, "Unknown status")


# Educational helper messages for various statuses
EDUCATIONAL_MESSAGES = {
    "NO_TRADE": {
        "what_this_means": (
            "The system has insufficient evidence to justify a trade. "
            "This is a protective outcome, not an error. "
            "NO_TRADE signals indicate the system is working correctly by "
            "refusing to make recommendations without adequate data support."
        ),
        "user_action": (
            "No action required. The system will generate actionable signals "
            "when sufficient data and clear market conditions are present."
        ),
    },
    "INSUFFICIENT_HISTORY": {
        "what_this_means": (
            "Not enough historical price data is available to compute "
            "reliable technical indicators. This is a data availability issue, "
            "not a system failure."
        ),
        "user_action": (
            "Wait for more historical data to be ingested, or check if "
            "historical ingestion has been run for this symbol."
        ),
    },
    "INSUFFICIENT_SAMPLE": {
        "what_this_means": (
            "There are not enough evaluated signals to compute statistically "
            "meaningful performance metrics. This is normal for new systems "
            "or symbols with limited trading history."
        ),
        "user_action": (
            "Performance metrics will become available as more signals are "
            "generated and evaluated over time. No action required."
        ),
    },
    "PARTIALLY_READY": {
        "what_this_means": (
            "Some symbols have sufficient historical data for analysis, "
            "while others do not. Performance metrics are available for "
            "ready symbols only."
        ),
        "user_action": (
            "You can use the system for symbols that are ready. Check the "
            "historical coverage endpoint to see which symbols are available."
        ),
    },
    "NOT_READY": {
        "what_this_means": (
            "No symbols currently have sufficient historical data for "
            "performance tracking. The system can still provide live price "
            "data and technical analysis, but forward performance metrics "
            "are not available."
        ),
        "user_action": (
            "Run historical data ingestion to enable performance tracking. "
            "See documentation for ingestion instructions."
        ),
    },
    "STALE_DATA": {
        "what_this_means": (
            "Historical data for this symbol has not been updated recently. "
            "Results may not reflect current market conditions."
        ),
        "user_action": (
            "Run historical ingestion to refresh data for this symbol."
        ),
    },
}


def get_educational_message(status_code: str) -> Dict[str, str]:
    """Get educational helper message for a status code."""
    return EDUCATIONAL_MESSAGES.get(status_code, {
        "what_this_means": f"Status: {status_code}",
        "user_action": "Consult documentation for more information.",
    })


class TrustStatusService:
    """
    Service for computing and providing system trust status.
    
    Aggregates status from:
    - Historical storage (data availability)
    - Coverage service (indicator readiness)
    - Performance service (evaluation readiness)
    - Provider chain (simulation rate)
    """
    
    def __init__(self):
        self._storage = None
        self._coverage_service = None
        self._performance_service = None
        self._validation_service = None
    
    def _get_storage(self):
        """Get storage instance (lazy-loaded)."""
        if self._storage is None:
            try:
                from app.data.historical.storage import get_historical_storage
                self._storage = get_historical_storage()
            except ImportError:
                logger.warning("Historical storage not available")
                self._storage = False
        return self._storage if self._storage else None
    
    def _get_coverage_service(self):
        """Get coverage service (lazy-loaded)."""
        if self._coverage_service is None:
            try:
                from app.services.historical_coverage import get_historical_coverage_service
                self._coverage_service = get_historical_coverage_service()
            except ImportError:
                logger.warning("Coverage service not available")
                self._coverage_service = False
        return self._coverage_service if self._coverage_service else None
    
    def _get_performance_service(self):
        """Get performance service (lazy-loaded)."""
        if self._performance_service is None:
            try:
                from app.services.performance_service import get_performance_service
                self._performance_service = get_performance_service()
            except ImportError:
                logger.warning("Performance service not available")
                self._performance_service = False
        return self._performance_service if self._performance_service else None
    
    def _get_validation_service(self):
        """Get validation service (lazy-loaded)."""
        if self._validation_service is None:
            try:
                from app.services.validation_service import get_validation_service
                self._validation_service = get_validation_service()
            except ImportError:
                logger.warning("Validation service not available")
                self._validation_service = False
        return self._validation_service if self._validation_service else None
    
    def get_trust_status(self) -> TrustStatus:
        """
        Compute and return current system trust status.
        
        Aggregates information from all subsystems to provide
        a comprehensive view of system health and reliability.
        """
        notes = []
        subsystem_status = {}
        
        # Get storage stats
        storage = self._get_storage()
        symbols_with_history = 0
        symbols_ready = 0
        total_sessions = 0
        stale_data_present = False
        last_ingestion = None
        
        if storage:
            try:
                stats = storage.get_stats()
                all_metadata = storage.get_all_metadata()
                
                symbols_with_history = stats.get("total_symbols", 0)
                total_sessions = stats.get("total_records", 0)
                
                # Count ready and stale symbols
                for m in all_metadata:
                    if m.total_sessions >= 50 and not m.is_stale():
                        symbols_ready += 1
                    if m.is_stale():
                        stale_data_present = True
                    if m.last_ingested_at:
                        ing_date = m.last_ingested_at.date()
                        if last_ingestion is None or ing_date > last_ingestion:
                            last_ingestion = ing_date
                
                subsystem_status["historical_storage"] = "OPERATIONAL"
            except Exception as e:
                logger.error("Error getting storage stats: %s", e)
                subsystem_status["historical_storage"] = f"ERROR: {e}"
        else:
            subsystem_status["historical_storage"] = "NOT_AVAILABLE"
            notes.append("Historical storage not initialized")
        
        # Determine performance readiness
        perf_service = self._get_performance_service()
        if perf_service:
            try:
                perf_status = perf_service.get_readiness_status()
                status_str = perf_status.get("status", "NOT_READY")
                performance_readiness = PerformanceReadiness(status_str)
                subsystem_status["performance"] = status_str
            except Exception as e:
                logger.error("Error getting performance status: %s", e)
                performance_readiness = PerformanceReadiness.NOT_READY
                subsystem_status["performance"] = f"ERROR: {e}"
        else:
            performance_readiness = PerformanceReadiness.NOT_READY
            subsystem_status["performance"] = "NOT_AVAILABLE"
        
        # Calculate simulation rate (currently 0 since we removed simulation)
        simulation_rate = 0.0
        subsystem_status["simulation"] = "DISABLED"
        
        # Determine overall data integrity
        if symbols_ready > 0 and not stale_data_present and simulation_rate == 0:
            data_integrity = DataIntegrityLevel.HIGH
        elif symbols_with_history > 0:
            data_integrity = DataIntegrityLevel.MEDIUM
            if stale_data_present:
                notes.append("Some historical data is stale and may not reflect current conditions")
        else:
            data_integrity = DataIntegrityLevel.DEGRADED
            notes.append("No historical data available - run ingestion to enable full functionality")
        
        # Add standard informational notes
        if performance_readiness == PerformanceReadiness.READY:
            notes.append("Performance metrics are forward-only (no backfilled results)")
        elif performance_readiness == PerformanceReadiness.PARTIALLY_READY:
            notes.append("Performance metrics available for some symbols only")
            notes.append("Early metrics may have small sample sizes")
        else:
            notes.append("Performance tracking requires historical data ingestion")
        
        # Get validation service status
        validation_sources_count = 1
        validation_active = False
        validation_agreement_rate = 0.0
        active_sources = []
        
        validation_service = self._get_validation_service()
        if validation_service:
            try:
                validation_sources_count = validation_service.get_sources_count()
                active_sources = validation_service.get_active_sources()
                
                summary = validation_service.get_validation_summary()
                if summary.get("available"):
                    validation_active = True
                    stats = summary.get("stats", {})
                    validation_agreement_rate = stats.get("agreement_rate", 0.0)
                    
                    sources_str = ", ".join(active_sources)
                    if validation_agreement_rate > 0.8:
                        notes.append(f"Multi-source validation active ({sources_str}) with high agreement")
                    elif validation_sources_count > 1:
                        notes.append(f"Multi-source validation active using {sources_str}")
                
                subsystem_status["validation"] = f"ACTIVE ({validation_sources_count} sources: {', '.join(active_sources)})"
            except Exception as e:
                logger.warning("Error getting validation status: %s", e)
                subsystem_status["validation"] = "ERROR"
        else:
            subsystem_status["validation"] = "NOT_AVAILABLE"
        
        return TrustStatus(
            data_integrity=data_integrity,
            performance_readiness=performance_readiness,
            simulation_rate=simulation_rate,
            stale_data_present=stale_data_present,
            symbols_with_history=symbols_with_history,
            symbols_ready_for_trading=symbols_ready,
            total_historical_sessions=total_sessions,
            last_successful_ingestion=last_ingestion,
            status_computed_at=datetime.now(timezone.utc),
            validation_sources_count=validation_sources_count,
            validation_active=validation_active,
            validation_agreement_rate=validation_agreement_rate,
            active_sources=active_sources,
            notes=notes,
            subsystem_status=subsystem_status,
        )


# Singleton instance
_service_instance: Optional[TrustStatusService] = None


def get_trust_status_service() -> TrustStatusService:
    """Get singleton trust status service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = TrustStatusService()
    return _service_instance
