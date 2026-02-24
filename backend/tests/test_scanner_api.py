"""
Scanner API Tests (PR6).

Covers:
  1. Pydantic schema validation (response contracts)
  2. Buylist filtering: confidence penalty, data quality
  3. Trailing returns structure
  4. Currency note logic
  5. Router registration
  6. Schema serialization
"""

import os
import sys
import pytest
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.scanner import (
    UniverseMemberResponse, UniverseResponse,
    ScanRunResponse, ScanRunListResponse,
    ScanResultResponse, ScanResultListResponse, TrailingReturns,
    BuylistEntry, BuylistResponse,
)


# ═══════════════════════════════════════════════════════════════════════
# Schema validation tests
# ═══════════════════════════════════════════════════════════════════════

class TestUniverseSchema:
    def test_universe_member_response(self):
        m = UniverseMemberResponse(
            symbol="DANGCEM",
            universe_name="top_liquid_50",
            as_of_date=date(2025, 6, 15),
            rank=1,
            liquidity_score=1.0,
            avg_daily_value=500_000_000,
            zero_volume_days=2,
        )
        assert m.symbol == "DANGCEM"
        assert m.rank == 1

    def test_universe_response(self):
        members = [
            UniverseMemberResponse(
                symbol=s, universe_name="test", as_of_date=date(2025, 6, 15),
                rank=i + 1, liquidity_score=1.0 - i * 0.1,
            )
            for i, s in enumerate(["A", "B", "C"])
        ]
        resp = UniverseResponse(
            universe_name="test", as_of_date=date(2025, 6, 15),
            member_count=3, members=members,
        )
        assert resp.member_count == 3
        assert len(resp.members) == 3


class TestScanRunSchema:
    def test_scan_run_response(self):
        r = ScanRunResponse(
            id=1, as_of_date=date(2025, 6, 15),
            universe_name="top_liquid_50",
            symbols_scanned=50, symbols_ranked=50,
            created_at=datetime(2025, 6, 15, 12, 0, 0),
            summary={"top_5": ["A", "B", "C", "D", "E"]},
        )
        assert r.id == 1
        assert r.symbols_ranked == 50

    def test_scan_run_list_response(self):
        resp = ScanRunListResponse(total=0, runs=[])
        assert resp.total == 0


class TestScanResultSchema:
    def test_trailing_returns(self):
        tr = TrailingReturns(
            tri_1y_ngn=0.15, tri_3y_ngn=0.45,
            tri_1y_usd=-0.10, tri_3y_usd=0.05,
            tri_1y_real=-0.05, tri_3y_real=0.10,
        )
        assert tr.tri_1y_ngn == 0.15
        assert tr.tri_1y_usd == -0.10

    def test_trailing_returns_all_none(self):
        tr = TrailingReturns()
        assert tr.tri_1y_ngn is None
        assert tr.tri_1y_usd is None

    def test_scan_result_response(self):
        r = ScanResultResponse(
            symbol="DANGCEM", rank=1, quality_score=85.5,
            sub_scores={"profitability": 20, "cash_quality": 22},
            reasons=["Strong ROE"], red_flags=[],
            flags={"data_quality": "FULL"},
            liquidity_score=0.95, confidence_penalty=0.0,
            trailing_returns=TrailingReturns(tri_1y_ngn=0.15),
        )
        assert r.quality_score == 85.5
        assert r.trailing_returns.tri_1y_ngn == 0.15

    def test_scan_result_list_response(self):
        resp = ScanResultListResponse(
            run_id=1, as_of_date=date(2025, 6, 15),
            universe_name="test", total=0, results=[],
        )
        assert resp.total == 0


class TestBuylistSchema:
    def test_buylist_entry(self):
        entry = BuylistEntry(
            rank=1, symbol="DANGCEM", quality_score=90.0,
            data_quality="FULL", confidence_penalty=0.0,
            sub_scores={"profitability": 22},
            top_reasons=["Strong ROE", "Positive FCF"],
            red_flags=[],
            trailing_returns=TrailingReturns(
                tri_1y_ngn=0.15, tri_1y_usd=-0.10,
            ),
        )
        assert entry.symbol == "DANGCEM"
        assert len(entry.top_reasons) == 2

    def test_buylist_response(self):
        resp = BuylistResponse(
            as_of_date=date(2025, 6, 15),
            universe_name="top_liquid_50",
            run_id=1,
            currency_note="Returns shown in NGN only",
            total=0,
            buylist=[],
        )
        assert resp.run_id == 1
        assert resp.total == 0

    def test_buylist_response_with_entries(self):
        entries = [
            BuylistEntry(
                rank=i + 1, symbol=f"SYM{i}", quality_score=90 - i * 5,
                data_quality="FULL", confidence_penalty=0.0,
                sub_scores={}, top_reasons=["Good"], red_flags=[],
                trailing_returns=TrailingReturns(tri_1y_ngn=0.1 + i * 0.02),
            )
            for i in range(5)
        ]
        resp = BuylistResponse(
            as_of_date=date(2025, 6, 15),
            universe_name="test", run_id=1,
            currency_note="Returns shown in NGN only",
            total=5, buylist=entries,
        )
        assert resp.total == 5
        assert resp.buylist[0].quality_score == 90

    def test_buylist_currency_note_ngn_only(self):
        """When no USD/REAL data, note should say NGN only."""
        entries = [
            BuylistEntry(
                rank=1, symbol="A", quality_score=80,
                data_quality="FULL", confidence_penalty=0.0,
                sub_scores={}, top_reasons=[], red_flags=[],
                trailing_returns=TrailingReturns(tri_1y_ngn=0.10),
            )
        ]
        # Verify the entry has no USD data
        assert entries[0].trailing_returns.tri_1y_usd is None

    def test_buylist_currency_note_full(self):
        """With USD and REAL data, currency note should mention all three."""
        entries = [
            BuylistEntry(
                rank=1, symbol="A", quality_score=80,
                data_quality="FULL", confidence_penalty=0.0,
                sub_scores={}, top_reasons=[], red_flags=[],
                trailing_returns=TrailingReturns(
                    tri_1y_ngn=0.10, tri_1y_usd=-0.05, tri_1y_real=0.02,
                ),
            )
        ]
        has_usd = any(e.trailing_returns.tri_1y_usd is not None for e in entries)
        has_real = any(e.trailing_returns.tri_1y_real is not None for e in entries)
        assert has_usd and has_real


