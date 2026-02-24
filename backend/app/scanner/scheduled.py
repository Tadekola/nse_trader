"""
Scheduled Scanner — Automated scan execution with artifact storage and audit trail.

Integrates with the existing scheduler infrastructure:
  - Uses ManifestWriter for artifact persistence
  - Writes audit events for each run
  - Honors idempotency (same-day guard from workflow.run_scan)
  - Supports daily/weekly frequency with configurable as-of date

Usage (cron-invoked, no hardcoded TZ):
  # Daily at 6PM WAT (after market close):
  # 0 18 * * 1-5  cd /opt/nse_trader/backend && python -m app.scanner.scheduled

  # Weekly (Sunday evening):
  # 0 20 * * 0  cd /opt/nse_trader/backend && python -m app.scanner.scheduled --freq weekly

  # Or via scheduler hook:
  from app.scanner.scheduled import run_scheduled_scan
  summary = await run_scheduled_scan(session, freq="daily")
"""

import json
import logging
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.artifacts.manifest import ManifestWriter, RunManifest
from app.scanner.workflow import run_scan
from app.scanner.explainer import get_scoring_config_hash, SCORING_CONFIG_VERSION
from app.db.models import AuditEvent

logger = logging.getLogger(__name__)


def _compute_as_of(freq: str, reference_date: Optional[date] = None) -> date:
    """
    Determine the as-of date based on frequency.

    - daily: today (or last business day if weekend)
    - weekly: previous Friday (most recent completed week)
    """
    ref = reference_date or date.today()

    if freq == "weekly":
        # Roll back to last Friday
        days_since_friday = (ref.weekday() - 4) % 7
        if days_since_friday == 0 and ref.weekday() != 4:
            days_since_friday = 7
        return ref - timedelta(days=days_since_friday)
    else:  # daily
        # If weekend, roll back to Friday
        if ref.weekday() == 5:  # Saturday
            return ref - timedelta(days=1)
        elif ref.weekday() == 6:  # Sunday
            return ref - timedelta(days=2)
        return ref


async def run_scheduled_scan(
    session: AsyncSession,
    universe_name: str = "top_liquid_50",
    top_n: int = 50,
    freq: str = "daily",
    force: bool = False,
    artifacts_dir: Optional[str] = None,
    reference_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Execute a scheduled quality scan with artifact storage and audit trail.

    Args:
        session: async DB session
        universe_name: universe to scan
        top_n: max members
        freq: "daily" or "weekly"
        force: override idempotency guard
        artifacts_dir: where to store manifest (default: data/artifacts/)
        reference_date: override today for testing

    Returns:
        Summary dict with scan results and artifact paths.
    """
    start_time = time.monotonic()
    as_of = _compute_as_of(freq, reference_date)

    logger.info("Scheduled scan: freq=%s, universe=%s, as_of=%s, force=%s",
                freq, universe_name, as_of, force)

    # ── Create manifest ──────────────────────────────────────────────
    writer = ManifestWriter(artifacts_dir=artifacts_dir)
    manifest = writer.create_manifest(
        source="scanner",
        symbols=[],
        start_date=as_of.isoformat(),
        end_date=as_of.isoformat(),
    )

    # ── Run the scan ─────────────────────────────────────────────────
    scan_error = None
    scan_summary = None
    try:
        scan_summary = await run_scan(
            session,
            universe_name=universe_name,
            as_of=as_of,
            top_n=top_n,
            persist=True,
            force=force,
        )

        status = scan_summary.get("status", "unknown")
        if status == "completed":
            manifest.symbols_updated = [
                r["symbol"] for r in scan_summary.get("top_10", [])
            ]
            manifest.total_records = scan_summary.get("symbols_ranked", 0)
        elif status == "skipped_idempotent":
            logger.info("Scan skipped (idempotent): run_id=%s",
                        scan_summary.get("run_id"))
        elif status == "empty_universe":
            logger.warning("Scan produced empty universe")

    except Exception as e:
        scan_error = str(e)
        logger.error("Scheduled scan failed: %s", e)
        manifest.symbols_failed.append(f"SCAN_ERROR: {scan_error}")

    # ── Finalize manifest ────────────────────────────────────────────
    elapsed = time.monotonic() - start_time
    manifest.duration_seconds = round(elapsed, 2)
    manifest.finalize()

    # Store scan summary as artifact
    if scan_summary:
        summary_path = _write_scan_summary(writer, manifest.run_id, scan_summary)
        manifest.artifacts["scan_summary"] = summary_path

    manifest_path = writer.save(manifest)
    manifest.artifacts["manifest"] = manifest_path

    # ── Write audit event ────────────────────────────────────────────
    scan_status = scan_summary.get("status", "error") if scan_summary else "error"
    run_id = scan_summary.get("run_id") if scan_summary else None
    provenance = scan_summary.get("provenance", {}) if scan_summary else {}

    audit_level = "INFO"
    if scan_error:
        audit_level = "ERROR"
    elif scan_status == "skipped_idempotent":
        audit_level = "INFO"
    elif scan_status == "empty_universe":
        audit_level = "WARNING"

    session.add(AuditEvent(
        component="scanner",
        event_type="SCHEDULED_SCAN",
        level=audit_level,
        message=(
            f"Scheduled {freq} scan: status={scan_status}, "
            f"universe={universe_name}, as_of={as_of}"
        ),
        payload={
            "freq": freq,
            "universe_name": universe_name,
            "as_of": as_of.isoformat(),
            "scan_status": scan_status,
            "run_id": run_id,
            "symbols_ranked": scan_summary.get("symbols_ranked", 0) if scan_summary else 0,
            "duration_seconds": manifest.duration_seconds,
            "manifest_path": manifest_path,
            "scoring_config_hash": provenance.get("scoring_config_hash"),
            "error": scan_error,
        },
    ))

    try:
        await session.commit()
    except Exception as e:
        logger.error("Failed to commit audit event: %s", e)

    # ── Return summary ───────────────────────────────────────────────
    return {
        "status": scan_status,
        "freq": freq,
        "as_of": as_of.isoformat(),
        "universe": universe_name,
        "run_id": run_id,
        "symbols_ranked": scan_summary.get("symbols_ranked", 0) if scan_summary else 0,
        "duration_seconds": manifest.duration_seconds,
        "manifest_path": manifest_path,
        "error": scan_error,
        "provenance": provenance,
    }


def _write_scan_summary(
    writer: ManifestWriter, run_id: str, summary: Dict[str, Any]
) -> str:
    """Write scan summary JSON to artifacts directory."""
    import os
    filename = f"scan_summary_{run_id}.json"
    path = os.path.join(writer.artifacts_dir, filename)
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    return path
