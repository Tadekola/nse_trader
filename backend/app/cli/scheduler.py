"""
Daily Scheduler — Automated Nightly EOD Ingestion (P1-4).

Runs an incremental backfill each evening (or on-demand) with:
  - Configurable schedule via CLI flags (no hardcoded timezone)
  - Artifact storage: run manifest JSON per execution
  - Audit event summarizing each run
  - Safe mode detection via circuit breakers

Usage::

    # Default: auto source, 5 days back
    python -m app.cli.scheduler

    # Custom
    python -m app.cli.scheduler --source auto --days-back 10 --min-sessions 60

    # In cron (schedule externally, no hardcoded TZ):
    # 0 17 * * 1-5  cd /opt/nse_trader/backend && python -m app.cli.scheduler
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.core.config import get_settings
from app.data.artifacts.manifest import (
    DateEntry,
    ManifestWriter,
    RunManifest,
)
from app.data.circuit_breaker import get_breaker_registry
from app.data.historical.storage import get_historical_storage
from app.data.universe import get_symbol_universe
from app.services.source_health import get_source_health_service
from app.cli.backfill import (
    backfill_via_ngx_pdf,
    generate_coverage_report,
    persist_coverage_report,
)
from app.data.historical.ingestion import HistoricalIngestionService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_scheduled_ingestion(
    source: str = "auto",
    days_back: int = 5,
    min_sessions: Optional[int] = None,
    symbols: Optional[List[str]] = None,
    artifacts_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a single scheduled ingestion run.

    Returns a summary dict suitable for audit persistence.
    """
    settings = get_settings()
    symbols = symbols or get_symbol_universe()
    min_sess = min_sessions or settings.MIN_OHLCV_SESSIONS

    writer = ManifestWriter(artifacts_dir=artifacts_dir)
    manifest = writer.create_manifest(
        source=source,
        symbols=symbols,
        days_back=days_back,
        end_date=date.today().isoformat(),
        start_date=(date.today() - timedelta(days=days_back)).isoformat(),
    )

    start_time = time.monotonic()
    registry = get_breaker_registry()
    health_svc = get_source_health_service()

    # Check safe mode before starting
    safe_mode = registry.is_safe_mode()
    if safe_mode:
        logger.warning("SAFE MODE active — all sources have open circuit breakers")
        manifest.safe_mode_activated = True

    storage = get_historical_storage()
    ingestion = HistoricalIngestionService()
    results: List[Dict[str, Any]] = []

    # ── Phase 1: ngnmarket (if source is ngnmarket or auto) ──
    if source in ("ngnmarket", "auto") and not safe_mode:
        logger.info("Scheduler: ingesting from ngnmarket for %d symbols", len(symbols))
        for symbol in symbols:
            try:
                result = await ingestion.ingest_symbol(symbol)
                results.append(result)
                if result.get("success"):
                    manifest.symbols_updated.append(symbol)
                    health_svc.record_success("ngnmarket")
                else:
                    manifest.symbols_failed.append(symbol)
                    health_svc.record_failure("ngnmarket", result.get("error"))
            except Exception as e:
                logger.error("Scheduler: error ingesting %s: %s", symbol, e)
                manifest.symbols_failed.append(symbol)
                health_svc.record_failure("ngnmarket", str(e))

    # ── Phase 2: NGX PDF (if source is ngx_pdf or auto-fallback) ──
    if source in ("ngx_pdf", "auto") and not safe_mode:
        try:
            end_d = date.today()
            start_d = end_d - timedelta(days=days_back)
            pdf_results = await backfill_via_ngx_pdf(
                symbols, days_back=days_back,
                start_date=start_d, end_date=end_d,
            )
            for sym, res in pdf_results.items():
                if res.get("success"):
                    if sym not in manifest.symbols_updated:
                        manifest.symbols_updated.append(sym)
                    health_svc.record_success("ngx_pdf")
                else:
                    health_svc.record_failure("ngx_pdf", "no data")
        except Exception as e:
            logger.error("Scheduler: NGX PDF phase failed: %s", e)
            health_svc.record_failure("ngx_pdf", str(e))

    # ── Finalize manifest ──
    elapsed = time.monotonic() - start_time
    manifest.duration_seconds = round(elapsed, 2)
    manifest.total_records = sum(
        r.get("sessions_fetched", 0) for r in results
    )
    manifest.finalize()

    # Generate coverage report path as artifact
    try:
        coverage = generate_coverage_report(symbols)
        cov_path = persist_coverage_report(coverage)
        manifest.artifacts["coverage_report"] = cov_path
    except Exception as e:
        logger.error("Scheduler: coverage report failed: %s", e)

    # Save manifest
    manifest_path = writer.save(manifest)
    manifest.artifacts["manifest"] = manifest_path

    # ── Build audit summary ──
    summary = {
        "component": "scheduler",
        "event_type": "SCHEDULED_RUN",
        "level": "WARN" if manifest.safe_mode_activated else "INFO",
        "message": (
            f"Scheduled run complete: {len(manifest.symbols_updated)} updated, "
            f"{len(manifest.symbols_failed)} failed, "
            f"{manifest.total_records} records in {manifest.duration_seconds}s"
        ),
        "payload": {
            "run_id": manifest.run_id,
            "source": source,
            "symbols_updated": manifest.symbols_updated,
            "symbols_failed": manifest.symbols_failed,
            "total_records": manifest.total_records,
            "duration_seconds": manifest.duration_seconds,
            "safe_mode": manifest.safe_mode_activated,
            "manifest_path": manifest_path,
        },
    }

    # Persist audit event (best-effort)
    try:
        _persist_scheduler_audit(summary)
    except Exception as e:
        logger.error("Scheduler: audit persistence failed: %s", e)

    logger.info(
        "Scheduler run complete: %s", summary["message"]
    )
    return summary


def _persist_scheduler_audit(event: Dict[str, Any]) -> None:
    """Best-effort persist audit event for the scheduler run."""
    try:
        from app.services.audit import AuditService
        import asyncio

        async def _write():
            svc = AuditService()
            await svc.record_audit(
                component=event["component"],
                event_type=event["event_type"],
                level=event["level"],
                message=event["message"],
                payload=event.get("payload"),
            )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_write())
        except RuntimeError:
            asyncio.run(_write())
    except ImportError:
        logger.debug("AuditService not available; skipping audit persistence")
    except Exception as e:
        logger.error("Audit persistence error: %s", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Daily scheduled EOD ingestion",
    )
    parser.add_argument(
        "--source",
        choices=["ngnmarket", "ngx_pdf", "auto"],
        default="auto",
        help="Data source (default: auto)",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=5,
        help="Days back to fetch (default: 5)",
    )
    parser.add_argument(
        "--min-sessions",
        type=int,
        default=None,
        help="Minimum sessions per symbol (default: from config)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbols (default: full universe)",
    )
    args = parser.parse_args()

    syms = None
    if args.symbols:
        syms = [s.strip().upper() for s in args.symbols.split(",")]

    asyncio.run(run_scheduled_ingestion(
        source=args.source,
        days_back=args.days_back,
        min_sessions=args.min_sessions,
        symbols=syms,
    ))
