"""
Performance Service for NSE Trader (Phase 3 Re-enablement).

Provides truthful performance tracking using ONLY real stored historical OHLCV data.
No simulated backfills. No misleading metrics.

Features:
- Readiness checking based on historical storage
- Forward return computation from stored OHLCV
- Signal tracking with historical validation
- Transparent handling of insufficient data
"""
import logging
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from enum import Enum

from app.data.historical.storage import (
    HistoricalOHLCVStorage,
    get_historical_storage,
    IngestionStatus,
)
from app.services.historical_coverage import (
    HistoricalCoverageService,
    get_historical_coverage_service,
    MINIMUM_SESSIONS_FOR_RECOMMENDATION,
)
from app.services.signal_history import (
    SignalHistoryStore,
    TrackedSignal,
    SignalStatus,
    get_signal_history_store,
)

logger = logging.getLogger(__name__)


class PerformanceReadiness(str, Enum):
    """Status of performance tracking system."""
    READY = "READY"                    # At least one symbol has sufficient history
    NOT_READY = "NOT_READY"            # No symbols with sufficient history
    PARTIALLY_READY = "PARTIALLY_READY"  # Some symbols ready, others not


class UnevaluatedReason(str, Enum):
    """Reasons why a signal could not be evaluated."""
    NOT_ENOUGH_FORWARD_DATA = "NOT_ENOUGH_FORWARD_DATA"
    STALE_DATA = "STALE_DATA"
    NO_HISTORICAL_DATA = "NO_HISTORICAL_DATA"
    INVALID_PRICE = "INVALID_PRICE"
    PENDING_EVALUATION = "PENDING_EVALUATION"


@dataclass
class TrackedSignalWithHistory:
    """Extended tracked signal with historical data context."""
    signal: TrackedSignal
    historical_source: str = "NGNMARKET_HISTORICAL"
    ingestion_status_at_signal: Optional[str] = None
    last_date_at_signal: Optional[date] = None
    sessions_available_at_signal: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        result = self.signal.to_dict()
        result["historical_context"] = {
            "source": self.historical_source,
            "ingestion_status_at_signal": self.ingestion_status_at_signal,
            "last_date_at_signal": self.last_date_at_signal.isoformat() if self.last_date_at_signal else None,
            "sessions_available_at_signal": self.sessions_available_at_signal,
        }
        return result


@dataclass
class EvaluationResult:
    """Result of evaluating a signal's forward returns."""
    signal_id: str
    evaluated: bool
    reason: Optional[UnevaluatedReason] = None
    reason_details: Optional[str] = None
    
    # Forward prices (if available)
    price_1d: Optional[float] = None
    price_5d: Optional[float] = None
    price_20d: Optional[float] = None
    
    # Returns (if available)
    return_1d: Optional[float] = None
    return_5d: Optional[float] = None
    return_20d: Optional[float] = None
    
    # Hits (if available)
    hit_1d: Optional[bool] = None
    hit_5d: Optional[bool] = None
    hit_20d: Optional[bool] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "evaluated": self.evaluated,
            "reason": self.reason.value if self.reason else None,
            "reason_details": self.reason_details,
            "forward_prices": {
                "1d": self.price_1d,
                "5d": self.price_5d,
                "20d": self.price_20d,
            },
            "returns": {
                "1d": round(self.return_1d, 4) if self.return_1d is not None else None,
                "5d": round(self.return_5d, 4) if self.return_5d is not None else None,
                "20d": round(self.return_20d, 4) if self.return_20d is not None else None,
            },
            "hits": {
                "1d": self.hit_1d,
                "5d": self.hit_5d,
                "20d": self.hit_20d,
            },
        }


# Educational explanations for status codes (Phase 5)
STATUS_EXPLANATIONS = {
    "NO_SIGNALS": {
        "what_this_means": (
            "No trading signals have been tracked in the specified time period. "
            "This is normal for new systems or periods with insufficient data."
        ),
        "user_action": "Signals are tracked automatically when conditions are met. No action required.",
    },
    "NO_EVALUATED_SIGNALS": {
        "what_this_means": (
            "Signals were tracked but none could be evaluated for performance. "
            "This typically means forward price data is not yet available."
        ),
        "user_action": "Wait for more market data to be collected for evaluation.",
    },
    "INSUFFICIENT_SAMPLE": {
        "what_this_means": (
            "There are not enough evaluated signals to compute statistically "
            "meaningful metrics. This is normal for new systems or symbols."
        ),
        "user_action": "Performance metrics will become available as more signals are evaluated over time.",
    },
    "OK": {
        "what_this_means": "Performance metrics have been computed successfully from real data.",
        "user_action": None,
    },
}


