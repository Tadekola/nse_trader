"""
Tests for Source Health Dashboard (P1-3).

Covers:
  1. SourceHealthService — record_success, record_failure, record_stale
  2. Overall status computation — OK, RECOVERING, DEGRADED, SAFE_MODE
  3. API endpoint response structure + never_called flag
  4. Integration with CircuitBreakerRegistry
  5. Staleness → DEGRADED
  6. Registry-only sources appear in get_all_sources
"""

import sys
import os
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
)
from app.services.source_health import SourceHealthService


@pytest.fixture
def registry():
    return CircuitBreakerRegistry(
        default_config=CircuitBreakerConfig(
            failure_threshold=3,
            error_rate_threshold=0.99,
            rolling_window_seconds=60,
            cooldown_seconds=60,
        )
    )


@pytest.fixture
def svc(registry):
    return SourceHealthService(registry=registry)


# ── 1. Recording events ─────────────────────────────────────────────


class TestRecordEvents:

    def test_record_success(self, svc):
        svc.record_success("src_a")
        h = svc.get_source("src_a")
        assert h["total_calls"] == 1
        assert h["total_failures"] == 0
        assert h["consecutive_failures"] == 0
        assert h["last_success"] is not None
        assert h["error_rate"] == 0.0

    def test_record_failure(self, svc):
        svc.record_failure("src_a", "timeout")
        h = svc.get_source("src_a")
        assert h["total_calls"] == 1
        assert h["total_failures"] == 1
        assert h["consecutive_failures"] == 1
        assert h["last_error"] is not None
        assert h["last_error_message"] == "timeout"
        assert h["error_rate"] == 1.0

    def test_record_stale(self, svc):
        svc.record_stale("src_a")
        h = svc.get_source("src_a")
        assert h["stale_count"] == 1

    def test_success_resets_consecutive_failures(self, svc):
        svc.record_failure("src_a")
        svc.record_failure("src_a")
        svc.record_success("src_a")
        h = svc.get_source("src_a")
        assert h["consecutive_failures"] == 0
        assert h["total_failures"] == 2
        assert h["total_calls"] == 3

    def test_error_rate_calculation(self, svc):
        for _ in range(3):
            svc.record_success("src_a")
        svc.record_failure("src_a")
        h = svc.get_source("src_a")
        assert h["error_rate"] == 0.25


# ── 2. Overall status ───────────────────────────────────────────────


class TestOverallStatus:

    def test_ok_when_no_sources(self, svc):
        assert svc.overall_status() == "OK"

    def test_ok_when_all_healthy(self, svc):
        svc.record_success("src_a")
        svc.record_success("src_b")
        assert svc.overall_status() == "OK"

    def test_degraded_when_one_source_open(self, svc, registry):
        svc.record_success("src_a")
        # Trip src_b
        for _ in range(3):
            svc.record_failure("src_b")
        assert registry.get("src_b").state == CircuitState.OPEN
        assert svc.overall_status() == "DEGRADED"

    def test_safe_mode_when_all_open(self, svc, registry):
        for _ in range(3):
            svc.record_failure("src_a")
            svc.record_failure("src_b")
        assert svc.overall_status() == "SAFE_MODE"

    def test_recovering_when_half_open(self, registry):
        """HALF_OPEN sources → RECOVERING (not OK)."""
        cfg = CircuitBreakerConfig(
            failure_threshold=2,
            error_rate_threshold=0.99,
            rolling_window_seconds=60,
            cooldown_seconds=0.05,
        )
        reg = CircuitBreakerRegistry(default_config=cfg)
        svc = SourceHealthService(registry=reg)
        svc.record_success("src_a")
        # Trip src_b
        svc.record_failure("src_b")
        svc.record_failure("src_b")
        assert reg.get("src_b").state == CircuitState.OPEN
        assert svc.overall_status() == "DEGRADED"
        # Wait for cooldown → HALF_OPEN
        import time
        time.sleep(0.1)
        assert reg.get("src_b").state == CircuitState.HALF_OPEN
        assert svc.overall_status() == "RECOVERING"

    def test_degraded_when_stale(self, svc):
        """Staleness alone triggers DEGRADED even if all breakers CLOSED."""
        svc.record_success("src_a")
        svc.record_stale("src_a")
        assert svc.overall_status() == "DEGRADED"

    def test_degraded_not_recovering_when_open_and_half_open(self):
        """If any source is OPEN, status is DEGRADED even if others are HALF_OPEN."""
        cfg = CircuitBreakerConfig(
            failure_threshold=2,
            error_rate_threshold=0.99,
            rolling_window_seconds=60,
            cooldown_seconds=0.05,
        )
        reg = CircuitBreakerRegistry(default_config=cfg)
        svc = SourceHealthService(registry=reg)
        # Trip both
        for src in ["src_a", "src_b"]:
            svc.record_failure(src)
            svc.record_failure(src)
        # Wait for cooldown so both go HALF_OPEN
        import time
        time.sleep(0.1)
        assert reg.get("src_a").state == CircuitState.HALF_OPEN
        # Recover src_a
        reg.get("src_a").record_success()
        assert reg.get("src_a").state == CircuitState.CLOSED
        # Re-trip src_a to OPEN
        svc.record_failure("src_a")
        svc.record_failure("src_a")
        assert reg.get("src_a").state == CircuitState.OPEN
        # src_b is HALF_OPEN, src_a is OPEN → DEGRADED (not RECOVERING)
        assert svc.overall_status() == "DEGRADED"


