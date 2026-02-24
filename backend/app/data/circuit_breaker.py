"""
Per-Source Circuit Breaker (P1-1).

Prevents hammering degraded sources and triggers Safe Mode when
all sources are unavailable.

States:
  CLOSED    — normal operation, calls pass through
  OPEN      — source is degraded, fast-fail all calls
  HALF_OPEN — probe window, limited calls allowed to test recovery

Policy:
  → OPEN if consecutive_failures >= failure_threshold
           OR error_rate > 50% in rolling window
  → HALF_OPEN after cooldown_seconds elapsed since OPEN
  → CLOSED if probe call succeeds in HALF_OPEN
  → back to OPEN if probe call fails in HALF_OPEN

Thread-safe in-memory state (acceptable for single-process deployments).
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerConfig:
    """Configuration for a single circuit breaker."""
    failure_threshold: int = 3          # consecutive failures to trip
    error_rate_threshold: float = 0.5   # 50% error rate to trip
    rolling_window_seconds: float = 300 # 5-minute rolling window
    cooldown_seconds: float = 60        # seconds before HALF_OPEN probe
    half_open_max_calls: int = 1        # max probe calls in HALF_OPEN


@dataclass
class BreakerSnapshot:
    """Observable snapshot of breaker state."""
    source: str
    state: CircuitState
    consecutive_failures: int
    total_calls: int
    total_failures: int
    error_rate: float
    last_failure_time: Optional[float]
    last_success_time: Optional[float]
    opened_at: Optional[float]
    state_changed_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "total_calls": self.total_calls,
            "total_failures": self.total_failures,
            "error_rate": round(self.error_rate, 3),
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "opened_at": self.opened_at,
        }


class CircuitBreaker:
    """
    Per-source circuit breaker with rolling window error tracking.

    Usage::

        breaker = CircuitBreaker("ngx_official")

        if not breaker.allow_request():
            return None  # fast-fail

        try:
            result = await fetch_from_source()
            breaker.record_success()
            return result
        except Exception:
            breaker.record_failure()
            raise
    """

    def __init__(self, source: str, config: Optional[CircuitBreakerConfig] = None):
        self.source = source
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._lock = Lock()

        # Counters
        self._consecutive_failures = 0
        self._half_open_calls = 0

        # Rolling window: deque of (timestamp, success: bool)
        self._window: deque = deque()

        # Timestamps
        self._opened_at: Optional[float] = None
        self._last_failure_time: Optional[float] = None
        self._last_success_time: Optional[float] = None
        self._state_changed_at: float = time.monotonic()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition()
            return self._state

    def allow_request(self) -> bool:
        """
        Check if a request should be allowed through.

        Returns True if the call may proceed, False if it should fast-fail.
        """
        with self._lock:
            self._maybe_transition()

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False

            # OPEN
            return False

    def record_success(self) -> None:
        """Record a successful call."""
        now = time.monotonic()
        with self._lock:
            self._window.append((now, True))
            self._prune_window(now)
            self._consecutive_failures = 0
            self._last_success_time = now

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.CLOSED)
                logger.info(
                    "Circuit breaker %s: HALF_OPEN → CLOSED (probe succeeded)",
                    self.source,
                )

    def record_failure(self) -> None:
        """Record a failed call."""
        now = time.monotonic()
        with self._lock:
            self._window.append((now, False))
            self._prune_window(now)
            self._consecutive_failures += 1
            self._last_failure_time = now

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    "Circuit breaker %s: HALF_OPEN → OPEN (probe failed)",
                    self.source,
                )
                return

            if self._state == CircuitState.CLOSED:
                if self._should_trip(now):
                    self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        "Circuit breaker %s: CLOSED → OPEN "
                        "(consecutive=%d, error_rate=%.1f%%)",
                        self.source,
                        self._consecutive_failures,
                        self._error_rate(now) * 100,
                    )

    def snapshot(self) -> BreakerSnapshot:
        """Get an observable snapshot of current state."""
        with self._lock:
            self._maybe_transition()
            now = time.monotonic()
            total, failures = self._window_counts(now)
            rate = failures / total if total > 0 else 0.0

            return BreakerSnapshot(
                source=self.source,
                state=self._state,
                consecutive_failures=self._consecutive_failures,
                total_calls=total,
                total_failures=failures,
                error_rate=rate,
                last_failure_time=self._last_failure_time,
                last_success_time=self._last_success_time,
                opened_at=self._opened_at,
                state_changed_at=self._state_changed_at,
            )

    def reset(self) -> None:
        """Force-reset to CLOSED (for testing / manual recovery)."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._consecutive_failures = 0
            self._window.clear()
            self._opened_at = None
            logger.info("Circuit breaker %s: force-reset to CLOSED", self.source)

    # ── internal ─────────────────────────────────────────────────────

    def _maybe_transition(self) -> None:
        """Auto-transition OPEN → HALF_OPEN if cooldown has elapsed."""
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.config.cooldown_seconds:
                self._transition_to(CircuitState.HALF_OPEN)
                self._half_open_calls = 0
                logger.info(
                    "Circuit breaker %s: OPEN → HALF_OPEN (cooldown %.0fs elapsed)",
                    self.source,
                    elapsed,
                )

    def _should_trip(self, now: float) -> bool:
        """Check if breaker should trip from CLOSED → OPEN."""
        if self._consecutive_failures >= self.config.failure_threshold:
            return True
        if self._error_rate(now) > self.config.error_rate_threshold:
            total, _ = self._window_counts(now)
            # Only trip on error rate if we have enough samples
            return total >= self.config.failure_threshold
        return False

    def _error_rate(self, now: float) -> float:
        total, failures = self._window_counts(now)
        return failures / total if total > 0 else 0.0

    def _window_counts(self, now: float) -> tuple:
        cutoff = now - self.config.rolling_window_seconds
        total = 0
        failures = 0
        for ts, success in self._window:
            if ts >= cutoff:
                total += 1
                if not success:
                    failures += 1
        return total, failures

    def _prune_window(self, now: float) -> None:
        cutoff = now - self.config.rolling_window_seconds
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def _transition_to(self, new_state: CircuitState) -> None:
        self._state = new_state
        self._state_changed_at = time.monotonic()
        if new_state == CircuitState.OPEN:
            self._opened_at = time.monotonic()
        elif new_state == CircuitState.CLOSED:
            self._opened_at = None
            self._half_open_calls = 0