@dataclass
class PerformanceResponse:
    """Standard performance API response with transparency fields."""
    status: str
    data: Dict[str, Any]
    evaluated_signal_count: int = 0
    unevaluated_signal_count: int = 0
    unevaluated_reasons: Dict[str, int] = field(default_factory=dict)
    stale_symbols_excluded_count: int = 0
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        # Get educational explanation for this status
        explanation = STATUS_EXPLANATIONS.get(self.status, {})
        
        result = {
            "status": self.status,
            "data": self.data,
            "transparency": {
                "evaluated_signal_count": self.evaluated_signal_count,
                "unevaluated_signal_count": self.unevaluated_signal_count,
                "unevaluated_reasons": self.unevaluated_reasons,
                "stale_symbols_excluded_count": self.stale_symbols_excluded_count,
            },
            "computed_at": self.computed_at.isoformat(),
        }
        
        # Add educational fields if status is not OK
        if self.status != "OK" and explanation:
            result["explanation"] = explanation
        
        return result


class PerformanceService:
    """
    Service for truthful performance tracking using real historical data.
    
    Key principles:
    - Uses ONLY stored validated OHLCV data
    - No web calls inside evaluator
    - Transparent about what couldn't be evaluated and why
    - No fabrication or interpolation
    """
    
    # Minimum signals required for meaningful calibration
    MIN_SIGNALS_FOR_CALIBRATION = 10
    
    def __init__(
        self,
        storage: Optional[HistoricalOHLCVStorage] = None,
        coverage_service: Optional[HistoricalCoverageService] = None,
        signal_store: Optional[SignalHistoryStore] = None,
    ):
        self._storage = storage
        self._coverage_service = coverage_service
        self._signal_store = signal_store
    
    @property
    def storage(self) -> HistoricalOHLCVStorage:
        if self._storage is None:
            self._storage = get_historical_storage()
        return self._storage
    
    @property
    def coverage_service(self) -> HistoricalCoverageService:
        if self._coverage_service is None:
            self._coverage_service = get_historical_coverage_service()
        return self._coverage_service
    
    @property
    def signal_store(self) -> SignalHistoryStore:
        if self._signal_store is None:
            self._signal_store = get_signal_history_store()
        return self._signal_store
    
    def get_readiness_status(self) -> Dict[str, Any]:
        """
        Check if performance tracking is ready.
        
        Returns READY if:
        - Historical storage exists
        - At least one symbol has sufficient sessions (>= 50)
        """
        try:
            stats = self.storage.get_stats()
            all_metadata = self.storage.get_all_metadata()
            
            total_symbols = stats.get("total_symbols", 0)
            total_records = stats.get("total_records", 0)
            
            # Count symbols with sufficient history
            symbols_ready = [
                m for m in all_metadata
                if m.total_sessions >= MINIMUM_SESSIONS_FOR_RECOMMENDATION
                and not m.is_stale()
            ]
            
            # Count stale symbols
            stale_symbols = [m for m in all_metadata if m.is_stale()]
            
            if not all_metadata:
                return {
                    "status": PerformanceReadiness.NOT_READY.value,
                    "reasons": [
                        "No historical data has been ingested",
                        "Run historical ingestion to enable performance tracking"
                    ],
                    "symbols_total": 0,
                    "symbols_ready": 0,
                    "symbols_stale": 0,
                    "total_records": 0,
                    "minimum_sessions_required": MINIMUM_SESSIONS_FOR_RECOMMENDATION,
                }
            
            if not symbols_ready:
                reasons = []
                if stale_symbols:
                    reasons.append(f"{len(stale_symbols)} symbols have stale data")
                else:
                    reasons.append("No symbols have sufficient history")
                reasons.append(f"Minimum required: {MINIMUM_SESSIONS_FOR_RECOMMENDATION} sessions")
                
                return {
                    "status": PerformanceReadiness.NOT_READY.value,
                    "reasons": reasons,
                    "symbols_total": total_symbols,
                    "symbols_ready": 0,
                    "symbols_stale": len(stale_symbols),
                    "total_records": total_records,
                    "minimum_sessions_required": MINIMUM_SESSIONS_FOR_RECOMMENDATION,
                }
            
            status = PerformanceReadiness.READY if len(symbols_ready) == len(all_metadata) else PerformanceReadiness.PARTIALLY_READY
            
            return {
                "status": status.value,
                "symbols_total": total_symbols,
                "symbols_ready": len(symbols_ready),
                "symbols_stale": len(stale_symbols),
                "total_records": total_records,
                "minimum_sessions_required": MINIMUM_SESSIONS_FOR_RECOMMENDATION,
                "ready_symbols": [m.symbol for m in symbols_ready[:10]],  # First 10
            }
            
        except Exception as e:
            logger.error("Error checking readiness: %s", e)
            return {
                "status": PerformanceReadiness.NOT_READY.value,
                "reasons": [f"Error accessing historical storage: {str(e)}"],
                "symbols_total": 0,
                "symbols_ready": 0,
                "symbols_stale": 0,
                "total_records": 0,
            }
    
    def can_track_signal(self, symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a signal can be tracked for performance evaluation.
        
        Requirements:
        - Historical coverage is sufficient
        - Data is not stale
        
        Returns:
            Tuple of (can_track, reason_if_not)
        """
        coverage = self.coverage_service.get_coverage(symbol)
        
        if not coverage.is_sufficient:
            return False, f"Insufficient history: {coverage.sessions_available}/{coverage.required_sessions} sessions"
        
        if coverage.is_stale:
            return False, f"Stale data: {coverage.stale_reason}"
        
        return True, None
    
    def track_signal_with_validation(
        self,
        symbol: str,
        bias_direction: str,
        bias_probability: int,
        regime: str,
        regime_confidence: float,
        data_confidence_score: float,
        price_at_signal: float,
        horizon: str,
        **kwargs
    ) -> Tuple[Optional[TrackedSignal], Optional[str]]:
        """
        Track a signal only if historical data requirements are met.
        
        Returns:
            Tuple of (tracked_signal, rejection_reason)
        """
        can_track, reason = self.can_track_signal(symbol)
        
        if not can_track:
            logger.info("Signal for %s not tracked: %s", symbol, reason)
            return None, reason
        
        # Get historical context at signal time
        coverage = self.coverage_service.get_coverage(symbol)
        metadata = self.storage.get_metadata(symbol)
        
        # Store the signal
        signal = self.signal_store.store_signal(
            symbol=symbol,
            bias_direction=bias_direction,
            bias_probability=bias_probability,
            regime=regime,
            regime_confidence=regime_confidence,
            data_confidence_score=data_confidence_score,
            price_at_signal=price_at_signal,
            horizon=horizon,
            **kwargs
        )
        
        logger.info(
            "Tracked signal %s for %s with %d sessions available",
            signal.signal_id, symbol, coverage.sessions_available
        )
        
        return signal, None
    
    def get_forward_prices(
        self,
        symbol: str,
        signal_date: date,
        horizons: List[int] = [1, 5, 20]
    ) -> Dict[int, Optional[float]]:
        """
        Get forward prices from stored OHLCV data.
        
        Args:
            symbol: Stock symbol
            signal_date: Date of the signal
            horizons: List of trading days forward to look
            
        Returns:
            Dict mapping horizon to close price (or None if not available)
        """
        result = {}
        
        # Get all OHLCV records after signal date
        records = self.storage.get_ohlcv(
            symbol,
            start_date=signal_date + timedelta(days=1),
            limit=max(horizons) + 5  # Buffer for weekends
        )
        
        # Build date -> price map
        price_by_date = {r.date: r.close for r in records}
        
        # For each horizon, find the Nth trading day
        trading_days_seen = 0
        sorted_dates = sorted(price_by_date.keys())
        
        for horizon in sorted(horizons):
            result[horizon] = None
            
            # Find the Nth trading day
            if len(sorted_dates) >= horizon:
                target_date = sorted_dates[horizon - 1]
                result[horizon] = price_by_date[target_date]
        
        return result
    
    def evaluate_signal_from_storage(
        self,
        signal: TrackedSignal
    ) -> EvaluationResult:
        """
        Evaluate a signal's forward returns using stored OHLCV data.
        
        No web calls - uses only stored data.
        """
        symbol = signal.symbol
        signal_date = signal.generated_at.date()
        
        # Check if we have historical data for this symbol
        metadata = self.storage.get_metadata(symbol)
        
        if not metadata:
            return EvaluationResult(
                signal_id=signal.signal_id,
                evaluated=False,
                reason=UnevaluatedReason.NO_HISTORICAL_DATA,
                reason_details=f"No historical data stored for {symbol}"
            )
        
        if metadata.is_stale():
            return EvaluationResult(
                signal_id=signal.signal_id,
                evaluated=False,
                reason=UnevaluatedReason.STALE_DATA,
                reason_details=metadata.get_stale_reason()
            )
        
        # Get forward prices
        forward_prices = self.get_forward_prices(symbol, signal_date)
        
        # Check if we have any forward data
        if all(p is None for p in forward_prices.values()):
            return EvaluationResult(
                signal_id=signal.signal_id,
                evaluated=False,
                reason=UnevaluatedReason.NOT_ENOUGH_FORWARD_DATA,
                reason_details=f"No trading days available after {signal_date}"
            )
        
        # Calculate returns and hits
        base_price = signal.price_at_signal
        if base_price <= 0:
            return EvaluationResult(
                signal_id=signal.signal_id,
                evaluated=False,
                reason=UnevaluatedReason.INVALID_PRICE,
                reason_details=f"Invalid price at signal: {base_price}"
            )
        
        result = EvaluationResult(
            signal_id=signal.signal_id,
            evaluated=True,
            price_1d=forward_prices.get(1),
            price_5d=forward_prices.get(5),
            price_20d=forward_prices.get(20),
        )
        
        bias = signal.bias_direction
        
        # Calculate 1-day
        if result.price_1d is not None:
            result.return_1d = (result.price_1d - base_price) / base_price * 100
            result.hit_1d = self._check_directional_hit(bias, result.return_1d)
        
        # Calculate 5-day
        if result.price_5d is not None:
            result.return_5d = (result.price_5d - base_price) / base_price * 100
            result.hit_5d = self._check_directional_hit(bias, result.return_5d)
        
        # Calculate 20-day
        if result.price_20d is not None:
            result.return_20d = (result.price_20d - base_price) / base_price * 100
            result.hit_20d = self._check_directional_hit(bias, result.return_20d)
        
        return result
    
    def _check_directional_hit(self, bias_direction: str, return_pct: float) -> bool:
        """Check if actual return matches predicted direction."""
        if bias_direction == "bullish":
            return return_pct > 0
        elif bias_direction == "bearish":
            return return_pct < 0
        else:  # neutral
            return abs(return_pct) < 1.0
    
    def get_performance_summary(self, days: int = 30) -> PerformanceResponse:
        """
        Get overall performance summary.
        
        Returns transparent metrics including what couldn't be evaluated.
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # Get signals in range
        all_signals = self.signal_store.get_signals_in_range(start_date, end_date)
        
        if not all_signals:
            return PerformanceResponse(
                status="NO_SIGNALS",
                data={"message": f"No signals tracked in the last {days} days"},
                evaluated_signal_count=0,
                unevaluated_signal_count=0,
            )
        
        # Evaluate signals
        evaluated_signals = []
        unevaluated_reasons: Dict[str, int] = {}
        stale_excluded = 0
        
        for signal in all_signals:
            result = self.evaluate_signal_from_storage(signal)
            
            if result.evaluated:
                evaluated_signals.append((signal, result))
            else:
                reason = result.reason.value if result.reason else "UNKNOWN"
                unevaluated_reasons[reason] = unevaluated_reasons.get(reason, 0) + 1
                
                if result.reason == UnevaluatedReason.STALE_DATA:
                    stale_excluded += 1
        
        if not evaluated_signals:
            return PerformanceResponse(
                status="NO_EVALUATED_SIGNALS",
                data={
                    "message": "No signals could be evaluated",
                    "period_days": days,
                },
                evaluated_signal_count=0,
                unevaluated_signal_count=len(all_signals),
                unevaluated_reasons=unevaluated_reasons,
                stale_symbols_excluded_count=stale_excluded,
            )
        
        # Calculate aggregate metrics
        hit_1d_values = [r.hit_1d for _, r in evaluated_signals if r.hit_1d is not None]
        hit_5d_values = [r.hit_5d for _, r in evaluated_signals if r.hit_5d is not None]
        hit_20d_values = [r.hit_20d for _, r in evaluated_signals if r.hit_20d is not None]
        
        return_1d_values = [r.return_1d for _, r in evaluated_signals if r.return_1d is not None]
        return_5d_values = [r.return_5d for _, r in evaluated_signals if r.return_5d is not None]
        return_20d_values = [r.return_20d for _, r in evaluated_signals if r.return_20d is not None]
        
        data = {
            "period_days": days,
            "hit_rates": {
                "1d": round(sum(hit_1d_values) / len(hit_1d_values), 4) if hit_1d_values else None,
                "5d": round(sum(hit_5d_values) / len(hit_5d_values), 4) if hit_5d_values else None,
                "20d": round(sum(hit_20d_values) / len(hit_20d_values), 4) if hit_20d_values else None,
            },
            "avg_returns": {
                "1d": round(sum(return_1d_values) / len(return_1d_values), 4) if return_1d_values else None,
                "5d": round(sum(return_5d_values) / len(return_5d_values), 4) if return_5d_values else None,
                "20d": round(sum(return_20d_values) / len(return_20d_values), 4) if return_20d_values else None,
            },
            "sample_sizes": {
                "1d": len(hit_1d_values),
                "5d": len(hit_5d_values),
                "20d": len(hit_20d_values),
            },
        }
        
        return PerformanceResponse(
            status="OK",
            data=data,
            evaluated_signal_count=len(evaluated_signals),
            unevaluated_signal_count=len(all_signals) - len(evaluated_signals),
            unevaluated_reasons=unevaluated_reasons,
            stale_symbols_excluded_count=stale_excluded,
        )
    
    def get_calibration_metrics(self, days: int = 30) -> PerformanceResponse:
        """
        Get calibration metrics.
        
        Returns INSUFFICIENT_SAMPLE if not enough signals.
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        all_signals = self.signal_store.get_signals_in_range(start_date, end_date)
        
        # Evaluate signals
        evaluated = []
        unevaluated_reasons: Dict[str, int] = {}
        
        for signal in all_signals:
            result = self.evaluate_signal_from_storage(signal)
            if result.evaluated and result.hit_5d is not None:
                evaluated.append((signal, result))
            elif result.reason:
                reason = result.reason.value
                unevaluated_reasons[reason] = unevaluated_reasons.get(reason, 0) + 1
        
        if len(evaluated) < self.MIN_SIGNALS_FOR_CALIBRATION:
            return PerformanceResponse(
                status="INSUFFICIENT_SAMPLE",
                data={
                    "message": f"Need at least {self.MIN_SIGNALS_FOR_CALIBRATION} evaluated signals for calibration",
                    "current_sample": len(evaluated),
                    "required_sample": self.MIN_SIGNALS_FOR_CALIBRATION,
                },
                evaluated_signal_count=len(evaluated),
                unevaluated_signal_count=len(all_signals) - len(evaluated),
                unevaluated_reasons=unevaluated_reasons,
            )
        
        # Compute calibration by probability bucket
        buckets = {
            "low": {"range": "0-40%", "signals": [], "avg_prob": 0, "hit_rate": None},
            "neutral": {"range": "40-60%", "signals": [], "avg_prob": 0, "hit_rate": None},
            "moderate": {"range": "60-80%", "signals": [], "avg_prob": 0, "hit_rate": None},
            "high": {"range": "80-100%", "signals": [], "avg_prob": 0, "hit_rate": None},
        }
        
        for signal, result in evaluated:
            prob = signal.bias_probability
            if prob < 40:
                buckets["low"]["signals"].append((signal, result))
            elif prob < 60:
                buckets["neutral"]["signals"].append((signal, result))
            elif prob < 80:
                buckets["moderate"]["signals"].append((signal, result))
            else:
                buckets["high"]["signals"].append((signal, result))
        
        calibration_data = {}
        total_calibration_error = 0
        total_weight = 0
        
        for bucket_name, bucket_data in buckets.items():
            signals = bucket_data["signals"]
            if not signals:
                calibration_data[bucket_name] = {
                    "range": bucket_data["range"],
                    "count": 0,
                    "avg_probability": None,
                    "actual_hit_rate": None,
                    "calibration_error": None,
                }
                continue
            
            avg_prob = sum(s.bias_probability for s, _ in signals) / len(signals)
            hit_rate = sum(1 for _, r in signals if r.hit_5d) / len(signals)
            cal_error = abs(avg_prob / 100 - hit_rate)
            
            calibration_data[bucket_name] = {
                "range": bucket_data["range"],
                "count": len(signals),
                "avg_probability": round(avg_prob, 2),
                "actual_hit_rate": round(hit_rate, 4),
                "calibration_error": round(cal_error, 4),
            }
            
            total_calibration_error += cal_error * len(signals)
            total_weight += len(signals)
        
        overall_calibration_error = total_calibration_error / total_weight if total_weight > 0 else None
        
        return PerformanceResponse(
            status="OK",
            data={
                "period_days": days,
                "overall_calibration_error": round(overall_calibration_error, 4) if overall_calibration_error else None,
                "by_probability_bucket": calibration_data,
            },
            evaluated_signal_count=len(evaluated),
            unevaluated_signal_count=len(all_signals) - len(evaluated),
            unevaluated_reasons=unevaluated_reasons,
        )
    
    def get_hit_rates(self, days: int = 30) -> PerformanceResponse:
        """Get simple hit rate summary."""
        return self.get_performance_summary(days)
    
    def get_by_direction(self, days: int = 30) -> PerformanceResponse:
        """Get performance broken down by bias direction."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        all_signals = self.signal_store.get_signals_in_range(start_date, end_date)
        
        # Group by direction
        by_direction: Dict[str, List] = {"bullish": [], "bearish": [], "neutral": []}
        unevaluated_reasons: Dict[str, int] = {}
        
        for signal in all_signals:
            result = self.evaluate_signal_from_storage(signal)
            direction = signal.bias_direction
            
            if result.evaluated:
                by_direction.setdefault(direction, []).append((signal, result))
            elif result.reason:
                reason = result.reason.value
                unevaluated_reasons[reason] = unevaluated_reasons.get(reason, 0) + 1
        
        direction_data = {}
        total_evaluated = 0
        
        for direction, signals in by_direction.items():
            if not signals:
                direction_data[direction] = {"count": 0, "hit_rates": {}, "avg_returns": {}}
                continue
            
            total_evaluated += len(signals)
            
            hit_5d_values = [r.hit_5d for _, r in signals if r.hit_5d is not None]
            return_5d_values = [r.return_5d for _, r in signals if r.return_5d is not None]
            
            direction_data[direction] = {
                "count": len(signals),
                "hit_rates": {
                    "5d": round(sum(hit_5d_values) / len(hit_5d_values), 4) if hit_5d_values else None,
                },
                "avg_returns": {
                    "5d": round(sum(return_5d_values) / len(return_5d_values), 4) if return_5d_values else None,
                },
            }
        
        return PerformanceResponse(
            status="OK",
            data={
                "period_days": days,
                "by_direction": direction_data,
            },
            evaluated_signal_count=total_evaluated,
            unevaluated_signal_count=len(all_signals) - total_evaluated,
            unevaluated_reasons=unevaluated_reasons,
        )
    
    def get_by_regime(self, days: int = 30) -> PerformanceResponse:
        """Get performance broken down by market regime."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        all_signals = self.signal_store.get_signals_in_range(start_date, end_date)
        
        # Group by regime
        by_regime: Dict[str, List] = {}
        unevaluated_reasons: Dict[str, int] = {}
        
        for signal in all_signals:
            result = self.evaluate_signal_from_storage(signal)
            regime = signal.regime
            
            if result.evaluated:
                by_regime.setdefault(regime, []).append((signal, result))
            elif result.reason:
                reason = result.reason.value
                unevaluated_reasons[reason] = unevaluated_reasons.get(reason, 0) + 1
        
        regime_data = {}
        total_evaluated = 0
        
        for regime, signals in by_regime.items():
            total_evaluated += len(signals)
            
            hit_5d_values = [r.hit_5d for _, r in signals if r.hit_5d is not None]
            return_5d_values = [r.return_5d for _, r in signals if r.return_5d is not None]
            
            regime_data[regime] = {
                "count": len(signals),
                "hit_rates": {
                    "5d": round(sum(hit_5d_values) / len(hit_5d_values), 4) if hit_5d_values else None,
                },
                "avg_returns": {
                    "5d": round(sum(return_5d_values) / len(return_5d_values), 4) if return_5d_values else None,
                },
            }
        
        return PerformanceResponse(
            status="OK",
            data={
                "period_days": days,
                "by_regime": regime_data,
            },
            evaluated_signal_count=total_evaluated,
            unevaluated_signal_count=len(all_signals) - total_evaluated,
            unevaluated_reasons=unevaluated_reasons,
        )
    
    def get_symbol_performance(self, symbol: str) -> PerformanceResponse:
        """Get performance for a specific symbol."""
        signals = self.signal_store.get_signals_by_symbol(symbol)
        
        if not signals:
            return PerformanceResponse(
                status="NO_SIGNALS",
                data={
                    "symbol": symbol,
                    "message": f"No signals tracked for {symbol}",
                },
                evaluated_signal_count=0,
                unevaluated_signal_count=0,
            )
        
        evaluated = []
        unevaluated_reasons: Dict[str, int] = {}
        
        for signal in signals:
            result = self.evaluate_signal_from_storage(signal)
            if result.evaluated:
                evaluated.append((signal, result))
            elif result.reason:
                reason = result.reason.value
                unevaluated_reasons[reason] = unevaluated_reasons.get(reason, 0) + 1
        
        if not evaluated:
            return PerformanceResponse(
                status="NO_EVALUATED_SIGNALS",
                data={
                    "symbol": symbol,
                    "message": "No signals could be evaluated",
                },
                evaluated_signal_count=0,
                unevaluated_signal_count=len(signals),
                unevaluated_reasons=unevaluated_reasons,
            )
        
        hit_5d_values = [r.hit_5d for _, r in evaluated if r.hit_5d is not None]
        return_5d_values = [r.return_5d for _, r in evaluated if r.return_5d is not None]
        
        return PerformanceResponse(
            status="OK",
            data={
                "symbol": symbol,
                "total_signals": len(signals),
                "hit_rates": {
                    "5d": round(sum(hit_5d_values) / len(hit_5d_values), 4) if hit_5d_values else None,
                },
                "avg_returns": {
                    "5d": round(sum(return_5d_values) / len(return_5d_values), 4) if return_5d_values else None,
                },
            },
            evaluated_signal_count=len(evaluated),
            unevaluated_signal_count=len(signals) - len(evaluated),
            unevaluated_reasons=unevaluated_reasons,
        )
    
    def list_signals(
        self,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        direction: Optional[str] = None,
        limit: int = 50
    ) -> PerformanceResponse:
        """List tracked signals with optional filters."""
        all_signals = self.signal_store.get_all_signals()
        
        # Apply filters
        filtered = all_signals
        
        if symbol:
            filtered = [s for s in filtered if s.symbol == symbol.upper()]
        
        if direction:
            filtered = [s for s in filtered if s.bias_direction == direction.lower()]
        
        if status:
            filtered = [s for s in filtered if s.status.value == status.lower()]
        
        # Limit
        filtered = filtered[:limit]
        
        return PerformanceResponse(
            status="OK",
            data={
                "signals": [s.to_dict() for s in filtered],
                "count": len(filtered),
                "total_available": len(all_signals),
            },
            evaluated_signal_count=len([s for s in all_signals if s.status == SignalStatus.EVALUATED]),
            unevaluated_signal_count=len([s for s in all_signals if s.status != SignalStatus.EVALUATED]),
        )


# Singleton instance
_service_instance: Optional[PerformanceService] = None


def get_performance_service() -> PerformanceService:
    """Get singleton performance service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = PerformanceService()
    return _service_instance
