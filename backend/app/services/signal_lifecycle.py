"""
Signal Lifecycle Governance Module for NSE Trader.

Manages signal states, TTL enforcement, and NO_TRADE decisions.
Ensures signals have explicit lifecycles and clear governance.

Signal States:
- ACTIVE: Valid signal within TTL, actionable
- SUPPRESSED: Signal suppressed due to data quality issues
- INVALID: Signal has expired (past TTL) or invalidated
- NO_TRADE: Explicit decision not to provide signal (first-class state)

NO_TRADE is triggered when:
- Data confidence < threshold
- Regime hostility exceeds limit
- Indicator agreement is weak
- Calibration confidence is low
"""
import logging
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class SignalState(str, Enum):
    """
    Signal lifecycle states.
    
    ACTIVE: Valid signal within TTL, can be acted upon
    SUPPRESSED: Data quality issues prevent confident signal
    INVALID: Signal has expired or been invalidated
    NO_TRADE: Explicit decision not to trade (first-class state)
    """
    ACTIVE = "active"
    SUPPRESSED = "suppressed"
    INVALID = "invalid"
    NO_TRADE = "no_trade"


class NoTradeReason(str, Enum):
    """Reasons for NO_TRADE decision."""
    LOW_DATA_CONFIDENCE = "low_data_confidence"
    HOSTILE_REGIME = "hostile_regime"
    WEAK_INDICATOR_AGREEMENT = "weak_indicator_agreement"
    LOW_CALIBRATION_CONFIDENCE = "low_calibration_confidence"
    CONFLICTING_SIGNALS = "conflicting_signals"
    EXTREME_VOLATILITY = "extreme_volatility"
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"
    MULTIPLE_FACTORS = "multiple_factors"
    # Phase 2: Insufficient historical data
    INSUFFICIENT_HISTORY = "insufficient_history"


@dataclass
class NoTradeDecision:
    """
    Records a NO_TRADE decision for analysis.
    
    NO_TRADE is a first-class state representing an explicit,
    informed decision NOT to provide a trading signal.
    """
    symbol: str
    timestamp: datetime
    reasons: List[NoTradeReason]
    primary_reason: NoTradeReason
    human_readable: str
    
    # Context at decision time
    data_confidence: Optional[float] = None
    regime: Optional[str] = None
    regime_confidence: Optional[float] = None
    indicator_agreement: Optional[float] = None
    calibration_confidence: Optional[float] = None
    
    # Thresholds that triggered NO_TRADE
    thresholds_breached: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/API."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "state": SignalState.NO_TRADE.value,
            "reasons": [r.value for r in self.reasons],
            "primary_reason": self.primary_reason.value,
            "human_readable": self.human_readable,
            "context": {
                "data_confidence": self.data_confidence,
                "regime": self.regime,
                "regime_confidence": self.regime_confidence,
                "indicator_agreement": self.indicator_agreement,
                "calibration_confidence": self.calibration_confidence
            },
            "thresholds_breached": {
                k: {"actual": v[0], "threshold": v[1]}
                for k, v in self.thresholds_breached.items()
            }
        }


@dataclass
class LifecycleConfig:
    """Configuration for signal lifecycle governance."""
    # TTL settings (in hours)
    default_ttl_hours: int = 24
    short_term_ttl_hours: int = 8
    swing_ttl_hours: int = 72
    long_term_ttl_hours: int = 168  # 7 days
    
    # NO_TRADE thresholds
    min_data_confidence: float = 0.70
    min_indicator_agreement: float = 0.40
    min_calibration_confidence: float = 0.50
    max_regime_hostility: float = 0.70  # 1 - regime_confidence
    
    # Regime-specific hostility thresholds
    hostile_regimes: Dict[str, float] = field(default_factory=lambda: {
        "news_driven": 0.60,      # Lower threshold = easier to trigger NO_TRADE
        "high_volatility": 0.65,
        "low_liquidity": 0.60
    })