# ── Registry ─────────────────────────────────────────────────────────


class CircuitBreakerRegistry:
    """
    Registry of per-source circuit breakers.

    Singleton: use get_breaker_registry().
    """

    def __init__(self, default_config: Optional[CircuitBreakerConfig] = None):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._default_config = default_config or CircuitBreakerConfig()
        self._lock = Lock()

    def get(self, source: str) -> CircuitBreaker:
        """Get or create a breaker for the given source."""
        with self._lock:
            if source not in self._breakers:
                self._breakers[source] = CircuitBreaker(
                    source, config=self._default_config
                )
            return self._breakers[source]

    def all_snapshots(self) -> List[BreakerSnapshot]:
        """Get snapshots of all registered breakers."""
        with self._lock:
            return [b.snapshot() for b in self._breakers.values()]

    def is_safe_mode(self, required_sources: Optional[List[str]] = None) -> bool:
        """
        Check if Safe Mode should be activated.

        Safe Mode = ALL required sources have OPEN circuit breakers.
        If no required_sources specified, checks all registered breakers.
        """
        with self._lock:
            if required_sources:
                sources = required_sources
            else:
                sources = list(self._breakers.keys())

            if not sources:
                return False

            for src in sources:
                if src in self._breakers:
                    breaker = self._breakers[src]
                    if breaker.state != CircuitState.OPEN:
                        return False
                else:
                    # Unregistered source = assumed available
                    return False

            return True

    def reset_all(self) -> None:
        """Reset all breakers (for testing)."""
        with self._lock:
            for b in self._breakers.values():
                b.reset()


# Singleton
_registry: Optional[CircuitBreakerRegistry] = None


def get_breaker_registry() -> CircuitBreakerRegistry:
    """Get the singleton breaker registry."""
    global _registry
    if _registry is None:
        _registry = CircuitBreakerRegistry()
    return _registry
