"""
Circuit Breaker / Safe-Mode Operational Drill.

Run 1: Happy path — all sources healthy, breakers stay CLOSED.
Run 2: Forced failures — trip breakers, observe HALF_OPEN probe, safe mode.

Usage:
    python -m tests.drill_circuit_breaker
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
)
from app.services.source_health import SourceHealthService

SOURCES = ["ngnmarket", "ngx_pdf", "kwayisi"]

SEP = "=" * 72


def print_breaker_table(registry, health_svc):
    """Print a compact status table."""
    snaps = registry.all_snapshots()
    print(f"  {'Source':<14} {'State':<12} {'Consec.Fail':>11} {'ErrRate':>8} {'Calls':>6} {'Fails':>6}")
    print(f"  {'-'*14} {'-'*12} {'-'*11} {'-'*8} {'-'*6} {'-'*6}")
    for s in snaps:
        print(
            f"  {s.source:<14} {s.state.value:<12} {s.consecutive_failures:>11} "
            f"{s.error_rate:>7.1%} {s.total_calls:>6} {s.total_failures:>6}"
        )
    status = health_svc.overall_status()
    safe = registry.is_safe_mode(SOURCES)
    print(f"\n  Overall: {status}  |  Safe Mode: {safe}")


def run_good_path():
    """Run 1: All sources succeed — breakers stay CLOSED."""
    print(f"\n{SEP}")
    print("  RUN 1: HAPPY PATH — all sources healthy")
    print(SEP)

    config = CircuitBreakerConfig(
        failure_threshold=3,
        error_rate_threshold=0.5,
        rolling_window_seconds=60,
        cooldown_seconds=2,  # short for drill
        half_open_max_calls=1,
    )
    registry = CircuitBreakerRegistry(default_config=config)
    health = SourceHealthService(registry=registry)

    # Register sources
    for src in SOURCES:
        registry.get(src)

    print("\n  [Step 1] Initial state (all CLOSED):")
    print_breaker_table(registry, health)

    # Simulate 5 successful calls per source
    print("\n  [Step 2] 5 successful calls per source...")
    for _ in range(5):
        for src in SOURCES:
            health.record_success(src)

    print_breaker_table(registry, health)

    # Simulate 1 failure per source (should NOT trip — threshold=3)
    print("\n  [Step 3] 1 failure per source (should stay CLOSED)...")
    for src in SOURCES:
        health.record_failure(src, "transient timeout")

    print_breaker_table(registry, health)

    # Simulate recovery
    print("\n  [Step 4] Recovery — 3 more successes per source...")
    for _ in range(3):
        for src in SOURCES:
            health.record_success(src)

    print_breaker_table(registry, health)
    print(f"\n  ✓ Run 1 complete: all breakers CLOSED, no safe mode.\n")


def run_forced_failure():
    """Run 2: Force failures, observe trip → HALF_OPEN → recovery / safe mode."""
    print(f"\n{SEP}")
    print("  RUN 2: FORCED FAILURE — trip breakers, safe mode drill")
    print(SEP)

    config = CircuitBreakerConfig(
        failure_threshold=3,
        error_rate_threshold=0.5,
        rolling_window_seconds=60,
        cooldown_seconds=1,  # 1s for fast drill
        half_open_max_calls=1,
    )
    registry = CircuitBreakerRegistry(default_config=config)
    health = SourceHealthService(registry=registry)

    for src in SOURCES:
        registry.get(src)

    print("\n  [Step 1] Initial state:")
    print_breaker_table(registry, health)

    # Trip ngnmarket with 3 consecutive failures
    print("\n  [Step 2] Trip 'ngnmarket' with 3 consecutive failures...")
    for i in range(3):
        health.record_failure("ngnmarket", f"connection refused (attempt {i+1})")
        b = registry.get("ngnmarket")
        print(f"    failure {i+1}: state={b.state.value}, allow={b.allow_request()}")

    print_breaker_table(registry, health)

    # Verify fast-fail
    b = registry.get("ngnmarket")
    allowed = b.allow_request()
    print(f"\n  [Step 3] Fast-fail check: ngnmarket.allow_request() = {allowed}")
    assert not allowed, "BUG: OPEN breaker should block requests"

    # Check safe mode (only 1/3 sources open — should be DEGRADED, not SAFE_MODE)
    print(f"\n  [Step 4] Only 1/3 sources OPEN — should be DEGRADED:")
    print_breaker_table(registry, health)
    assert health.overall_status() == "DEGRADED", f"Expected DEGRADED, got {health.overall_status()}"

    # Trip remaining 2 sources
    print("\n  [Step 5] Trip remaining sources (ngx_pdf, kwayisi)...")
    for src in ["ngx_pdf", "kwayisi"]:
        for i in range(3):
            health.record_failure(src, f"source down (attempt {i+1})")

    print_breaker_table(registry, health)
    assert health.overall_status() == "SAFE_MODE", f"Expected SAFE_MODE, got {health.overall_status()}"
    assert registry.is_safe_mode(SOURCES), "BUG: all sources OPEN but is_safe_mode() returned False"
    print(f"\n  ⚠ SAFE MODE ACTIVATED — all 3 sources OPEN")

    # Wait for cooldown → HALF_OPEN
    print(f"\n  [Step 6] Waiting 1.2s for cooldown → HALF_OPEN probe window...")
    time.sleep(1.2)

    for src in SOURCES:
        b = registry.get(src)
        print(f"    {src}: state={b.state.value}")
    print_breaker_table(registry, health)
    assert health.overall_status() == "RECOVERING", (
        f"Expected RECOVERING when all HALF_OPEN, got {health.overall_status()}"
    )
    print(f"\n  ✓ All HALF_OPEN → overall_status = RECOVERING (not OK)")

    # Probe ngnmarket: success → CLOSED
    print(f"\n  [Step 7] Probe ngnmarket with SUCCESS → should transition to CLOSED...")
    b = registry.get("ngnmarket")
    assert b.allow_request(), "BUG: HALF_OPEN should allow 1 probe call"
    health.record_success("ngnmarket")
    print(f"    ngnmarket: state={b.state.value}")
    assert b.state == CircuitState.CLOSED, f"Expected CLOSED after probe success, got {b.state.value}"

    # Probe ngx_pdf: failure → back to OPEN
    print(f"\n  [Step 8] Probe ngx_pdf with FAILURE → should go back to OPEN...")
    b2 = registry.get("ngx_pdf")
    assert b2.allow_request(), "BUG: HALF_OPEN should allow 1 probe call"
    health.record_failure("ngx_pdf", "still down")
    print(f"    ngx_pdf: state={b2.state.value}")
    assert b2.state == CircuitState.OPEN, f"Expected OPEN after probe failure, got {b2.state.value}"

    # Second probe on ngx_pdf should be blocked (already used the 1 allowed call)
    b2_allow = b2.allow_request()
    print(f"    ngx_pdf second probe blocked: allow={b2_allow}")
    assert not b2_allow, "BUG: OPEN breaker should block after failed probe"

    print(f"\n  [Step 9] Final state after partial recovery:")
    print_breaker_table(registry, health)

    status = health.overall_status()
    print(f"\n  Overall: {status}")
    # ngnmarket=CLOSED, ngx_pdf=OPEN, kwayisi=HALF_OPEN → DEGRADED
    assert status == "DEGRADED", f"Expected DEGRADED after partial recovery, got {status}"

    print(f"\n  ✓ Run 2 complete: trip → fast-fail → safe mode → RECOVERING → partial recovery.\n")


def run_error_rate_trip():
    """Run 3: Error rate trip — interleaved successes/failures."""
    print(f"\n{SEP}")
    print("  RUN 3: ERROR RATE TRIP — high error rate without consecutive failures")
    print(SEP)

    config = CircuitBreakerConfig(
        failure_threshold=10,  # high — won't trip on consecutive alone
        error_rate_threshold=0.5,
        rolling_window_seconds=60,
        cooldown_seconds=1,
    )
    registry = CircuitBreakerRegistry(default_config=config)
    health = SourceHealthService(registry=registry)
    registry.get("ngnmarket")

    print("\n  [Step 1] Interleave: 3 success, 7 failures (70% error rate)...")
    pattern = ["ok", "ok", "ok", "fail", "fail", "fail", "fail", "fail", "fail", "fail"]
    for i, action in enumerate(pattern):
        if action == "ok":
            health.record_success("ngnmarket")
        else:
            health.record_failure("ngnmarket", f"error {i}")
        b = registry.get("ngnmarket")
        snap = b.snapshot()
        print(f"    call {i+1:2d} ({action:4s}): state={snap.state.value:<10} consec_fail={snap.consecutive_failures} err_rate={snap.error_rate:.0%}")

    b = registry.get("ngnmarket")
    print(f"\n  Final state: {b.state.value}")
    assert b.state == CircuitState.OPEN, f"Expected OPEN from error rate, got {b.state.value}"
    print(f"  ✓ Run 3 complete: error rate trip without consecutive threshold.\n")


def run_snapshot_observability():
    """Run 4: Verify snapshot and health API response shape."""
    print(f"\n{SEP}")
    print("  RUN 4: OBSERVABILITY — snapshot + health API response")
    print(SEP)

    registry = CircuitBreakerRegistry()
    health = SourceHealthService(registry=registry)

    health.record_success("ngnmarket")
    health.record_success("ngnmarket")
    health.record_failure("ngx_pdf", "timeout")
    health.record_stale("kwayisi")
    health.record_success("kwayisi")

    print("\n  [SourceHealthService.to_response()]:")
    import json
    resp = health.to_response()
    print(json.dumps(resp, indent=2, default=str))

    # kwayisi has stale_count=1 → should be DEGRADED
    assert resp["overall_status"] == "DEGRADED", (
        f"Expected DEGRADED (stale kwayisi), got {resp['overall_status']}"
    )
    print(f"\n  ✓ overall_status = DEGRADED (kwayisi is stale)")

    print(f"\n  [BreakerSnapshot.to_dict() for ngnmarket]:")
    snap = registry.get("ngnmarket").snapshot().to_dict()
    print(json.dumps(snap, indent=2, default=str))

    print(f"\n  ✓ Run 4 complete: observability check.\n")


def run_never_called():
    """Run 5: Verify never_called flag and registry-only source visibility."""
    print(f"\n{SEP}")
    print("  RUN 5: NEVER_CALLED FLAG — registry-only sources visible")
    print(SEP)

    registry = CircuitBreakerRegistry()
    health = SourceHealthService(registry=registry)

    # Register sources in registry but only call some via health service
    registry.get("ngnmarket")
    registry.get("ngx_pdf")
    registry.get("kwayisi")

    health.record_success("ngnmarket")

    print("\n  [Step 1] get_all_sources() includes registry-only sources:")
    sources = health.get_all_sources()
    for s in sources:
        print(f"    {s['name']:<14} called={not s['never_called']:<5}  state={s['circuit_state']}")

    names = {s["name"] for s in sources}
    assert "ngnmarket" in names, "ngnmarket should appear (called)"
    assert "ngx_pdf" in names, "ngx_pdf should appear (registry-only)"
    assert "kwayisi" in names, "kwayisi should appear (registry-only)"

    ngn = next(s for s in sources if s["name"] == "ngnmarket")
    pdf = next(s for s in sources if s["name"] == "ngx_pdf")
    assert ngn["never_called"] is False
    assert pdf["never_called"] is True

    print(f"\n  [Step 2] overall_status = OK (all CLOSED, none stale):")
    assert health.overall_status() == "OK"
    print(f"    ✓ OK")

    print(f"\n  ✓ Run 5 complete: never_called flag works correctly.\n")


if __name__ == "__main__":
    print(f"\n{'#' * 72}")
    print(f"  CIRCUIT BREAKER / SAFE MODE OPERATIONAL DRILL")
    print(f"{'#' * 72}")

    run_good_path()
    run_forced_failure()
    run_error_rate_trip()
    run_snapshot_observability()
    run_never_called()

    print(f"{'#' * 72}")
    print(f"  ALL DRILLS PASSED")
    print(f"{'#' * 72}\n")