# ── 3. get_all_sources / to_response ────────────────────────────────


class TestResponse:

    def test_get_all_sources_sorted(self, svc):
        svc.record_success("zebra")
        svc.record_success("alpha")
        sources = svc.get_all_sources()
        assert sources[0]["name"] == "alpha"
        assert sources[1]["name"] == "zebra"

    def test_never_called_flag(self, svc):
        svc.record_success("active_src")
        h_active = svc.get_source("active_src")
        assert h_active["never_called"] is False
        # Source registered in registry but never called via health service
        svc._registry.get("ghost_src")
        h_ghost = svc.get_source("ghost_src")
        assert h_ghost["never_called"] is True

    def test_registry_only_sources_in_get_all(self, svc, registry):
        """Sources registered only in the registry appear in get_all_sources."""
        svc.record_success("called_src")
        registry.get("registry_only_src")
        sources = svc.get_all_sources()
        names = {s["name"] for s in sources}
        assert "called_src" in names
        assert "registry_only_src" in names
        ghost = next(s for s in sources if s["name"] == "registry_only_src")
        assert ghost["never_called"] is True
        assert ghost["circuit_state"] == "CLOSED"

    def test_to_response_structure(self, svc):
        svc.record_success("src_a")
        resp = svc.to_response()
        assert "overall_status" in resp
        assert "sources" in resp
        assert "checked_at" in resp
        assert resp["overall_status"] == "OK"
        assert len(resp["sources"]) == 1

    def test_circuit_state_in_response(self, svc):
        svc.record_success("src_a")
        resp = svc.to_response()
        assert resp["sources"][0]["circuit_state"] == "CLOSED"

    def test_circuit_state_reflects_breaker(self, svc, registry):
        for _ in range(3):
            svc.record_failure("src_a")
        resp = svc.to_response()
        assert resp["sources"][0]["circuit_state"] == "OPEN"
        assert resp["overall_status"] == "SAFE_MODE"


# ── 4. API endpoint (unit test via direct function call) ─────────────


class TestEndpoint:

    @pytest.mark.asyncio
    async def test_get_source_health_endpoint(self):
        """Verify the endpoint function returns correct structure."""
        from app.api.v1.health import get_source_health

        # Patch the singleton to use a fresh service
        fresh_registry = CircuitBreakerRegistry()
        fresh_svc = SourceHealthService(registry=fresh_registry)
        fresh_svc.record_success("ngx_official")
        fresh_svc.record_success("ngnmarket")

        with patch("app.api.v1.health.get_source_health_service", return_value=fresh_svc):
            resp = await get_source_health()

        assert resp["overall_status"] == "OK"
        assert len(resp["sources"]) == 2
        names = {s["name"] for s in resp["sources"]}
        assert names == {"ngx_official", "ngnmarket"}

    @pytest.mark.asyncio
    async def test_endpoint_reflects_degraded(self):
        """Endpoint shows DEGRADED when a source is tripped."""
        from app.api.v1.health import get_source_health

        fresh_registry = CircuitBreakerRegistry(
            default_config=CircuitBreakerConfig(failure_threshold=2)
        )
        fresh_svc = SourceHealthService(registry=fresh_registry)
        fresh_svc.record_success("src_ok")
        fresh_svc.record_failure("src_bad")
        fresh_svc.record_failure("src_bad")

        with patch("app.api.v1.health.get_source_health_service", return_value=fresh_svc):
            resp = await get_source_health()

        assert resp["overall_status"] == "DEGRADED"
