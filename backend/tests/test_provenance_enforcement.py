"""
Tests for Provenance Completeness Enforcement (P3-3).

Covers:
  1. _check_item_provenance — field validation logic
  2. _extract_items — extraction from various response shapes
  3. Middleware pass-through — valid provenance passes cleanly
  4. Middleware rejection (DEV mode) — 500 on missing provenance
  5. Middleware fail-safe (PROD mode) — NO_TRADE rewrite
  6. Middleware skips non-recommendation paths
  7. Audit event written on violation
"""

import json
import sys
import os
import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.middleware.provenance import (
    ProvenanceEnforcementMiddleware,
    _check_item_provenance,
    _extract_items,
    _build_no_trade_response,
    _build_audit_event,
    REQUIRED_ITEM_FIELDS,
    PROVENANCE_DEPTH_FIELDS,
)


# ── 1. _check_item_provenance unit tests ────────────────────────────


class TestCheckItemProvenance:

    def test_valid_item_passes(self):
        item = {
            "confidence_score": 0.85,
            "status": "ACTIVE",
            "data_confidence": {"price_agreement": 0.9},
        }
        assert _check_item_provenance(item) == []

    def test_valid_with_confidence_field(self):
        """confidence (float) satisfies the depth requirement."""
        item = {
            "confidence_score": 0.8,
            "status": "ACTIVE",
            "confidence": 0.75,
        }
        assert _check_item_provenance(item) == []

    def test_valid_with_bias_signal(self):
        """bias_signal satisfies the depth requirement."""
        item = {
            "confidence_score": 0.8,
            "status": "SUPPRESSED",
            "bias_signal": {"direction": "bearish"},
        }
        assert _check_item_provenance(item) == []

    def test_missing_confidence_score(self):
        item = {
            "status": "ACTIVE",
            "data_confidence": {"x": 1},
        }
        violations = _check_item_provenance(item)
        assert any("confidence_score" in v for v in violations)

    def test_missing_status(self):
        item = {
            "confidence_score": 0.8,
            "data_confidence": {"x": 1},
        }
        violations = _check_item_provenance(item)
        assert any("status" in v for v in violations)

    def test_missing_all_depth_fields(self):
        item = {
            "confidence_score": 0.8,
            "status": "ACTIVE",
        }
        violations = _check_item_provenance(item)
        assert any("provenance depth" in v for v in violations)

    def test_none_values_count_as_missing(self):
        item = {
            "confidence_score": None,
            "status": None,
            "data_confidence": None,
            "confidence": None,
            "bias_signal": None,
        }
        violations = _check_item_provenance(item)
        assert len(violations) >= 2  # confidence_score + status + depth

    def test_empty_dict_fails(self):
        violations = _check_item_provenance({})
        assert len(violations) >= 3  # confidence_score + status + depth


# ── 2. _extract_items unit tests ─────────────────────────────────────


class TestExtractItems:

    def test_list_response(self):
        body = {"data": [{"symbol": "A"}, {"symbol": "B"}]}
        assert len(_extract_items(body)) == 2

    def test_single_response(self):
        body = {"data": {"symbol": "A"}}
        assert len(_extract_items(body)) == 1

    def test_all_horizons_response(self):
        body = {"recommendations": {"short_term": {"symbol": "A"}, "swing": {"symbol": "B"}}}
        assert len(_extract_items(body)) == 2

    def test_empty_body(self):
        assert _extract_items({}) == []

    def test_non_dict_data(self):
        body = {"data": "not a dict or list"}
        assert _extract_items(body) == []


# ── 3. Build helpers ─────────────────────────────────────────────────


class TestBuildHelpers:

    def test_no_trade_response_shape(self):
        resp = _build_no_trade_response("/test", ["missing field X"])
        assert resp["data"]["status"] == "NO_TRADE"
        assert resp["data"]["confidence_score"] == 0.0
        assert "Provenance enforcement" in resp["data"]["suppression_reason"]
        assert resp["_provenance_enforcement"]["enforced"] is True

    def test_audit_event_shape(self):
        evt = _build_audit_event("/test", ["violation1"], "development")
        assert evt["component"] == "provenance_enforcement"
        assert evt["event_type"] == "PROVENANCE_VIOLATION"
        assert evt["level"] == "ERROR"
        assert "violation1" in evt["message"]
        assert evt["payload"]["mode"] == "development"


# ── 4. Middleware integration tests ──────────────────────────────────


def _make_test_app(response_data: dict, path: str = "/api/v1/recommendations/test"):
    """Create a minimal FastAPI app with the middleware and a test endpoint."""
    app = FastAPI()
    app.add_middleware(ProvenanceEnforcementMiddleware)

    @app.get(path)
    async def _endpoint():
        return response_data

    return app


