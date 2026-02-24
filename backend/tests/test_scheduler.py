"""
Tests for Daily Scheduler + Artifact Storage (P1-4).

Covers:
  1. ManifestWriter — create, save, load, list
  2. RunManifest — structure, finalize, to_dict
  3. DateEntry — serialization
  4. Scheduler run — creates manifest + returns audit summary (mocked network)
"""

import sys
import os
import json
import tempfile
import pytest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data.artifacts.manifest import (
    DateEntry,
    ManifestWriter,
    RunManifest,
)


# ── 1. DateEntry tests ──────────────────────────────────────────────


class TestDateEntry:

    def test_default_status_ok(self):
        e = DateEntry(trade_date="2026-02-20")
        assert e.status == "ok"
        assert e.rows_parsed == 0

    def test_with_all_fields(self):
        e = DateEntry(
            trade_date="2026-02-20",
            url="https://example.com/pdf",
            checksum="abc123",
            rows_parsed=150,
            pdf_path="/tmp/ngx.pdf",
            status="ok",
        )
        assert e.trade_date == "2026-02-20"
        assert e.rows_parsed == 150

    def test_error_entry(self):
        e = DateEntry(
            trade_date="2026-02-21",
            status="error",
            error="PDF not found",
        )
        assert e.status == "error"
        assert e.error == "PDF not found"


# ── 2. RunManifest tests ────────────────────────────────────────────


class TestRunManifest:

    def test_to_dict(self):
        m = RunManifest(
            run_id="20260220T180000",
            started_at="2026-02-20T18:00:00",
            source="auto",
            symbols_requested=["DANGCEM", "GTCO"],
        )
        d = m.to_dict()
        assert d["run_id"] == "20260220T180000"
        assert d["source"] == "auto"
        assert len(d["symbols_requested"]) == 2
        assert d["dates"] == []

    def test_add_date(self):
        m = RunManifest(run_id="test", started_at="now")
        m.add_date(DateEntry(trade_date="2026-02-20", rows_parsed=100))
        m.add_date(DateEntry(trade_date="2026-02-21", rows_parsed=95))
        assert len(m.dates) == 2

    def test_finalize_sets_finished_at(self):
        m = RunManifest(run_id="test", started_at="now")
        assert m.finished_at is None
        m.finalize()
        assert m.finished_at is not None

    def test_finalize_with_explicit_time(self):
        m = RunManifest(run_id="test", started_at="now")
        m.finalize(finished_at="2026-02-20T18:05:00")
        assert m.finished_at == "2026-02-20T18:05:00"


# ── 3. ManifestWriter tests ─────────────────────────────────────────


class TestManifestWriter:

    def test_create_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ManifestWriter(artifacts_dir=tmpdir)
            m = writer.create_manifest(
                source="auto",
                symbols=["DANGCEM"],
                days_back=5,
            )
            assert m.source == "auto"
            assert m.symbols_requested == ["DANGCEM"]
            assert m.run_id  # not empty

    def test_save_creates_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ManifestWriter(artifacts_dir=tmpdir)
            m = writer.create_manifest(source="ngx_pdf", symbols=["GTCO"])
            m.add_date(DateEntry(trade_date="2026-02-20", rows_parsed=100))
            m.finalize()

            path = writer.save(m)
            assert os.path.exists(path)
            assert path.endswith(".json")

            with open(path) as f:
                data = json.load(f)
            assert data["source"] == "ngx_pdf"
            assert len(data["dates"]) == 1
            assert data["dates"][0]["rows_parsed"] == 100

    def test_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ManifestWriter(artifacts_dir=tmpdir)
            m = writer.create_manifest(source="auto", symbols=["A", "B"])
            m.add_date(DateEntry(trade_date="2026-02-20", rows_parsed=50))
            m.total_records = 50
            m.finalize()
            path = writer.save(m)

            loaded = writer.load(path)
            assert loaded.source == "auto"
            assert loaded.total_records == 50
            assert len(loaded.dates) == 1
            assert loaded.dates[0].rows_parsed == 50

    def test_list_manifests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ManifestWriter(artifacts_dir=tmpdir)

            # Create two manifests
            m1 = writer.create_manifest(source="auto")
            m1.finalize()
            writer.save(m1)

            m2 = writer.create_manifest(source="ngx_pdf")
            m2.finalize()
            writer.save(m2)

            manifests = writer.list_manifests()
            assert len(manifests) >= 1  # may be same second → same filename
            for name in manifests:
                assert name.startswith("manifest_")
                assert name.endswith(".json")

    def test_creates_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "sub", "dir")
            writer = ManifestWriter(artifacts_dir=nested)
            assert os.path.isdir(nested)