@dataclass
class SignalLifecycleResult:
    """
    Result of lifecycle evaluation.
    
    Contains the determined state and all context needed
    for the recommendation response.
    """
    state: SignalState
    expires_at: datetime
    is_valid: bool
    
    # NO_TRADE specific
    no_trade_decision: Optional[NoTradeDecision] = None
    
    # Suppression specific
    suppression_reason: Optional[str] = None
    
    # General
    reasoning: str = ""
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "state": self.state.value,
            "expires_at": self.expires_at.isoformat(),
            "is_valid": self.is_valid,
            "reasoning": self.reasoning,
            "warnings": self.warnings
        }
        
        if self.no_trade_decision:
            result["no_trade_decision"] = self.no_trade_decision.to_dict()
        
        if self.suppression_reason:
            result["suppression_reason"] = self.suppression_reason
        
        return result


class SignalLifecycleManager:
    """
    Manages signal lifecycle, TTL enforcement, and NO_TRADE decisions.
    
    Responsibilities:
    1. Assign TTL to every signal based on horizon
    2. Evaluate conditions for NO_TRADE state
    3. Mark expired signals as INVALID
    4. Log NO_TRADE decisions for analysis
    """
    
    def __init__(self, config: Optional[LifecycleConfig] = None):
        self.config = config or LifecycleConfig()
        self._no_trade_log: List[NoTradeDecision] = []
        self._lock = threading.RLock()
    
    def calculate_expiry(
        self,
        horizon: str,
        generated_at: Optional[datetime] = None
    ) -> datetime:
        """
        Calculate signal expiry time based on horizon.
        
        Every signal MUST have an expires_at timestamp.
        
        Args:
            horizon: Investment horizon (short_term, swing, long_term)
            generated_at: When signal was generated (defaults to now)
        
        Returns:
            Expiry datetime
        """
        if generated_at is None:
            generated_at = datetime.utcnow()
        
        horizon_lower = horizon.lower()
        
        if horizon_lower == "short_term":
            ttl_hours = self.config.short_term_ttl_hours
        elif horizon_lower == "swing":
            ttl_hours = self.config.swing_ttl_hours
        elif horizon_lower == "long_term":
            ttl_hours = self.config.long_term_ttl_hours
        else:
            ttl_hours = self.config.default_ttl_hours
        
        return generated_at + timedelta(hours=ttl_hours)
    
    def is_expired(self, expires_at: datetime) -> bool:
        """Check if a signal has expired."""
        return datetime.utcnow() > expires_at
    
    def evaluate_lifecycle(
        self,
        symbol: str,
        horizon: str,
        data_confidence: float,
        indicator_agreement: float,
        regime: str,
        regime_confidence: float,
        bias_probability: int,
        is_suppressed: bool = False,
        suppression_reason: Optional[str] = None,
        calibration_confidence: Optional[float] = None,
        generated_at: Optional[datetime] = None
    ) -> SignalLifecycleResult:
        """
        Evaluate signal lifecycle and determine final state.
        
        State determination priority:
        1. If already suppressed → SUPPRESSED
        2. If NO_TRADE conditions met → NO_TRADE
        3. Otherwise → ACTIVE
        
        Args:
            symbol: Stock symbol
            horizon: Investment horizon
            data_confidence: Data quality confidence score
            indicator_agreement: Proportion of indicators agreeing
            regime: Current market regime
            regime_confidence: Confidence in regime classification
            bias_probability: Final bias probability (0-100)
            is_suppressed: Whether already suppressed by data quality
            suppression_reason: Reason for suppression if applicable
            calibration_confidence: Historical calibration confidence
            generated_at: When signal was generated
        
        Returns:
            SignalLifecycleResult with determined state
        """
        if generated_at is None:
            generated_at = datetime.utcnow()
        
        expires_at = self.calculate_expiry(horizon, generated_at)
        
        # If already suppressed, maintain that state
        if is_suppressed:
            return SignalLifecycleResult(
                state=SignalState.SUPPRESSED,
                expires_at=expires_at,
                is_valid=False,
                suppression_reason=suppression_reason,
                reasoning=(
                    f"Signal suppressed due to data quality issues. "
                    f"Reason: {suppression_reason or 'Unspecified'}"
                )
            )
        
        # Check for NO_TRADE conditions
        no_trade_result = self._evaluate_no_trade(
            symbol=symbol,
            data_confidence=data_confidence,
            indicator_agreement=indicator_agreement,
            regime=regime,
            regime_confidence=regime_confidence,
            bias_probability=bias_probability,
            calibration_confidence=calibration_confidence or 0.5
        )
        
        if no_trade_result:
            # Log the NO_TRADE decision (in-memory + durable DB)
            self._log_no_trade(no_trade_result)
            self._persist_no_trade_async(no_trade_result)
            
            return SignalLifecycleResult(
                state=SignalState.NO_TRADE,
                expires_at=expires_at,
                is_valid=False,
                no_trade_decision=no_trade_result,
                reasoning=no_trade_result.human_readable,
                warnings=[
                    f"NO_TRADE: {r.value}" for r in no_trade_result.reasons
                ]
            )
        
        # Signal is ACTIVE
        warnings = self._generate_warnings(
            data_confidence=data_confidence,
            indicator_agreement=indicator_agreement,
            regime=regime,
            regime_confidence=regime_confidence
        )
        
        return SignalLifecycleResult(
            state=SignalState.ACTIVE,
            expires_at=expires_at,
            is_valid=True,
            reasoning=(
                f"Signal is active and valid until {expires_at.isoformat()}. "
                f"Data confidence: {data_confidence:.0%}, "
                f"Indicator agreement: {indicator_agreement:.0%}"
            ),
            warnings=warnings
        )
    
    def _evaluate_no_trade(
        self,
        symbol: str,
        data_confidence: float,
        indicator_agreement: float,
        regime: str,
        regime_confidence: float,
        bias_probability: int,
        calibration_confidence: float
    ) -> Optional[NoTradeDecision]:
        """
        Evaluate whether NO_TRADE state should be triggered.
        
        Returns NoTradeDecision if NO_TRADE, None if ACTIVE.
        """
        reasons: List[NoTradeReason] = []
        thresholds_breached: Dict[str, Tuple[float, float]] = {}
        
        # Check data confidence
        if data_confidence < self.config.min_data_confidence:
            reasons.append(NoTradeReason.LOW_DATA_CONFIDENCE)
            thresholds_breached["data_confidence"] = (
                data_confidence, self.config.min_data_confidence
            )
        
        # Check indicator agreement
        if indicator_agreement < self.config.min_indicator_agreement:
            reasons.append(NoTradeReason.WEAK_INDICATOR_AGREEMENT)
            thresholds_breached["indicator_agreement"] = (
                indicator_agreement, self.config.min_indicator_agreement
            )
        
        # Check calibration confidence
        if calibration_confidence < self.config.min_calibration_confidence:
            reasons.append(NoTradeReason.LOW_CALIBRATION_CONFIDENCE)
            thresholds_breached["calibration_confidence"] = (
                calibration_confidence, self.config.min_calibration_confidence
            )
        
        # Check regime hostility
        regime_hostility = 1.0 - regime_confidence
        regime_threshold = self.config.hostile_regimes.get(
            regime, self.config.max_regime_hostility
        )
        
        if regime_hostility > regime_threshold:
            reasons.append(NoTradeReason.HOSTILE_REGIME)
            thresholds_breached["regime_hostility"] = (
                regime_hostility, regime_threshold
            )
        
        # Check for hostile regime types
        if regime in ["news_driven", "high_volatility", "low_liquidity"]:
            specific_threshold = self.config.hostile_regimes.get(regime, 0.70)
            if regime_confidence < (1 - specific_threshold):
                if NoTradeReason.HOSTILE_REGIME not in reasons:
                    reasons.append(NoTradeReason.HOSTILE_REGIME)
                
                if regime == "news_driven":
                    reasons.append(NoTradeReason.EXTREME_VOLATILITY)
                elif regime == "low_liquidity":
                    reasons.append(NoTradeReason.INSUFFICIENT_LIQUIDITY)
        
        # If no reasons, signal is ACTIVE
        if not reasons:
            return None
        
        # Determine primary reason
        if len(reasons) > 2:
            primary_reason = NoTradeReason.MULTIPLE_FACTORS
        else:
            primary_reason = reasons[0]
        
        # Generate human-readable explanation
        human_readable = self._generate_no_trade_explanation(
            symbol=symbol,
            reasons=reasons,
            thresholds_breached=thresholds_breached,
            regime=regime
        )
        
        return NoTradeDecision(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            reasons=reasons,
            primary_reason=primary_reason,
            human_readable=human_readable,
            data_confidence=data_confidence,
            regime=regime,
            regime_confidence=regime_confidence,
            indicator_agreement=indicator_agreement,
            calibration_confidence=calibration_confidence,
            thresholds_breached=thresholds_breached
        )
    
    def _generate_no_trade_explanation(
        self,
        symbol: str,
        reasons: List[NoTradeReason],
        thresholds_breached: Dict[str, Tuple[float, float]],
        regime: str
    ) -> str:
        """Generate human-readable NO_TRADE explanation."""
        explanations = []
        
        if NoTradeReason.LOW_DATA_CONFIDENCE in reasons:
            actual, threshold = thresholds_breached.get("data_confidence", (0, 0))
            explanations.append(
                f"Data confidence ({actual:.0%}) is below the minimum threshold ({threshold:.0%})"
            )
        
        if NoTradeReason.WEAK_INDICATOR_AGREEMENT in reasons:
            actual, threshold = thresholds_breached.get("indicator_agreement", (0, 0))
            explanations.append(
                f"Indicator agreement ({actual:.0%}) shows conflicting signals"
            )
        
        if NoTradeReason.LOW_CALIBRATION_CONFIDENCE in reasons:
            actual, threshold = thresholds_breached.get("calibration_confidence", (0, 0))
            explanations.append(
                f"Historical calibration ({actual:.0%}) suggests unreliable predictions"
            )
        
        if NoTradeReason.HOSTILE_REGIME in reasons:
            explanations.append(
                f"Current market regime ({regime}) presents elevated uncertainty"
            )
        
        if NoTradeReason.EXTREME_VOLATILITY in reasons:
            explanations.append(
                "Market volatility is too extreme for reliable signal generation"
            )
        
        if NoTradeReason.INSUFFICIENT_LIQUIDITY in reasons:
            explanations.append(
                "Market liquidity is insufficient for safe execution"
            )
        
        if not explanations:
            explanations.append("Multiple factors indicate elevated uncertainty")
        
        prefix = f"NO_TRADE for {symbol}: "
        if len(explanations) == 1:
            return prefix + explanations[0] + "."
        else:
            return prefix + "; ".join(explanations) + "."
    
    def _generate_warnings(
        self,
        data_confidence: float,
        indicator_agreement: float,
        regime: str,
        regime_confidence: float
    ) -> List[str]:
        """Generate warnings for ACTIVE signals that are near thresholds."""
        warnings = []
        
        # Warn if approaching thresholds
        if data_confidence < self.config.min_data_confidence + 0.10:
            warnings.append(
                f"Data confidence ({data_confidence:.0%}) is approaching minimum threshold"
            )
        
        if indicator_agreement < self.config.min_indicator_agreement + 0.15:
            warnings.append(
                f"Indicator agreement ({indicator_agreement:.0%}) is relatively weak"
            )
        
        if regime in ["news_driven", "high_volatility"]:
            warnings.append(
                f"Elevated uncertainty due to {regime.replace('_', ' ')} market conditions"
            )
        
        return warnings
    
    def _log_no_trade(self, decision: NoTradeDecision):
        """Log NO_TRADE decision for analysis."""
        with self._lock:
            self._no_trade_log.append(decision)
        
        # Also log to standard logger
        logger.info(
            "NO_TRADE decision for %s: %s (reasons: %s)",
            decision.symbol,
            decision.primary_reason.value,
            [r.value for r in decision.reasons]
        )

    def _persist_no_trade_async(self, decision: NoTradeDecision):
        """Fire-and-forget persistence of NO_TRADE to PostgreSQL."""
        import asyncio

        async def _persist():
            try:
                from app.services.audit import get_audit_service
                audit = get_audit_service()
                await audit.record_no_trade(
                    symbol=decision.symbol,
                    reason_code=decision.primary_reason.value,
                    detail=decision.human_readable,
                    confidence=decision.data_confidence,
                    provenance={
                        "regime": decision.regime,
                        "regime_confidence": decision.regime_confidence,
                        "indicator_agreement": decision.indicator_agreement,
                        "calibration_confidence": decision.calibration_confidence,
                        "thresholds_breached": {
                            k: {"actual": v[0], "threshold": v[1]}
                            for k, v in decision.thresholds_breached.items()
                        },
                        "reasons": [r.value for r in decision.reasons],
                    },
                )
            except Exception as e:
                logger.error("Failed to persist NO_TRADE to DB: %s", e)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_persist())
        except RuntimeError:
            # No running loop — skip DB persistence (e.g. in sync tests)
            logger.debug("No event loop — skipping NO_TRADE DB persistence")
    
    def get_no_trade_log(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[NoTradeDecision]:
        """
        Get logged NO_TRADE decisions for analysis.
        
        Args:
            symbol: Filter by symbol
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum records to return
        
        Returns:
            List of NoTradeDecision records
        """
        with self._lock:
            result = list(self._no_trade_log)
        
        if symbol:
            result = [d for d in result if d.symbol == symbol.upper()]
        
        if start_date:
            result = [d for d in result if d.timestamp >= start_date]
        
        if end_date:
            result = [d for d in result if d.timestamp <= end_date]
        
        # Sort by timestamp descending and limit
        result.sort(key=lambda x: x.timestamp, reverse=True)
        return result[:limit]
    
    def get_no_trade_stats(self) -> Dict[str, Any]:
        """Get statistics on NO_TRADE decisions."""
        with self._lock:
            decisions = list(self._no_trade_log)
        
        if not decisions:
            return {
                "total": 0,
                "by_reason": {},
                "by_regime": {}
            }
        
        by_reason: Dict[str, int] = {}
        by_regime: Dict[str, int] = {}
        
        for d in decisions:
            # Count by primary reason
            reason_key = d.primary_reason.value
            by_reason[reason_key] = by_reason.get(reason_key, 0) + 1
            
            # Count by regime
            if d.regime:
                by_regime[d.regime] = by_regime.get(d.regime, 0) + 1
        
        return {
            "total": len(decisions),
            "by_reason": by_reason,
            "by_regime": by_regime,
            "most_common_reason": max(by_reason.keys(), key=lambda k: by_reason[k]) if by_reason else None
        }
    
    def validate_signal_state(
        self,
        current_state: str,
        expires_at: datetime
    ) -> Tuple[SignalState, bool]:
        """
        Validate and potentially update signal state.
        
        Used to check if an existing signal is still valid.
        
        Args:
            current_state: Current state string
            expires_at: Signal expiry time
        
        Returns:
            Tuple of (new_state, is_valid)
        """
        # Check expiry first
        if self.is_expired(expires_at):
            return SignalState.INVALID, False
        
        # Parse current state
        try:
            state = SignalState(current_state.lower())
        except ValueError:
            return SignalState.INVALID, False
        
        # Invalid signals stay invalid
        if state == SignalState.INVALID:
            return SignalState.INVALID, False
        
        # NO_TRADE and SUPPRESSED are not valid for trading
        if state in [SignalState.NO_TRADE, SignalState.SUPPRESSED]:
            return state, False
        
        # ACTIVE signals are valid
        return state, True
    
    def clear_log(self):
        """Clear NO_TRADE log (for testing)."""
        with self._lock:
            self._no_trade_log.clear()


# Singleton instance
_lifecycle_manager: Optional[SignalLifecycleManager] = None


def get_lifecycle_manager(
    config: Optional[LifecycleConfig] = None
) -> SignalLifecycleManager:
    """Get singleton lifecycle manager instance."""
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = SignalLifecycleManager(config)
    return _lifecycle_manager
