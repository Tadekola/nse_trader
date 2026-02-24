"""
Tests for Circuit Breaker (P1-1).

Covers:
  1. CLOSED → OPEN on consecutive failures
  2. CLOSED → OPEN on error rate threshold
  3. OPEN fast-fails (allow_request returns False)
  4. OPEN → HALF_OPEN after cooldown
  5. HALF_OPEN → CLOSED on probe success
  6. HALF_OPEN → OPEN on probe failure
  7. Registry: get/create, all_snapshots, is_safe_mode
  8. Safe Mode: all sources OPEN triggers safe mode
  9. Snapshot observability
"""

import sys
import os
import time
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
    BreakerSnapshot,
)


@pytest.fixture
def config():
    return CircuitBreakerConfig(
        failure_threshold=3,
        error_rate_threshold=0.5,
        rolling_window_seconds=60,
        cooldown_seconds=5,
        half_open_max_calls=1,
    )


@pytest.fixture
def breaker(config):
    return CircuitBreaker("test_source", config=config)


# ── 1. State transitions ────────────────────────────────────────────


class TestStateTransitions:

    def test_starts_closed(self, breaker):
        assert breaker.state == CircuitState.CLOSED

    def test_closed_allows_requests(self, breaker):
        assert breaker.allow_request() is True

    def test_consecutive_failures_trip_to_open(self, breaker):
        """3 consecutive failures → OPEN."""
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_open_blocks_requests(self, breaker):
        """OPEN state fast-fails."""
        for _ in range(3):
            breaker.record_failure()
        assert breaker.allow_request() is False

    def test_success_resets_consecutive_failures(self):
        """A success between failures resets the counter."""
        # Use high error_rate_threshold so only consecutive count matters
        cfg = CircuitBreakerConfig(
            failure_threshold=3,
            error_rate_threshold=0.99,
            rolling_window_seconds=60,
            cooldown_seconds=5,
        )
        b = CircuitBreaker("test", config=cfg)
        b.record_failure()
        b.record_failure()
        b.record_success()  # resets counter
        b.record_failure()
        # Only 1 consecutive failure, not 3 → still CLOSED
        assert b.state == CircuitState.CLOSED

    def test_open_to_half_open_after_cooldown(self, config):
        """After cooldown, OPEN transitions to HALF_OPEN."""
        config.cooldown_seconds = 0.1  # 100ms for fast test
        b = CircuitBreaker("test", config=config)

        for _ in range(3):
            b.record_failure()
        assert b.state == CircuitState.OPEN

        time.sleep(0.15)
        assert b.state == CircuitState.HALF_OPEN

    def test_half_open_allows_probe(self, config):
        """HALF_OPEN allows exactly 1 probe call."""
        config.cooldown_seconds = 0.05
        b = CircuitBreaker("test", config=config)

        for _ in range(3):
            b.record_failure()
        time.sleep(0.1)

        assert b.allow_request() is True   # probe allowed
        assert b.allow_request() is False  # second blocked

    def test_half_open_to_closed_on_success(self, config):
        """Probe success in HALF_OPEN → CLOSED."""
        config.cooldown_seconds = 0.05
        b = CircuitBreaker("test", config=config)

        for _ in range(3):
            b.record_failure()
        time.sleep(0.1)

        b.allow_request()
        b.record_success()
        assert b.state == CircuitState.CLOSED
        assert b.allow_request() is True

    def test_half_open_to_open_on_failure(self, config):
        """Probe failure in HALF_OPEN → back to OPEN."""
        config.cooldown_seconds = 0.05
        b = CircuitBreaker("test", config=config)

        for _ in range(3):
            b.record_failure()
        time.sleep(0.1)

        b.allow_request()
        b.record_failure()
        assert b.state == CircuitState.OPEN


# ── 2. Error rate threshold ──────────────────────────────────────────


