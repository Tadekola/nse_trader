"""
Consolidated Data Confidence Module for NSE Trader.

Single authoritative source for all confidence scoring.

Two entry points:
1. validate_snapshot() — compare primary vs secondary price snapshots
2. score_recommendation_data() — score overall data quality for recommendation pipeline

Returns a unified ConfidenceScore with:
- overall_score (0.0–1.0)
- sub-scores (price_agreement, volume_agreement, freshness, source_availability)
- is_suppressed flag
- reason_codes list
- human_readable_reason
- provenance metadata
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ReasonCode(str, Enum):
    """Machine-readable reason codes for confidence outcomes."""
    LOW_OVERALL_CONFIDENCE = "LOW_OVERALL_CONFIDENCE"
    HIGH_PRICE_VARIANCE = "HIGH_PRICE_VARIANCE"
    HIGH_VOLUME_VARIANCE = "HIGH_VOLUME_VARIANCE"
    STALE_DATA = "STALE_DATA"
    INSUFFICIENT_SOURCES = "INSUFFICIENT_SOURCES"
    CIRCUIT_BREAKER_ACTIVE = "CIRCUIT_BREAKER_ACTIVE"
    PRICE_DIVERGENT = "PRICE_DIVERGENT"
    SECONDARY_MISSING = "SECONDARY_MISSING"
    SECONDARY_STALE = "SECONDARY_STALE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    GAPPY_HISTORY = "GAPPY_HISTORY"


class ConfidenceLevel(str, Enum):
    """Overall confidence tier."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    SUPPRESSED = "SUPPRESSED"


class ValidationStatus(str, Enum):
    """Status of secondary validation."""
    VALIDATED = "VALIDATED"
    DIVERGENT = "DIVERGENT"
    SECONDARY_MISSING = "SECONDARY_MISSING"
    SECONDARY_STALE = "SECONDARY_STALE"
    PRIMARY_ONLY = "PRIMARY_ONLY"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ConfidenceConfig:
    """All thresholds in one place."""
    # Suppression
    min_confidence_threshold: float = 0.75

    # Price agreement
    max_price_variance_percent: float = 5.0
    agreement_threshold_pct: float = 1.0
    minor_divergence_pct: float = 3.0
    major_divergence_pct: float = 5.0
    suppress_divergence_pct: float = 10.0

    # Volume
    max_volume_variance_percent: float = 20.0

    # Freshness
    max_data_age_minutes: int = 30
    staleness_hours: int = 24

    # Weights (must sum to 1.0)
    price_weight: float = 0.40
    volume_weight: float = 0.20
    freshness_weight: float = 0.20
    source_weight: float = 0.20

    # Bonuses / penalties for validation
    multi_source_bonus: float = 0.15
    agreement_bonus: float = 0.10
    divergence_penalty: float = 0.20
    base_single_source: float = 0.70
    base_validated: float = 0.85

    def __post_init__(self):
        total = self.price_weight + self.volume_weight + self.freshness_weight + self.source_weight
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")


# ---------------------------------------------------------------------------
# Source reliability table
# ---------------------------------------------------------------------------