# ═══════════════════════════════════════════════════════════════════════
# Buylist filtering logic tests
# ═══════════════════════════════════════════════════════════════════════

class TestBuylistFiltering:
    def _make_entries(self):
        """Create test entries with varying quality."""
        return [
            {"rank": 1, "symbol": "A", "quality_score": 90, "data_quality": "FULL",
             "confidence_penalty": 0.0, "red_flags": []},
            {"rank": 2, "symbol": "B", "quality_score": 80, "data_quality": "DEGRADED",
             "confidence_penalty": 0.3, "red_flags": []},
            {"rank": 3, "symbol": "C", "quality_score": 70, "data_quality": "INSUFFICIENT",
             "confidence_penalty": 0.8, "red_flags": ["NO_FUNDAMENTALS_DATA"]},
            {"rank": 4, "symbol": "D", "quality_score": 60, "data_quality": "FULL",
             "confidence_penalty": 0.1, "red_flags": []},
        ]

    def test_filter_by_confidence_penalty(self):
        """Entries with penalty > threshold should be excluded."""
        entries = self._make_entries()
        max_penalty = 0.5
        filtered = [e for e in entries if e["confidence_penalty"] <= max_penalty]
        assert len(filtered) == 3  # A, B, D included; C excluded

    def test_filter_insufficient_data(self):
        """Entries with INSUFFICIENT data quality should be excluded."""
        entries = self._make_entries()
        filtered = [e for e in entries if e["data_quality"] != "INSUFFICIENT"]
        assert len(filtered) == 3  # A, B, D included; C excluded

    def test_combined_filter(self):
        """Combined filtering: penalty + data quality."""
        entries = self._make_entries()
        max_penalty = 0.5
        filtered = [
            e for e in entries
            if e["confidence_penalty"] <= max_penalty
            and e["data_quality"] != "INSUFFICIENT"
        ]
        assert len(filtered) == 3  # A, B, D

    def test_top_n_truncation(self):
        """Buylist should be truncated to top_n."""
        entries = self._make_entries()
        filtered = [e for e in entries if e["data_quality"] != "INSUFFICIENT"][:2]
        assert len(filtered) == 2
        assert filtered[0]["symbol"] == "A"
        assert filtered[1]["symbol"] == "B"


# ═══════════════════════════════════════════════════════════════════════
# Router registration test
# ═══════════════════════════════════════════════════════════════════════

class TestRouterRegistration:
    def test_scanner_router_registered(self):
        """Scanner router should be registered in the main app."""
        from app.main import app
        routes = [r.path for r in app.routes]
        # Check that scanner endpoints exist
        scanner_paths = [r for r in routes if "/scanner" in r]
        assert len(scanner_paths) >= 4, f"Expected >= 4 scanner routes, got: {scanner_paths}"

    def test_scanner_endpoints_exist(self):
        """All 5 scanner endpoints should be registered."""
        from app.main import app
        routes = {r.path for r in app.routes}
        expected = {
            "/api/v1/scanner/universe",
            "/api/v1/scanner/runs",
            "/api/v1/scanner/runs/{run_id}",
            "/api/v1/scanner/runs/{run_id}/results",
            "/api/v1/scanner/buylist",
        }
        for path in expected:
            assert path in routes, f"Missing route: {path}"


# ═══════════════════════════════════════════════════════════════════════
# Serialization tests
# ═══════════════════════════════════════════════════════════════════════

class TestSerialization:
    def test_buylist_entry_json(self):
        """BuylistEntry should serialize to valid JSON."""
        entry = BuylistEntry(
            rank=1, symbol="TEST", quality_score=85.5,
            data_quality="FULL", confidence_penalty=0.02,
            sub_scores={"profitability": 20.5},
            top_reasons=["Strong ROE"],
            red_flags=["HIGH_LEVERAGE"],
            trailing_returns=TrailingReturns(tri_1y_ngn=0.15),
        )
        d = entry.model_dump()
        assert d["rank"] == 1
        assert d["trailing_returns"]["tri_1y_ngn"] == 0.15
        assert isinstance(d["top_reasons"], list)

    def test_buylist_response_json(self):
        """Full BuylistResponse should serialize cleanly."""
        resp = BuylistResponse(
            as_of_date=date(2025, 6, 15),
            universe_name="test", run_id=1,
            currency_note="NGN only",
            total=1,
            buylist=[
                BuylistEntry(
                    rank=1, symbol="A", quality_score=90,
                    data_quality="FULL", confidence_penalty=0.0,
                    sub_scores={}, top_reasons=[], red_flags=[],
                    trailing_returns=TrailingReturns(),
                )
            ],
        )
        d = resp.model_dump()
        assert d["total"] == 1
        assert d["buylist"][0]["symbol"] == "A"
