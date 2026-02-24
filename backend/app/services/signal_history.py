"""
Signal History Storage Module for NSE Trader.

Persists ACTIVE signals for post-hoc performance evaluation.
This is a read-only analytics store - results are NOT fed back into live signals.

Features:
- Deterministic signal_id hashing
- Signal persistence with full context
- Expiration tracking
- Thread-safe in-memory storage (can be extended to database)
"""
import hashlib
import logging
import threading
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)


class SignalStatus(str, Enum):
    """
    Status of a tracked signal for performance evaluation.
    
    Note: This is separate from SignalState (lifecycle state).
    SignalStatus tracks evaluation progress.
    SignalState (in signal_lifecycle.py) tracks signal validity.
    """
    PENDING = "pending"          # Awaiting evaluation
    EVALUATED = "evaluated"      # Performance calculated
    EXPIRED = "expired"          # Past evaluation window
    INVALIDATED = "invalidated"  # Data issue discovered


class SignalLifecycleState(str, Enum):
    """
    Signal lifecycle state for recommendation responses.
    
    ACTIVE: Valid signal within TTL, actionable
    SUPPRESSED: Signal suppressed due to data quality issues
    INVALID: Signal has expired (past TTL) or invalidated
    NO_TRADE: Explicit decision not to trade (first-class state)
    """
    ACTIVE = "active"
    SUPPRESSED = "suppressed"
    INVALID = "invalid"
    NO_TRADE = "no_trade"