SOURCE_RELIABILITY: Dict[str, float] = {
    "NGX": 0.95,
    "ngx_official": 0.95,
    "TradingView": 0.90,
    "kwayisi": 0.90,
    "KWAYISI": 0.90,
    "NGNMARKET": 0.95,
    "Simulated": 0.50,
    "simulated": 0.50,
    "cache": 0.85,
    "Registry": 0.80,
}


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of primary-vs-secondary price comparison."""
    symbol: str
    primary_price: float
    secondary_price: Optional[float]
    status: ValidationStatus
    confidence_level: ConfidenceLevel
    confidence_score: float
    price_difference: Optional[float] = None
    price_difference_percent: Optional[float] = None
    primary_timestamp: Optional[datetime] = None
    secondary_timestamp: Optional[datetime] = None
    validated_at: datetime = field(default_factory=datetime.utcnow)
    primary_source: str = "NGNMARKET"
    secondary_source: str = "KWAYISI"
    reason_codes: List[ReasonCode] = field(default_factory=list)

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
            "reason_codes": [r.value for r in self.reason_codes],
            "validated_at": self.validated_at.isoformat(),
        }


@dataclass
class ConfidenceScore:
    """
    Unified confidence score returned by all scoring paths.

    Every consumer sees the same shape; no more two-scorer ambiguity.
    """
    symbol: str
    overall_score: float
    confidence_level: ConfidenceLevel

    # Sub-scores
    price_agreement_score: float
    volume_agreement_score: float
    freshness_score: float
    source_availability_score: float

    # Governance
    is_suppressed: bool
    reason_codes: List[ReasonCode] = field(default_factory=list)
    human_readable_reason: Optional[str] = None

    # Provenance
    sources_used: List[str] = field(default_factory=list)
    primary_source: Optional[str] = None
    secondary_source: Optional[str] = None
    price_variance_percent: float = 0.0
    volume_variance_percent: float = 0.0
    data_age_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "confidence_score": round(self.overall_score, 4),
            "confidence_level": self.confidence_level.value,
            "status": "SUPPRESSED" if self.is_suppressed else "ACTIVE",
            "reason_codes": [r.value for r in self.reason_codes],
            "suppression_reason": self.human_readable_reason,
            "primary_source": self.primary_source,
            "secondary_source": self.secondary_source,
            "component_scores": {
                "price_agreement": round(self.price_agreement_score, 4),
                "volume_agreement": round(self.volume_agreement_score, 4),
                "freshness": round(self.freshness_score, 4),
                "source_availability": round(self.source_availability_score, 4),
            },
            "metrics": {
                "price_variance_percent": round(self.price_variance_percent, 2),
                "volume_variance_percent": round(self.volume_variance_percent, 2),
                "data_age_seconds": round(self.data_age_seconds, 1),
                "sources_used": self.sources_used,
            },
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# The ONE scorer
# ---------------------------------------------------------------------------

class DataConfidenceScorer:
    """
    Single authoritative confidence scorer.

    Entry points:
      validate()                   — primary vs secondary snapshot comparison
      calculate_confidence()       — multi-source confidence scoring for recommendations
    """

    def __init__(self, config: Optional[ConfidenceConfig] = None):
        self.config = config or ConfidenceConfig()

    # ------------------------------------------------------------------
    # Entry point 1: snapshot validation (replaces data_confidence.py)
    # ------------------------------------------------------------------

    def validate(
        self,
        primary: Any,  # PriceSnapshot
        secondary: Optional[Any] = None,  # PriceSnapshot
    ) -> ValidationResult:
        """Compare primary snapshot against optional secondary."""
        symbol = primary.symbol

        if secondary is None:
            return ValidationResult(
                symbol=symbol,
                primary_price=primary.price,
                secondary_price=None,
                status=ValidationStatus.PRIMARY_ONLY,
                confidence_level=ConfidenceLevel.MEDIUM,
                confidence_score=self.config.base_single_source,
                primary_timestamp=primary.timestamp,
                reason_codes=[ReasonCode.SECONDARY_MISSING],
            )

        # Staleness check
        if self._is_stale(secondary):
            return ValidationResult(
                symbol=symbol,
                primary_price=primary.price,
                secondary_price=secondary.price,
                status=ValidationStatus.SECONDARY_STALE,
                confidence_level=ConfidenceLevel.MEDIUM,
                confidence_score=self.config.base_single_source,
                primary_timestamp=primary.timestamp,
                secondary_timestamp=secondary.timestamp,
                reason_codes=[ReasonCode.SECONDARY_STALE],
            )

        divergence_pct = self._price_divergence(primary.price, secondary.price)
        status, level, score, reasons = self._score_divergence(divergence_pct)

        return ValidationResult(
            symbol=symbol,
            primary_price=primary.price,
            secondary_price=secondary.price,
            status=status,
            confidence_level=level,
            confidence_score=score,
            price_difference=round(primary.price - secondary.price, 4),
            price_difference_percent=divergence_pct,
            primary_timestamp=primary.timestamp,
            secondary_timestamp=secondary.timestamp,
            primary_source=(
                primary.source.value if hasattr(primary.source, "value") else str(primary.source)
            ),
            secondary_source=(
                secondary.source.value if hasattr(secondary.source, "value") else str(secondary.source)
            ),
            reason_codes=reasons,
        )

    # ------------------------------------------------------------------
    # Entry point 2: recommendation confidence (replaces confidence_scoring.py)
    # ------------------------------------------------------------------

    def calculate_confidence(
        self,
        symbol: str,
        source_data: List[Dict[str, Any]],
        circuit_breaker_active: bool = False,
    ) -> ConfidenceScore:
        """Score data quality from one or more sources."""
        symbol = symbol.upper()

        if circuit_breaker_active:
            return self._suppressed(
                symbol, ReasonCode.CIRCUIT_BREAKER_ACTIVE,
                f"Circuit breaker active for {symbol}.",
            )

        if not source_data:
            return self._suppressed(
                symbol, ReasonCode.INSUFFICIENT_SOURCES,
                f"No data sources available for {symbol}.",
            )

        sources_used = [d.get("source", "unknown") for d in source_data]

        price_score, price_var = self._calc_price_agreement(source_data)
        volume_score, vol_var = self._calc_volume_agreement(source_data)
        fresh_score, data_age = self._calc_freshness(source_data)
        src_score = self._calc_source_availability(source_data)

        cfg = self.config
        overall = (
            price_score * cfg.price_weight
            + volume_score * cfg.volume_weight
            + fresh_score * cfg.freshness_weight
            + src_score * cfg.source_weight
        )

        reasons: List[ReasonCode] = []
        human_parts: List[str] = []

        if overall < cfg.min_confidence_threshold:
            reasons.append(ReasonCode.LOW_OVERALL_CONFIDENCE)
            human_parts.append(
                f"Overall confidence ({overall:.1%}) below threshold ({cfg.min_confidence_threshold:.1%})"
            )
        if price_var > cfg.max_price_variance_percent:
            reasons.append(ReasonCode.HIGH_PRICE_VARIANCE)
            human_parts.append(f"Price variance {price_var:.1f}% exceeds {cfg.max_price_variance_percent:.1f}%")
        if vol_var > cfg.max_volume_variance_percent:
            reasons.append(ReasonCode.HIGH_VOLUME_VARIANCE)
            human_parts.append(f"Volume variance {vol_var:.1f}% exceeds {cfg.max_volume_variance_percent:.1f}%")
        if data_age > cfg.max_data_age_minutes * 60:
            reasons.append(ReasonCode.STALE_DATA)
            human_parts.append(f"Data {data_age / 60:.0f}min old (max {cfg.max_data_age_minutes}min)")
        if len(source_data) == 1 and src_score < 0.6:
            reasons.append(ReasonCode.INSUFFICIENT_SOURCES)
            human_parts.append(f"Single low-reliability source ({sources_used[0]})")

        is_suppressed = len(reasons) > 0
        human = "; ".join(human_parts) if human_parts else None
        level = self._level_from_score(overall, is_suppressed)

        if is_suppressed:
            logger.warning("Confidence suppressed for %s: %s", symbol, human)

        return ConfidenceScore(
            symbol=symbol,
            overall_score=overall,
            confidence_level=level,
            price_agreement_score=price_score,
            volume_agreement_score=volume_score,
            freshness_score=fresh_score,
            source_availability_score=src_score,
            is_suppressed=is_suppressed,
            reason_codes=reasons,
            human_readable_reason=human,
            sources_used=sources_used,
            primary_source=sources_used[0] if sources_used else None,
            secondary_source=sources_used[1] if len(sources_used) > 1 else None,
            price_variance_percent=price_var,
            volume_variance_percent=vol_var,
            data_age_seconds=data_age,
        )

    # ------------------------------------------------------------------
    # Internal: price agreement
    # ------------------------------------------------------------------

    def _calc_price_agreement(self, source_data: List[Dict[str, Any]]) -> Tuple[float, float]:
        prices = [d.get("price", 0) for d in source_data if d.get("price") and d["price"] > 0]
        if not prices:
            return 0.0, 100.0
        if len(prices) == 1:
            src = source_data[0].get("source", "unknown")
            return SOURCE_RELIABILITY.get(src, 0.5), 0.0
        avg = sum(prices) / len(prices)
        max_diff = max(abs(p - avg) for p in prices)
        var_pct = (max_diff / avg * 100) if avg > 0 else 100.0
        score = max(0.0, 1.0 - (var_pct / self.config.max_price_variance_percent) ** 0.5)
        return score, var_pct

    def _calc_volume_agreement(self, source_data: List[Dict[str, Any]]) -> Tuple[float, float]:
        volumes = [d.get("volume", 0) for d in source_data if d.get("volume") and d["volume"] > 0]
        if not volumes:
            return 0.5, 0.0
        if len(volumes) == 1:
            return 0.8, 0.0
        avg = sum(volumes) / len(volumes)
        max_diff = max(abs(v - avg) for v in volumes)
        var_pct = (max_diff / avg * 100) if avg > 0 else 100.0
        score = max(0.0, 1.0 - (var_pct / self.config.max_volume_variance_percent) ** 0.5)
        return score, var_pct

    def _calc_freshness(self, source_data: List[Dict[str, Any]]) -> Tuple[float, float]:
        now = datetime.utcnow()
        ages: List[float] = []
        for d in source_data:
            ts = d.get("timestamp")
            if ts is None:
                ages.append(self.config.max_data_age_minutes * 60)
                continue
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00").replace("+00:00", ""))
                except ValueError:
                    ages.append(self.config.max_data_age_minutes * 60)
                    continue
            ages.append(max(0, (now - ts).total_seconds()))
        if not ages:
            return 0.5, self.config.max_data_age_minutes * 60
        oldest = max(ages)
        max_secs = self.config.max_data_age_minutes * 60
        score = max(0.0, 1.0 - (oldest / max_secs))
        return score, oldest

    def _calc_source_availability(self, source_data: List[Dict[str, Any]]) -> float:
        if not source_data:
            return 0.0
        total_rel = sum(SOURCE_RELIABILITY.get(d.get("source", "unknown"), 0.5) for d in source_data)
        base = min(1.0, total_rel / 1.5)
        if len(source_data) >= 2:
            base = min(1.0, base + 0.15)
        return base

    # ------------------------------------------------------------------
    # Internal: divergence scoring for validate()
    # ------------------------------------------------------------------

    def _score_divergence(
        self, div_pct: float
    ) -> Tuple[ValidationStatus, ConfidenceLevel, float, List[ReasonCode]]:
        cfg = self.config
        if div_pct <= cfg.agreement_threshold_pct:
            return (
                ValidationStatus.VALIDATED, ConfidenceLevel.HIGH,
                min(1.0, cfg.base_validated + cfg.multi_source_bonus + cfg.agreement_bonus),
                [],
            )
        if div_pct <= cfg.minor_divergence_pct:
            return (
                ValidationStatus.VALIDATED, ConfidenceLevel.MEDIUM,
                cfg.base_validated + cfg.multi_source_bonus - cfg.divergence_penalty * 0.5,
                [],
            )
        if div_pct <= cfg.major_divergence_pct:
            return (
                ValidationStatus.DIVERGENT, ConfidenceLevel.MEDIUM,
                cfg.base_single_source,
                [ReasonCode.PRICE_DIVERGENT],
            )
        if div_pct <= cfg.suppress_divergence_pct:
            return (
                ValidationStatus.DIVERGENT, ConfidenceLevel.LOW,
                cfg.base_single_source - cfg.divergence_penalty,
                [ReasonCode.PRICE_DIVERGENT],
            )
        logger.warning("Extreme price divergence (%.1f%%) — suppressed", div_pct)
        return (
            ValidationStatus.DIVERGENT, ConfidenceLevel.SUPPRESSED, 0.0,
            [ReasonCode.PRICE_DIVERGENT],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _price_divergence(p1: float, p2: float) -> float:
        if p1 <= 0:
            return 0.0
        return abs(p1 - p2) / p1 * 100

    def _is_stale(self, snapshot: Any) -> bool:
        age = datetime.utcnow() - snapshot.timestamp
        return age > timedelta(hours=self.config.staleness_hours)

    @staticmethod
    def _level_from_score(score: float, suppressed: bool) -> ConfidenceLevel:
        if suppressed:
            return ConfidenceLevel.SUPPRESSED
        if score >= 0.85:
            return ConfidenceLevel.HIGH
        if score >= 0.60:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    def _suppressed(self, symbol: str, reason: ReasonCode, human: str) -> ConfidenceScore:
        return ConfidenceScore(
            symbol=symbol,
            overall_score=0.0,
            confidence_level=ConfidenceLevel.SUPPRESSED,
            price_agreement_score=0.0,
            volume_agreement_score=0.0,
            freshness_score=0.0,
            source_availability_score=0.0,
            is_suppressed=True,
            reason_codes=[reason],
            human_readable_reason=human,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_scorer_instance: Optional[DataConfidenceScorer] = None


def get_confidence_scorer(config: Optional[ConfidenceConfig] = None) -> DataConfidenceScorer:
    """Get singleton confidence scorer instance."""
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = DataConfidenceScorer(config)
    return _scorer_instance
