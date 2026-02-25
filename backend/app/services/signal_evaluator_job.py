"""
Scheduled Signal Evaluator for Paper Trading.

Periodically scans all PENDING signals, checks if enough forward OHLCV
data exists, and evaluates their performance (1d, 5d, 20d returns + hits).

Designed to run as a background task on app startup via asyncio.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from app.data.historical.storage import get_historical_storage
from app.services.signal_history import (
    get_signal_history_store,
    TrackedSignal,
    SignalStatus,
)

logger = logging.getLogger(__name__)

# How often to run the evaluator (seconds)
EVALUATION_INTERVAL_SECONDS = 3600  # 1 hour

# Minimum age before evaluating (trading days mapped to calendar days)
HORIZON_CALENDAR_DAYS = {
    1: 2,    # 1 trading day ≈ 2 calendar days buffer
    5: 8,    # 5 trading days ≈ 8 calendar days
    20: 30,  # 20 trading days ≈ 30 calendar days
}


def _check_directional_hit(bias_direction: str, return_pct: float) -> bool:
    """Check if actual return matches predicted direction."""
    if bias_direction == "bullish":
        return return_pct > 0
    elif bias_direction == "bearish":
        return return_pct < 0
    else:  # neutral
        return abs(return_pct) < 1.0


def evaluate_pending_signals() -> Dict[str, int]:
    """
    Evaluate all PENDING signals that have matured.

    Returns dict with counts: evaluated, skipped_no_data, already_evaluated, errors.
    """
    store = get_signal_history_store()
    storage = get_historical_storage()

    pending = store.get_pending_signals()
    if not pending:
        return {"evaluated": 0, "pending": 0, "skipped_no_data": 0, "errors": 0}

    now = datetime.now(timezone.utc)
    evaluated = 0
    skipped = 0
    errors = 0

    for signal in pending:
        try:
            symbol = signal.symbol
            signal_date = signal.generated_at.date()

            # Get all OHLCV records after signal date
            records = storage.get_ohlcv(
                symbol,
                start_date=signal_date + timedelta(days=1),
                limit=30,
            )

            if not records:
                skipped += 1
                continue

            # Build ordered list of forward trading days
            forward_closes = sorted(
                [(r.date, r.close) for r in records],
                key=lambda x: x[0],
            )

            base_price = signal.price_at_signal
            if base_price <= 0:
                errors += 1
                continue

            bias = signal.bias_direction
            updated = False

            # Evaluate 1-day forward
            if len(forward_closes) >= 1 and signal.price_1d is None:
                signal.price_1d = forward_closes[0][1]
                signal.return_1d = (signal.price_1d - base_price) / base_price * 100
                signal.hit_1d = _check_directional_hit(bias, signal.return_1d)
                updated = True

            # Evaluate 5-day forward
            if len(forward_closes) >= 5 and signal.price_5d is None:
                signal.price_5d = forward_closes[4][1]
                signal.return_5d = (signal.price_5d - base_price) / base_price * 100
                signal.hit_5d = _check_directional_hit(bias, signal.return_5d)
                updated = True

            # Evaluate 20-day forward
            if len(forward_closes) >= 20 and signal.price_20d is None:
                signal.price_20d = forward_closes[19][1]
                signal.return_20d = (signal.price_20d - base_price) / base_price * 100
                signal.hit_20d = _check_directional_hit(bias, signal.return_20d)
                updated = True

            if updated:
                # Mark as evaluated if we have at least 1d data
                if signal.price_1d is not None:
                    signal.status = SignalStatus.EVALUATED
                    signal.evaluated_at = now
                store.update_signal(signal)
                evaluated += 1
            else:
                skipped += 1

        except Exception as e:
            logger.error("Error evaluating signal %s: %s", signal.signal_id, e)
            errors += 1

    logger.info(
        "Signal evaluation complete: %d evaluated, %d skipped (no data), %d errors, %d still pending",
        evaluated,
        skipped,
        errors,
        len(pending) - evaluated - skipped - errors,
    )

    return {
        "evaluated": evaluated,
        "pending": len(pending),
        "skipped_no_data": skipped,
        "errors": errors,
    }


async def signal_evaluator_loop():
    """
    Background loop that periodically evaluates matured signals.

    Runs forever (until cancelled). Safe to call from asyncio task.
    """
    logger.info(
        "Signal evaluator started (interval: %ds)",
        EVALUATION_INTERVAL_SECONDS,
    )

    while True:
        try:
            # Run evaluation in a thread to avoid blocking the event loop
            # (SQLite operations are synchronous)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, evaluate_pending_signals)

            if result["evaluated"] > 0:
                logger.info("Evaluator cycle: %s", result)

        except asyncio.CancelledError:
            logger.info("Signal evaluator cancelled")
            break
        except Exception as e:
            logger.error("Signal evaluator error: %s", e)

        await asyncio.sleep(EVALUATION_INTERVAL_SECONDS)