# ── 4. Scheduler integration (mocked) ───────────────────────────────


class TestSchedulerRun:

    @pytest.mark.asyncio
    async def test_run_creates_manifest_and_audit(self):
        """Scheduler run creates a manifest artifact and returns audit summary."""
        from app.cli.scheduler import run_scheduled_ingestion

        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock the ingestion and backfill to avoid real network calls
            mock_result = {
                "symbol": "DANGCEM",
                "success": True,
                "sessions_fetched": 5,
                "sessions_stored": 100,
            }

            with patch("app.cli.scheduler.HistoricalIngestionService") as MockIng, \
                 patch("app.cli.scheduler.backfill_via_ngx_pdf", new_callable=AsyncMock) as mock_pdf, \
                 patch("app.cli.scheduler.generate_coverage_report", return_value={"summary": {}, "symbols": {}}), \
                 patch("app.cli.scheduler.persist_coverage_report", return_value=os.path.join(tmpdir, "cov.json")), \
                 patch("app.cli.scheduler._persist_scheduler_audit"):

                # Mock ingestion service
                mock_ing = AsyncMock()
                mock_ing.ingest_symbol = AsyncMock(return_value=mock_result)
                MockIng.return_value = mock_ing

                # Mock PDF backfill
                mock_pdf.return_value = {
                    "DANGCEM": {"success": True, "sessions_fetched": 3},
                }

                summary = await run_scheduled_ingestion(
                    source="auto",
                    days_back=5,
                    symbols=["DANGCEM"],
                    artifacts_dir=tmpdir,
                )

            # Verify audit summary
            assert summary["component"] == "scheduler"
            assert summary["event_type"] == "SCHEDULED_RUN"
            assert "payload" in summary
            assert summary["payload"]["source"] == "auto"
            assert summary["payload"]["duration_seconds"] >= 0

            # Verify manifest was written
            manifests = [
                f for f in os.listdir(tmpdir)
                if f.startswith("manifest_") and f.endswith(".json")
            ]
            assert len(manifests) >= 1

            # Verify manifest content
            with open(os.path.join(tmpdir, manifests[0])) as f:
                data = json.load(f)
            assert data["source"] == "auto"
            assert "DANGCEM" in data["symbols_requested"]

    @pytest.mark.asyncio
    async def test_safe_mode_flagged_in_manifest(self):
        """When all breakers are open, manifest flags safe_mode."""
        from app.cli.scheduler import run_scheduled_ingestion
        from app.data.circuit_breaker import CircuitBreakerRegistry, CircuitBreakerConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a registry where all sources are tripped
            reg = CircuitBreakerRegistry(
                default_config=CircuitBreakerConfig(failure_threshold=1)
            )
            for src in ["ngnmarket", "ngx_pdf"]:
                reg.get(src).record_failure()

            with patch("app.cli.scheduler.get_breaker_registry", return_value=reg), \
                 patch("app.cli.scheduler.get_source_health_service"), \
                 patch("app.cli.scheduler.generate_coverage_report", return_value={"summary": {}, "symbols": {}}), \
                 patch("app.cli.scheduler.persist_coverage_report", return_value="cov.json"), \
                 patch("app.cli.scheduler._persist_scheduler_audit"):

                summary = await run_scheduled_ingestion(
                    source="auto",
                    days_back=1,
                    symbols=["TEST"],
                    artifacts_dir=tmpdir,
                )

            assert summary["payload"]["safe_mode"] is True
