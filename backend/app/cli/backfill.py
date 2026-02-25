"""
Historical Data Backfill CLI for NSE Trader.

Usage:
    python -m app.cli.backfill [--symbols DANGCEM,GTCO,...] [--min-sessions 60] [--source auto]

Sources:
    ngnmarket  — Primary. Fetches per-symbol history from ngnmarket.com.
    ngx_pdf    — Secondary. Downloads NGX Daily Official List PDFs (per-date).
    auto       — Try ngnmarket first; for symbols still below --min-sessions,
                 fall back to NGX PDF for the missing date range.  Runs
                 reconciliation when both sources contribute data.

Produces a verification report at the end.
"""

import asyncio
import argparse
import json
import logging
import sys
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.data.universe import get_symbol_universe
from app.data.historical.storage import get_historical_storage
from app.data.historical.ingestion import HistoricalIngestionService
from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill")


# ── ngnmarket helpers (unchanged) ────────────────────────────────────


async def backfill_symbol(
    ingestion: HistoricalIngestionService,
    symbol: str,
) -> Dict[str, Any]:
    """Backfill a single symbol via ngnmarket. Returns result dict."""
    try:
        result = await ingestion.ingest_symbol(symbol)
        return result.to_dict()
    except Exception as e:
        logger.error("Failed to backfill %s: %s", symbol, e)
        return {
            "symbol": symbol,
            "success": False,
            "error": str(e),
            "sessions_fetched": 0,
            "sessions_stored": 0,
        }


async def backfill_asi(ingestion: HistoricalIngestionService) -> Dict[str, Any]:
    """Backfill ASI index history."""
    try:
        result = await ingestion.ingest_asi_history()
        return result.to_dict() if hasattr(result, "to_dict") else {
            "symbol": "ASI",
            "success": True,
            "sessions_stored": getattr(result, "sessions_stored", 0),
        }
    except Exception as e:
        logger.error("Failed to backfill ASI: %s", e)
        return {"symbol": "ASI", "success": False, "error": str(e)}


# ── NGX PDF helpers ──────────────────────────────────────────────────


async def backfill_via_ngx_pdf(
    symbols: List[str],
    days_back: int = 120,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Backfill symbols using NGX Official List PDFs.

    Downloads one PDF per trading day (skipping weekends), parses all
    symbols, and stores with reconciliation.

    Returns: {symbol: result_dict}
    """
    from app.data.sources.ngx_official_list import NgxOfficialListProvider
    from app.data.sources.reconciliation import ReconciliationService

    provider = NgxOfficialListProvider()
    reconciler = ReconciliationService()
    storage = get_historical_storage()

    end = end_date or date.today()
    start = start_date or (end - timedelta(days=days_back))

    logger.info(
        "NGX PDF backfill: %s → %s for %d symbols",
        start, end, len(symbols),
    )

    records, missing_dates, provenances = await provider.fetch_date_range(
        start_date=start,
        end_date=end,
        symbols=symbols,
        skip_weekends=True,
    )

    if missing_dates:
        logger.info(
            "NGX PDF: %d dates had no PDF available", len(missing_dates)
        )

    # Reconcile against existing storage
    if records:
        report = reconciler.reconcile_records(records)
        logger.info(
            "NGX PDF reconciliation: %s", report.summary()
        )

        # Persist audit events (fire-and-forget)
        if report.audit_events:
            try:
                _persist_reconciliation_audits(report.audit_events)
            except Exception as e:
                logger.error("Failed to persist reconciliation audits: %s", e)

    # Build per-symbol result summary
    results: Dict[str, Dict[str, Any]] = {}
    for symbol in symbols:
        meta = storage.get_metadata(symbol)
        results[symbol] = {
            "symbol": symbol,
            "success": meta is not None and meta.total_sessions > 0,
            "sessions_fetched": sum(
                1 for r in records if r.symbol == symbol
            ),
            "sessions_stored": meta.total_sessions if meta else 0,
            "source": "NGX_OFFICIAL_LIST_PDF",
        }

    logger.info(
        "NGX PDF backfill complete: %d total records across %d PDFs",
        len(records), len(provenances),
    )
    return results


def _persist_reconciliation_audits(audit_events: List[Dict[str, Any]]) -> None:
    """Best-effort persist reconciliation audit events."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule as fire-and-forget tasks
            for evt in audit_events:
                loop.create_task(_write_audit(evt))
        else:
            loop.run_until_complete(_write_audits_batch(audit_events))
    except RuntimeError:
        # No event loop; skip audit persistence (logs already emitted)
        pass


async def _write_audit(evt: Dict[str, Any]) -> None:
    from app.services.audit import get_audit_service
    svc = get_audit_service()
    await svc.record_audit(**evt)


async def _write_audits_batch(events: List[Dict[str, Any]]) -> None:
    for evt in events:
        await _write_audit(evt)


# ── Report ───────────────────────────────────────────────────────────


# ── Coverage Report ───────────────────────────────────────────────────────


def generate_coverage_report(symbols: List[str]) -> Dict[str, Any]:
    """
    Generate a structured coverage report for all symbols.

    For each symbol: sessions_count, first_date, last_date, gap_count,
    source_mix (percent per source), last_ingested_at.
    """
    storage = get_historical_storage()
    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbols": {},
        "summary": {},
    }

    total_sessions = 0
    symbols_above_252 = 0
    symbols_above_60 = 0

    for symbol in symbols:
        meta = storage.get_metadata(symbol)
        records = storage.get_ohlcv(symbol)

        sessions = meta.total_sessions if meta else 0
        first_d = meta.first_date.isoformat() if meta and meta.first_date else None
        last_d = meta.last_date.isoformat() if meta and meta.last_date else None
        last_ingested = (
            meta.last_ingested_at.isoformat()
            if meta and hasattr(meta, "last_ingested_at") and meta.last_ingested_at
            else None
        )

        # Count gaps (missing weekdays between first and last date)
        gap_count = 0
        if records and len(records) >= 2:
            dates_set = {r.date for r in records}
            d = records[0].date
            end_d = records[-1].date
            while d <= end_d:
                if d.weekday() < 5 and d not in dates_set:
                    gap_count += 1
                d += timedelta(days=1)

        # Source mix
        source_counter: Counter = Counter()
        for r in records:
            source_counter[r.source] += 1
        source_mix = {}
        if records:
            for src, count in source_counter.items():
                source_mix[src] = round(count / len(records) * 100, 1)

        report["symbols"][symbol] = {
            "sessions_count": sessions,
            "first_date": first_d,
            "last_date": last_d,
            "gap_count": gap_count,
            "source_mix": source_mix,
            "last_ingested_at": last_ingested,
        }

        total_sessions += sessions
        if sessions >= 252:
            symbols_above_252 += 1
        if sessions >= 60:
            symbols_above_60 += 1

    report["summary"] = {
        "total_symbols": len(symbols),
        "total_sessions": total_sessions,
        "symbols_ge_252": symbols_above_252,
        "symbols_ge_60": symbols_above_60,
    }

    return report