class TestErrorRate:

    def test_error_rate_trips_breaker(self):
        """High error rate trips even without consecutive failures."""
        config = CircuitBreakerConfig(
            failure_threshold=10,  # high threshold so consecutive won't trip
            error_rate_threshold=0.5,
            rolling_window_seconds=60,
            cooldown_seconds=5,
        )
        b = CircuitBreaker("test", config=config)

        # Interleave successes and failures: 7 failures, 3 successes = 70% error
        for i in range(10):
            if i % 3 == 0 and i < 9:
                b.record_success()
            else:
                b.record_failure()

        assert b.state == CircuitState.OPEN


# ── 3. Snapshot observability ────────────────────────────────────────


class TestSnapshot:

    def test_snapshot_structure(self, breaker):
        breaker.record_success()
        breaker.record_failure()

        snap = breaker.snapshot()
        assert isinstance(snap, BreakerSnapshot)
        assert snap.source == "test_source"
        assert snap.state == CircuitState.CLOSED
        assert snap.consecutive_failures == 1
        assert snap.total_calls == 2
        assert snap.total_failures == 1
        assert 0.4 < snap.error_rate < 0.6

    def test_snapshot_to_dict(self, breaker):
        d = breaker.snapshot().to_dict()
        assert d["source"] == "test_source"
        assert d["state"] == "CLOSED"
        assert isinstance(d["error_rate"], float)

    def test_reset(self, breaker):
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.allow_request() is True


# ── 4. Registry ──────────────────────────────────────────────────────


class TestRegistry:

    def test_get_creates_breaker(self):
        reg = CircuitBreakerRegistry()
        b = reg.get("source_a")
        assert isinstance(b, CircuitBreaker)
        assert b.source == "source_a"

    def test_get_returns_same_instance(self):
        reg = CircuitBreakerRegistry()
        b1 = reg.get("source_a")
        b2 = reg.get("source_a")
        assert b1 is b2

    def test_all_snapshots(self):
        reg = CircuitBreakerRegistry()
        reg.get("src1").record_success()
        reg.get("src2").record_failure()

        snaps = reg.all_snapshots()
        assert len(snaps) == 2
        sources = {s.source for s in snaps}
        assert sources == {"src1", "src2"}


# ── 5. Safe Mode ─────────────────────────────────────────────────────


class TestSafeMode:

    def test_safe_mode_false_when_any_source_closed(self):
        reg = CircuitBreakerRegistry(
            default_config=CircuitBreakerConfig(failure_threshold=2)
        )
        b1 = reg.get("src1")
        b2 = reg.get("src2")

        # Trip src1
        b1.record_failure()
        b1.record_failure()

        # src2 still CLOSED
        assert reg.is_safe_mode() is False

    def test_safe_mode_true_when_all_sources_open(self):
        reg = CircuitBreakerRegistry(
            default_config=CircuitBreakerConfig(failure_threshold=2)
        )
        b1 = reg.get("src1")
        b2 = reg.get("src2")

        for b in [b1, b2]:
            b.record_failure()
            b.record_failure()

        assert reg.is_safe_mode() is True

    def test_safe_mode_with_required_sources(self):
        reg = CircuitBreakerRegistry(
            default_config=CircuitBreakerConfig(failure_threshold=2)
        )
        b1 = reg.get("src1")
        b2 = reg.get("src2")
        b3 = reg.get("src3")

        # Only trip src1 and src2
        for b in [b1, b2]:
            b.record_failure()
            b.record_failure()

        # All of [src1, src2] are OPEN → safe mode for those
        assert reg.is_safe_mode(required_sources=["src1", "src2"]) is True
        # src3 is still CLOSED → not safe mode for all
        assert reg.is_safe_mode() is False

    def test_safe_mode_false_no_breakers(self):
        reg = CircuitBreakerRegistry()
        assert reg.is_safe_mode() is False

    def test_reset_all_clears_safe_mode(self):
        reg = CircuitBreakerRegistry(
            default_config=CircuitBreakerConfig(failure_threshold=2)
        )
        for src in ["s1", "s2"]:
            b = reg.get(src)
            b.record_failure()
            b.record_failure()

        assert reg.is_safe_mode() is True
        reg.reset_all()
        assert reg.is_safe_mode() is False