@dataclass
class TrackedSignal:
    """
    A signal persisted for performance tracking.
    
    Attributes:
        signal_id: Deterministic hash uniquely identifying this signal
        symbol: Stock symbol
        bias_direction: bullish | neutral | bearish
        bias_probability: Probability 0-100 at time of signal
        regime: Market regime at time of signal
        regime_confidence: Confidence in regime classification
        data_confidence_score: Data quality score at signal time
        generated_at: When signal was generated
        expires_at: When signal evaluation window closes (optional)
        price_at_signal: Price when signal was generated
        horizon: Investment horizon (short_term, swing, long_term)
        
        # Forward performance (filled in by evaluator)
        price_1d: Price after 1 day
        price_5d: Price after 5 days
        price_20d: Price after 20 days
        return_1d: 1-day return percentage
        return_5d: 5-day return percentage
        return_20d: 20-day return percentage
        hit_1d: Whether direction was correct at 1d
        hit_5d: Whether direction was correct at 5d
        hit_20d: Whether direction was correct at 20d
        
        status: Current evaluation status
        evaluated_at: When performance was evaluated
    """
    signal_id: str
    symbol: str
    bias_direction: str
    bias_probability: int
    regime: str
    regime_confidence: float
    data_confidence_score: float
    generated_at: datetime
    price_at_signal: float
    horizon: str
    
    expires_at: Optional[datetime] = None
    
    # Forward performance fields (filled by evaluator)
    price_1d: Optional[float] = None
    price_5d: Optional[float] = None
    price_20d: Optional[float] = None
    return_1d: Optional[float] = None
    return_5d: Optional[float] = None
    return_20d: Optional[float] = None
    hit_1d: Optional[bool] = None
    hit_5d: Optional[bool] = None
    hit_20d: Optional[bool] = None
    
    status: SignalStatus = SignalStatus.PENDING
    evaluated_at: Optional[datetime] = None
    
    # Additional context
    pre_regime_probability: Optional[int] = None
    regime_adjustment_factor: Optional[float] = None
    indicator_agreement: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/API."""
        result = {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "bias_direction": self.bias_direction,
            "bias_probability": self.bias_probability,
            "regime": self.regime,
            "regime_confidence": round(self.regime_confidence, 3),
            "data_confidence_score": round(self.data_confidence_score, 3),
            "generated_at": self.generated_at.isoformat(),
            "price_at_signal": self.price_at_signal,
            "horizon": self.horizon,
            "status": self.status.value,
        }
        
        if self.expires_at:
            result["expires_at"] = self.expires_at.isoformat()
        
        # Add forward performance if evaluated
        if self.status == SignalStatus.EVALUATED:
            result["forward_performance"] = {
                "1d": {
                    "price": self.price_1d,
                    "return_pct": round(self.return_1d, 4) if self.return_1d else None,
                    "hit": self.hit_1d
                },
                "5d": {
                    "price": self.price_5d,
                    "return_pct": round(self.return_5d, 4) if self.return_5d else None,
                    "hit": self.hit_5d
                },
                "20d": {
                    "price": self.price_20d,
                    "return_pct": round(self.return_20d, 4) if self.return_20d else None,
                    "hit": self.hit_20d
                }
            }
            result["evaluated_at"] = self.evaluated_at.isoformat() if self.evaluated_at else None
        
        # Add context if available
        if self.pre_regime_probability is not None:
            result["pre_regime_probability"] = self.pre_regime_probability
        if self.regime_adjustment_factor is not None:
            result["regime_adjustment_factor"] = round(self.regime_adjustment_factor, 3)
        if self.indicator_agreement is not None:
            result["indicator_agreement"] = round(self.indicator_agreement, 3)
        
        return result


def generate_signal_id(
    symbol: str,
    bias_direction: str,
    generated_at: datetime,
    horizon: str
) -> str:
    """
    Generate a deterministic signal ID.
    
    The ID is a hash of the key signal attributes, ensuring
    the same signal always gets the same ID.
    
    Args:
        symbol: Stock symbol
        bias_direction: bullish | neutral | bearish
        generated_at: Signal generation timestamp
        horizon: Investment horizon
    
    Returns:
        Deterministic hex hash string
    """
    # Create canonical string for hashing
    canonical = f"{symbol.upper()}|{bias_direction.lower()}|{generated_at.isoformat()}|{horizon.lower()}"
    
    # Use SHA-256 truncated to 16 chars for readability
    hash_bytes = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    
    return f"sig_{hash_bytes}"


class SignalHistoryStore:
    """
    In-memory signal history store for performance tracking.
    
    Thread-safe storage for tracked signals. Can be extended
    to use a database backend for persistence.
    
    This is a READ-ONLY analytics store - data flows one way
    from signal generation to performance evaluation.
    """
    
    def __init__(self):
        self._signals: Dict[str, TrackedSignal] = {}
        self._lock = threading.RLock()
        self._by_symbol: Dict[str, List[str]] = {}  # symbol -> signal_ids
        self._by_regime: Dict[str, List[str]] = {}  # regime -> signal_ids
        self._by_direction: Dict[str, List[str]] = {}  # direction -> signal_ids
    
    def store_signal(
        self,
        symbol: str,
        bias_direction: str,
        bias_probability: int,
        regime: str,
        regime_confidence: float,
        data_confidence_score: float,
        price_at_signal: float,
        horizon: str,
        generated_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        pre_regime_probability: Optional[int] = None,
        regime_adjustment_factor: Optional[float] = None,
        indicator_agreement: Optional[float] = None
    ) -> TrackedSignal:
        """
        Store a new signal for tracking.
        
        Args:
            symbol: Stock symbol
            bias_direction: bullish | neutral | bearish
            bias_probability: Final adjusted probability (0-100)
            regime: Market regime at signal time
            regime_confidence: Confidence in regime classification
            data_confidence_score: Data quality score
            price_at_signal: Price when signal was generated
            horizon: Investment horizon
            generated_at: When signal was generated (defaults to now)
            expires_at: When signal evaluation window closes
            pre_regime_probability: Probability before regime adjustment
            regime_adjustment_factor: Regime adjustment multiplier
            indicator_agreement: Indicator agreement ratio
        
        Returns:
            The stored TrackedSignal
        """
        if generated_at is None:
            generated_at = datetime.utcnow()
        
        # Generate deterministic ID
        signal_id = generate_signal_id(symbol, bias_direction, generated_at, horizon)
        
        signal = TrackedSignal(
            signal_id=signal_id,
            symbol=symbol.upper(),
            bias_direction=bias_direction.lower(),
            bias_probability=bias_probability,
            regime=regime,
            regime_confidence=regime_confidence,
            data_confidence_score=data_confidence_score,
            generated_at=generated_at,
            price_at_signal=price_at_signal,
            horizon=horizon.lower(),
            expires_at=expires_at,
            pre_regime_probability=pre_regime_probability,
            regime_adjustment_factor=regime_adjustment_factor,
            indicator_agreement=indicator_agreement
        )
        
        with self._lock:
            # Store signal
            self._signals[signal_id] = signal
            
            # Update indices
            self._by_symbol.setdefault(symbol.upper(), []).append(signal_id)
            self._by_regime.setdefault(regime, []).append(signal_id)
            self._by_direction.setdefault(bias_direction.lower(), []).append(signal_id)
        
        logger.info(
            "Stored signal %s: %s %s @ %d%% (regime: %s)",
            signal_id, symbol, bias_direction, bias_probability, regime
        )
        
        return signal
    
    def get_signal(self, signal_id: str) -> Optional[TrackedSignal]:
        """Get a signal by ID."""
        with self._lock:
            return self._signals.get(signal_id)
    
    def get_signals_by_symbol(self, symbol: str) -> List[TrackedSignal]:
        """Get all signals for a symbol."""
        with self._lock:
            signal_ids = self._by_symbol.get(symbol.upper(), [])
            return [self._signals[sid] for sid in signal_ids if sid in self._signals]
    
    def get_signals_by_regime(self, regime: str) -> List[TrackedSignal]:
        """Get all signals generated under a specific regime."""
        with self._lock:
            signal_ids = self._by_regime.get(regime, [])
            return [self._signals[sid] for sid in signal_ids if sid in self._signals]
    
    def get_signals_by_direction(self, direction: str) -> List[TrackedSignal]:
        """Get all signals with a specific bias direction."""
        with self._lock:
            signal_ids = self._by_direction.get(direction.lower(), [])
            return [self._signals[sid] for sid in signal_ids if sid in self._signals]
    
    def get_pending_signals(self) -> List[TrackedSignal]:
        """Get all signals pending evaluation."""
        with self._lock:
            return [
                s for s in self._signals.values()
                if s.status == SignalStatus.PENDING
            ]
    
    def get_evaluated_signals(self) -> List[TrackedSignal]:
        """Get all signals that have been evaluated."""
        with self._lock:
            return [
                s for s in self._signals.values()
                if s.status == SignalStatus.EVALUATED
            ]
    
    def get_signals_in_range(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[TrackedSignal]:
        """Get signals generated within a date range."""
        with self._lock:
            return [
                s for s in self._signals.values()
                if start_date <= s.generated_at <= end_date
            ]
    
    def update_signal(self, signal: TrackedSignal):
        """Update a signal (used by evaluator to add performance data)."""
        with self._lock:
            if signal.signal_id in self._signals:
                self._signals[signal.signal_id] = signal
    
    def get_all_signals(self) -> List[TrackedSignal]:
        """Get all stored signals."""
        with self._lock:
            return list(self._signals.values())
    
    def count_signals(self) -> Dict[str, int]:
        """Get signal counts by status."""
        with self._lock:
            counts = {
                "total": len(self._signals),
                "pending": 0,
                "evaluated": 0,
                "expired": 0,
                "invalidated": 0
            }
            for signal in self._signals.values():
                counts[signal.status.value] += 1
            return counts
    
    def clear(self):
        """Clear all stored signals (for testing)."""
        with self._lock:
            self._signals.clear()
            self._by_symbol.clear()
            self._by_regime.clear()
            self._by_direction.clear()


# Singleton instance
_store_instance: Optional[SignalHistoryStore] = None


def get_signal_history_store() -> SignalHistoryStore:
    """Get singleton signal history store instance.
    
    Uses SQLite-backed PersistentSignalStore so signals survive restarts.
    Falls back to in-memory store if persistence layer fails.
    """
    global _store_instance
    if _store_instance is None:
        try:
            from app.services.signal_persistence import get_persistent_signal_store
            _store_instance = get_persistent_signal_store()
            logger.info("Using persistent (SQLite) signal store")
        except Exception as e:
            logger.warning("Persistent signal store unavailable, using in-memory: %s", e)
            _store_instance = SignalHistoryStore()
    return _store_instance