def persist_coverage_report(report: Dict[str, Any]) -> str:
    """Write coverage report to JSON file and return path."""
    report_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "data"
    )
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, "coverage_report.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    return path


# ── Verification Report ──────────────────────────────────────────────────


def generate_verification_report(
    results: List[Dict[str, Any]],
    min_sessions: int,
    source: str = "ngnmarket",
) -> str:
    """Generate a human-readable verification report."""
    lines = [
        "=" * 70,
        "  BACKFILL VERIFICATION REPORT",
        f"  Generated: {datetime.now(timezone.utc).isoformat()}",
        f"  Source: {source}",
        f"  Minimum sessions required: {min_sessions}",
        "=" * 70,
        "",
    ]

    storage = get_historical_storage()
    passed = 0
    failed = 0

    lines.append(f"{'Symbol':<15} {'Sessions':>10} {'First':>12} {'Last':>12} {'Status':>10}")
    lines.append("-" * 70)

    for r in results:
        symbol = r["symbol"]
        meta = storage.get_metadata(symbol)
        sessions = meta.total_sessions if meta else 0
        first_d = meta.first_date.isoformat() if meta and meta.first_date else "N/A"
        last_d = meta.last_date.isoformat() if meta and meta.last_date else "N/A"

        if sessions >= min_sessions:
            status = "PASS"
            passed += 1
        else:
            status = "FAIL"
            failed += 1

        lines.append(f"{symbol:<15} {sessions:>10} {first_d:>12} {last_d:>12} {status:>10}")

    lines.append("-" * 70)
    lines.append(f"  PASSED: {passed}  |  FAILED: {failed}  |  TOTAL: {passed + failed}")
    lines.append("")

    gate_status = "PASS" if failed == 0 else "FAIL"
    lines.append(f"  G4 GATE STATUS: {gate_status}")
    lines.append("=" * 70)

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────


def resolve_date_window(
    start_date: Optional[str],
    end_date: Optional[str],
    days_back: int,
) -> tuple:
    """
    Resolve the date window from CLI args.

    Resolution rules:
      - If --start-date provided: use start_date..end_date (default today).
        Ignore --days-back.
      - If only --days-back: end=today, start=today - days_back.

    Returns: (start: date, end: date)
    """
    if start_date:
        s = date.fromisoformat(start_date)
        e = date.fromisoformat(end_date) if end_date else date.today()
        return s, e
    else:
        e = date.fromisoformat(end_date) if end_date else date.today()
        s = e - timedelta(days=days_back)
        return s, e