class TestMiddlewarePassThrough:

    @pytest.mark.asyncio
    async def test_valid_response_passes(self):
        """Response with complete provenance passes through unmodified."""
        data = {
            "success": True,
            "data": {
                "symbol": "DANGCEM",
                "confidence_score": 0.85,
                "status": "ACTIVE",
                "confidence": 0.85,
                "data_confidence": {"price_agreement": 0.9},
            },
        }
        app = _make_test_app(data)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/recommendations/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["symbol"] == "DANGCEM"

    @pytest.mark.asyncio
    async def test_list_response_passes(self):
        """List response with complete provenance passes."""
        data = {
            "success": True,
            "data": [
                {"confidence_score": 0.8, "status": "ACTIVE", "confidence": 0.8},
                {"confidence_score": 0.7, "status": "SUPPRESSED", "data_confidence": {"x": 1}},
            ],
        }
        app = _make_test_app(data)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/recommendations/test")

        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    @pytest.mark.asyncio
    async def test_non_recommendation_path_skipped(self):
        """Non-recommendation paths bypass enforcement entirely."""
        data = {"data": {"no_provenance": True}}
        app = _make_test_app(data, path="/api/v1/stocks/test")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/stocks/test")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_items_passes(self):
        """Response with no extractable items passes (e.g. market-regime)."""
        data = {"success": True, "regime": "bullish"}
        app = _make_test_app(data)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/recommendations/test")

        assert resp.status_code == 200


class TestMiddlewareRejection:

    @pytest.mark.asyncio
    async def test_dev_mode_returns_500(self):
        """In dev mode, missing provenance returns 500 with violations."""
        data = {
            "success": True,
            "data": {"symbol": "DANGCEM"},  # no provenance fields
        }
        app = _make_test_app(data)
        with patch.dict(os.environ, {"ENV": "development", "PROVENANCE_ENFORCEMENT": "on"}):
            with patch("app.middleware.provenance._persist_audit", new_callable=AsyncMock):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.get("/api/v1/recommendations/test")

        assert resp.status_code == 500
        body = resp.json()
        assert body["error"] == "provenance_enforcement_failure"
        assert len(body["violations"]) >= 2

    @pytest.mark.asyncio
    async def test_prod_mode_returns_no_trade(self):
        """In prod mode, missing provenance returns NO_TRADE fail-safe."""
        data = {
            "success": True,
            "data": {"symbol": "DANGCEM"},  # no provenance fields
        }
        app = _make_test_app(data)
        with patch.dict(os.environ, {"ENV": "production", "PROVENANCE_ENFORCEMENT": "on"}):
            with patch("app.middleware.provenance._persist_audit", new_callable=AsyncMock):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.get("/api/v1/recommendations/test")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "NO_TRADE"
        assert body["data"]["confidence_score"] == 0.0
        assert "_provenance_enforcement" in body

    @pytest.mark.asyncio
    async def test_enforcement_off_skips_check(self):
        """When PROVENANCE_ENFORCEMENT=off, no check is performed."""
        data = {
            "success": True,
            "data": {"symbol": "DANGCEM"},  # no provenance
        }
        app = _make_test_app(data)
        with patch.dict(os.environ, {"PROVENANCE_ENFORCEMENT": "off"}):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/v1/recommendations/test")

        assert resp.status_code == 200
        assert resp.json()["data"]["symbol"] == "DANGCEM"


class TestAuditEventWritten:

    @pytest.mark.asyncio
    async def test_audit_event_persisted_on_violation(self):
        """An audit event is written when provenance check fails."""
        data = {
            "success": True,
            "data": {"symbol": "DANGCEM"},
        }
        app = _make_test_app(data)
        mock_persist = AsyncMock()

        with patch.dict(os.environ, {"ENV": "development", "PROVENANCE_ENFORCEMENT": "on"}):
            with patch("app.middleware.provenance._persist_audit", mock_persist):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    await client.get("/api/v1/recommendations/test")

        mock_persist.assert_awaited_once()
        call_args = mock_persist.call_args[0][0]
        assert call_args["component"] == "provenance_enforcement"
        assert call_args["event_type"] == "PROVENANCE_VIOLATION"
        assert call_args["level"] == "ERROR"

    @pytest.mark.asyncio
    async def test_no_audit_on_valid_response(self):
        """No audit event when provenance is complete."""
        data = {
            "success": True,
            "data": {
                "confidence_score": 0.9,
                "status": "ACTIVE",
                "confidence": 0.9,
            },
        }
        app = _make_test_app(data)
        mock_persist = AsyncMock()

        with patch("app.middleware.provenance._persist_audit", mock_persist):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.get("/api/v1/recommendations/test")

        mock_persist.assert_not_awaited()
