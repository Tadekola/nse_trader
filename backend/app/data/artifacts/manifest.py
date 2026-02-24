"""
Run Manifest Writer (P1-4).

Stores a structured JSON manifest for each ingestion run, capturing:
  - Run metadata (timestamp, source, duration)
  - Dates processed, URLs fetched, checksums
  - Parse row counts per date
  - Symbols updated and failures
  - Artifact paths (PDFs, HTML snapshots)

Manifests are stored in data/artifacts/ with ISO-timestamped filenames.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "artifacts"
)


@dataclass
class DateEntry:
    """Per-date record in the manifest."""
    trade_date: str
    url: Optional[str] = None
    checksum: Optional[str] = None
    rows_parsed: int = 0
    pdf_path: Optional[str] = None
    status: str = "ok"  # ok | missing | error
    error: Optional[str] = None


@dataclass
class RunManifest:
    """Structured manifest for a single ingestion run."""
    run_id: str
    started_at: str
    finished_at: Optional[str] = None
    source: str = "auto"
    days_back: int = 0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    symbols_requested: List[str] = field(default_factory=list)
    symbols_updated: List[str] = field(default_factory=list)
    symbols_failed: List[str] = field(default_factory=list)
    dates: List[DateEntry] = field(default_factory=list)
    total_records: int = 0
    safe_mode_activated: bool = False
    reconciliation_updates: int = 0
    reconciliation_conflicts: int = 0
    duration_seconds: Optional[float] = None
    artifacts: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    def add_date(self, entry: DateEntry) -> None:
        self.dates.append(entry)

    def finalize(self, finished_at: Optional[str] = None) -> None:
        self.finished_at = finished_at or datetime.now(timezone.utc).isoformat()


class ManifestWriter:
    """
    Writes run manifests to the artifacts directory.

    Usage::

        writer = ManifestWriter()
        manifest = writer.create_manifest(source="auto", symbols=["DANGCEM"])
        manifest.add_date(DateEntry(trade_date="2026-02-20", rows_parsed=150))
        manifest.finalize()
        path = writer.save(manifest)
    """

    def __init__(self, artifacts_dir: Optional[str] = None):
        self.artifacts_dir = artifacts_dir or DEFAULT_ARTIFACTS_DIR
        os.makedirs(self.artifacts_dir, exist_ok=True)

    def create_manifest(
        self,
        source: str = "auto",
        symbols: Optional[List[str]] = None,
        days_back: int = 0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> RunManifest:
        now = datetime.now(timezone.utc)
        run_id = now.strftime("%Y%m%dT%H%M%S")
        return RunManifest(
            run_id=run_id,
            started_at=now.isoformat(),
            source=source,
            days_back=days_back,
            start_date=start_date,
            end_date=end_date,
            symbols_requested=symbols or [],
        )

    def save(self, manifest: RunManifest) -> str:
        """Save manifest to JSON file. Returns the file path."""
        filename = f"manifest_{manifest.run_id}.json"
        path = os.path.join(self.artifacts_dir, filename)

        with open(path, "w") as f:
            json.dump(manifest.to_dict(), f, indent=2, default=str)

        logger.info("Manifest written to %s", path)
        return path

    def load(self, path: str) -> RunManifest:
        """Load a manifest from a JSON file."""
        with open(path) as f:
            data = json.load(f)

        dates = [DateEntry(**d) for d in data.pop("dates", [])]
        manifest = RunManifest(**{k: v for k, v in data.items() if k != "dates"})
        manifest.dates = dates
        return manifest

    def list_manifests(self) -> List[str]:
        """List all manifest files in the artifacts directory."""
        if not os.path.exists(self.artifacts_dir):
            return []
        return sorted(
            f for f in os.listdir(self.artifacts_dir)
            if f.startswith("manifest_") and f.endswith(".json")
        )