async def main(
    symbols: List[str],
    min_sessions: int,
    source: str = "ngnmarket",
    days_back: int = 120,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    logger.info(
        "Starting backfill: %d symbols, min_sessions=%d, source=%s",
        len(symbols), min_sessions, source,
    )

    results: List[Dict[str, Any]] = []
    storage = get_historical_storage()

    # ── Phase 1: ngnmarket (if source is ngnmarket or auto) ──
    if source in ("ngnmarket", "auto"):
        ingestion = HistoricalIngestionService()

        # ASI first
        logger.info("Backfilling ASI index history (ngnmarket)...")
        asi_result = await backfill_asi(ingestion)
        results.append(asi_result)

        # Symbols
        for symbol in symbols:
            logger.info("Backfilling %s (ngnmarket)...", symbol)
            result = await backfill_symbol(ingestion, symbol)
            results.append(result)
            logger.info(
                "  %s: fetched=%d stored=%d success=%s",
                symbol,
                result.get("sessions_fetched", 0),
                result.get("sessions_stored", 0),
                result.get("success", False),
            )

    # ── Phase 2: NGX PDF (if source is ngx_pdf or auto-fallback) ──
    if source == "ngx_pdf":
        # Pure PDF mode — fetch all symbols from PDFs
        logger.info("Backfilling via NGX Official List PDFs...")
        pdf_results = await backfill_via_ngx_pdf(
            symbols, days_back=days_back,
            start_date=start_date, end_date=end_date,
        )
        for symbol in symbols:
            if symbol in pdf_results:
                results.append(pdf_results[symbol])
            else:
                results.append({
                    "symbol": symbol, "success": False,
                    "sessions_fetched": 0, "sessions_stored": 0,
                })

    elif source == "auto":
        # Auto-fallback: identify symbols that still need more sessions
        insufficient: List[str] = []
        for symbol in symbols:
            meta = storage.get_metadata(symbol)
            current = meta.total_sessions if meta else 0
            if current < min_sessions:
                insufficient.append(symbol)
                logger.info(
                    "  %s has %d sessions (need %d) — will try NGX PDF",
                    symbol, current, min_sessions,
                )

        if insufficient:
            logger.info(
                "Auto-fallback: %d symbols below threshold, trying NGX PDF...",
                len(insufficient),
            )
            pdf_results = await backfill_via_ngx_pdf(
                insufficient, days_back=days_back,
                start_date=start_date, end_date=end_date,
            )
            # Update results for symbols that got PDF data
            for symbol, pdf_res in pdf_results.items():
                # Replace the ngnmarket result with merged info
                for i, r in enumerate(results):
                    if r.get("symbol") == symbol:
                        meta = storage.get_metadata(symbol)
                        results[i]["sessions_stored"] = (
                            meta.total_sessions if meta else 0
                        )
                        results[i]["source"] = "auto (ngnmarket + ngx_pdf)"
                        break
        else:
            logger.info("All symbols meet threshold — no PDF fallback needed.")

    # ── Reports ──
    report = generate_verification_report(results, min_sessions, source=source)
    print("\n" + report)

    # Write verification report
    report_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "backfill_report.txt"
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    logger.info("Verification report written to %s", report_path)

    # Coverage report (structured JSON)
    coverage = generate_coverage_report(symbols)
    coverage_path = persist_coverage_report(coverage)
    logger.info("Coverage report written to %s", coverage_path)
    logger.info(
        "Coverage summary: %d symbols, %d/%d >= 252 sessions, %d/%d >= 60 sessions",
        coverage["summary"]["total_symbols"],
        coverage["summary"]["symbols_ge_252"],
        coverage["summary"]["total_symbols"],
        coverage["summary"]["symbols_ge_60"],
        coverage["summary"]["total_symbols"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill historical OHLCV data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m app.cli.backfill                              # ngnmarket, full universe
  python -m app.cli.backfill --source ngx_pdf             # NGX PDF only
  python -m app.cli.backfill --source auto                # ngnmarket + PDF fallback
  python -m app.cli.backfill --source auto --days-back 252  # 1-year fallback window
  python -m app.cli.backfill --symbols MTNN,DANGCEM --source ngx_pdf
        """,
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated list of symbols (default: full universe)",
    )
    parser.add_argument(
        "--min-sessions",
        type=int,
        default=None,
        help="Minimum sessions required per symbol (default: from config)",
    )
    parser.add_argument(
        "--source",
        type=str,
        choices=["ngnmarket", "ngx_pdf", "auto"],
        default="ngnmarket",
        help="Data source: ngnmarket (default), ngx_pdf, or auto (ngnmarket + PDF fallback)",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=120,
        help="How many calendar days back to fetch for NGX PDF (default: 120)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date YYYY-MM-DD (if set, --days-back is ignored)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date YYYY-MM-DD (default: today)",
    )
    args = parser.parse_args()

    settings = get_settings()
    min_sessions = args.min_sessions or settings.MIN_OHLCV_SESSIONS

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_symbol_universe()

    start_d, end_d = resolve_date_window(
        args.start_date, args.end_date, args.days_back,
    )
    # Compute effective days_back for ngnmarket path
    effective_days_back = (end_d - start_d).days

    asyncio.run(main(
        symbols, min_sessions,
        source=args.source,
        days_back=effective_days_back,
        start_date=start_d,
        end_date=end_d,
    ))
