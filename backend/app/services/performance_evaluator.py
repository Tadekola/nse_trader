"""
Performance Evaluator Module for NSE Trader.

Evaluates signal performance by tracking forward returns and computing
directional correctness metrics. This is a READ-ONLY analytics system
that does NOT feed results back into live signal generation.

Features:
- Forward return calculation (1d, 5d, 20d)
- Directional hit rate computation
- Hit rate by bias direction and regime
- Calibration error (predicted probability vs actual hit rate)
- Aggregated performance metrics
"""
import logging
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import statistics

from app.services.signal_history import (
    SignalHistoryStore,
    TrackedSignal,
    SignalStatus,
    get_signal_history_store
)

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """
    Aggregated performance metrics for a set of signals.
    
    Attributes:
        total_signals: Total number of signals evaluated
        hit_rate_1d: Directional hit rate at 1 day
        hit_rate_5d: Directional hit rate at 5 days
        hit_rate_20d: Directional hit rate at 20 days
        avg_return_1d: Average return at 1 day
        avg_return_5d: Average return at 5 days
        avg_return_20d: Average return at 20 days
        calibration_error: Mean absolute error between predicted prob and actual hit rate
        by_direction: Metrics broken down by bias direction
        by_regime: Metrics broken down by market regime
        by_probability_bucket: Calibration by probability range
    """
    total_signals: int
    hit_rate_1d: Optional[float]
    hit_rate_5d: Optional[float]
    hit_rate_20d: Optional[float]
    avg_return_1d: Optional[float]
    avg_return_5d: Optional[float]
    avg_return_20d: Optional[float]
    calibration_error: Optional[float]
    by_direction: Dict[str, Dict[str, Any]]
    by_regime: Dict[str, Dict[str, Any]]
    by_probability_bucket: Dict[str, Dict[str, Any]]
    evaluation_period: Dict[str, str]
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "total_signals": self.total_signals,
            "hit_rates": {
                "1d": round(self.hit_rate_1d, 4) if self.hit_rate_1d is not None else None,
                "5d": round(self.hit_rate_5d, 4) if self.hit_rate_5d is not None else None,
                "20d": round(self.hit_rate_20d, 4) if self.hit_rate_20d is not None else None
            },
            "avg_returns": {
                "1d": round(self.avg_return_1d, 4) if self.avg_return_1d is not None else None,
                "5d": round(self.avg_return_5d, 4) if self.avg_return_5d is not None else None,
                "20d": round(self.avg_return_20d, 4) if self.avg_return_20d is not None else None
            },
            "calibration_error": round(self.calibration_error, 4) if self.calibration_error is not None else None,
            "by_direction": self.by_direction,
            "by_regime": self.by_regime,
            "by_probability_bucket": self.by_probability_bucket,
            "evaluation_period": self.evaluation_period,
            "computed_at": self.computed_at.isoformat()
        }


class PerformanceEvaluator:
    """
    Evaluates signal performance using forward returns.
    
    Computes directional correctness (hit rate) rather than P&L,
    as the system does not execute trades.
    
    Evaluation windows:
    - 1-day: Short-term directional accuracy
    - 5-day: Swing trading accuracy
    - 20-day: Position trading accuracy
    """
    
    # Probability buckets for calibration analysis
    PROBABILITY_BUCKETS = [
        (0, 40, "low"),
        (40, 60, "neutral"),
        (60, 80, "moderate"),
        (80, 100, "high")
    ]
    
    def __init__(self, store: Optional[SignalHistoryStore] = None):
        self.store = store or get_signal_history_store()
    
    def evaluate_signal(
        self,
        signal: TrackedSignal,
        price_1d: Optional[float] = None,
        price_5d: Optional[float] = None,
        price_20d: Optional[float] = None
    ) -> TrackedSignal:
        """
        Evaluate a single signal's forward performance.
        
        Calculates returns and directional correctness for each horizon.
        A "hit" is when the price moved in the direction predicted by the bias.
        
        Args:
            signal: The signal to evaluate
            price_1d: Price 1 trading day after signal
            price_5d: Price 5 trading days after signal
            price_20d: Price 20 trading days after signal
        
        Returns:
            Updated signal with performance data
        """
        if signal.price_at_signal <= 0:
            logger.warning("Invalid price_at_signal for %s", signal.signal_id)
            signal.status = SignalStatus.INVALIDATED
            return signal
        
        base_price = signal.price_at_signal
        bias = signal.bias_direction
        
        # Calculate 1-day performance
        if price_1d is not None:
            signal.price_1d = price_1d
            signal.return_1d = (price_1d - base_price) / base_price * 100
            signal.hit_1d = self._check_directional_hit(bias, signal.return_1d)
        
        # Calculate 5-day performance
        if price_5d is not None:
            signal.price_5d = price_5d
            signal.return_5d = (price_5d - base_price) / base_price * 100
            signal.hit_5d = self._check_directional_hit(bias, signal.return_5d)
        
        # Calculate 20-day performance
        if price_20d is not None:
            signal.price_20d = price_20d
            signal.return_20d = (price_20d - base_price) / base_price * 100
            signal.hit_20d = self._check_directional_hit(bias, signal.return_20d)
        
        # Update status if we have at least 1d data
        if price_1d is not None:
            signal.status = SignalStatus.EVALUATED
            signal.evaluated_at = datetime.now(timezone.utc)
        
        # Update in store
        self.store.update_signal(signal)
        
        logger.debug(
            "Evaluated signal %s: 1d=%s 5d=%s 20d=%s",
            signal.signal_id,
            f"{signal.return_1d:.2f}%" if signal.return_1d else "N/A",
            f"{signal.return_5d:.2f}%" if signal.return_5d else "N/A",
            f"{signal.return_20d:.2f}%" if signal.return_20d else "N/A"
        )
        
        return signal
    
    def _check_directional_hit(self, bias_direction: str, return_pct: float) -> bool:
        """
        Check if the actual return matches the predicted direction.
        
        Rules:
        - Bullish: Hit if return > 0
        - Bearish: Hit if return < 0
        - Neutral: Hit if |return| < 1% (stayed relatively flat)
        
        Args:
            bias_direction: bullish | neutral | bearish
            return_pct: Actual return percentage
        
        Returns:
            True if direction was correct
        """
        if bias_direction == "bullish":
            return return_pct > 0
        elif bias_direction == "bearish":
            return return_pct < 0
        else:  # neutral
            return abs(return_pct) < 1.0  # Within 1% is considered "flat"
    
    def compute_metrics(
        self,
        signals: Optional[List[TrackedSignal]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> PerformanceMetrics:
        """
        Compute aggregated performance metrics.
        
        Args:
            signals: List of signals to analyze (defaults to all evaluated)
            start_date: Filter signals generated after this date
            end_date: Filter signals generated before this date
        
        Returns:
            PerformanceMetrics with aggregated stats
        """
        # Get signals to analyze
        if signals is None:
            signals = self.store.get_evaluated_signals()
        
        # Filter by date range
        if start_date or end_date:
            filtered = []
            for s in signals:
                if start_date and s.generated_at < start_date:
                    continue
                if end_date and s.generated_at > end_date:
                    continue
                filtered.append(s)
            signals = filtered
        
        # Only analyze evaluated signals
        evaluated = [s for s in signals if s.status == SignalStatus.EVALUATED]
        
        if not evaluated:
            return PerformanceMetrics(
                total_signals=0,
                hit_rate_1d=None,
                hit_rate_5d=None,
                hit_rate_20d=None,
                avg_return_1d=None,
                avg_return_5d=None,
                avg_return_20d=None,
                calibration_error=None,
                by_direction={},
                by_regime={},
                by_probability_bucket={},
                evaluation_period={
                    "start": start_date.isoformat() if start_date else None,
                    "end": end_date.isoformat() if end_date else None
                }
            )
        
        # Calculate overall metrics
        hit_rate_1d = self._calculate_hit_rate(evaluated, "hit_1d")
        hit_rate_5d = self._calculate_hit_rate(evaluated, "hit_5d")
        hit_rate_20d = self._calculate_hit_rate(evaluated, "hit_20d")
        
        avg_return_1d = self._calculate_avg_return(evaluated, "return_1d")
        avg_return_5d = self._calculate_avg_return(evaluated, "return_5d")
        avg_return_20d = self._calculate_avg_return(evaluated, "return_20d")
        
        # Calculate metrics by direction
        by_direction = self._compute_metrics_by_group(evaluated, "bias_direction")
        
        # Calculate metrics by regime
        by_regime = self._compute_metrics_by_group(evaluated, "regime")
        
        # Calculate calibration by probability bucket
        by_probability_bucket = self._compute_calibration_by_bucket(evaluated)
        
        # Calculate overall calibration error
        calibration_error = self._compute_calibration_error(evaluated)
        
        # Determine evaluation period
        dates = [s.generated_at for s in evaluated]
        period_start = min(dates) if dates else None
        period_end = max(dates) if dates else None
        
        return PerformanceMetrics(
            total_signals=len(evaluated),
            hit_rate_1d=hit_rate_1d,
            hit_rate_5d=hit_rate_5d,
            hit_rate_20d=hit_rate_20d,
            avg_return_1d=avg_return_1d,
            avg_return_5d=avg_return_5d,
            avg_return_20d=avg_return_20d,
            calibration_error=calibration_error,
            by_direction=by_direction,
            by_regime=by_regime,
            by_probability_bucket=by_probability_bucket,
            evaluation_period={
                "start": period_start.isoformat() if period_start else None,
                "end": period_end.isoformat() if period_end else None
            }
        )
    
    def _calculate_hit_rate(
        self,
        signals: List[TrackedSignal],
        hit_field: str
    ) -> Optional[float]:
        """Calculate hit rate for a specific horizon."""
        hits = [getattr(s, hit_field) for s in signals if getattr(s, hit_field) is not None]
        if not hits:
            return None
        return sum(1 for h in hits if h) / len(hits)
    
    def _calculate_avg_return(
        self,
        signals: List[TrackedSignal],
        return_field: str
    ) -> Optional[float]:
        """Calculate average return for a specific horizon."""
        returns = [getattr(s, return_field) for s in signals if getattr(s, return_field) is not None]
        if not returns:
            return None
        return statistics.mean(returns)
    
    def _compute_metrics_by_group(
        self,
        signals: List[TrackedSignal],
        group_field: str
    ) -> Dict[str, Dict[str, Any]]:
        """Compute metrics grouped by a field (direction or regime)."""
        groups = defaultdict(list)
        for s in signals:
            key = getattr(s, group_field)
            groups[key].append(s)
        
        result = {}
        for key, group_signals in groups.items():
            result[key] = {
                "count": len(group_signals),
                "hit_rate_1d": self._calculate_hit_rate(group_signals, "hit_1d"),
                "hit_rate_5d": self._calculate_hit_rate(group_signals, "hit_5d"),
                "hit_rate_20d": self._calculate_hit_rate(group_signals, "hit_20d"),
                "avg_return_1d": self._calculate_avg_return(group_signals, "return_1d"),
                "avg_return_5d": self._calculate_avg_return(group_signals, "return_5d"),
                "avg_return_20d": self._calculate_avg_return(group_signals, "return_20d"),
                "avg_probability": statistics.mean([s.bias_probability for s in group_signals])
            }
            
            # Round values
            for k, v in result[key].items():
                if isinstance(v, float):
                    result[key][k] = round(v, 4)
        
        return result
    
    def _compute_calibration_by_bucket(
        self,
        signals: List[TrackedSignal]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compute calibration metrics by probability bucket.
        
        Calibration measures how well predicted probabilities match
        actual hit rates. A well-calibrated system should have:
        - 60% predicted probability → ~60% actual hit rate
        """
        buckets = defaultdict(list)
        
        for s in signals:
            prob = s.bias_probability
            for low, high, name in self.PROBABILITY_BUCKETS:
                if low <= prob < high or (high == 100 and prob == 100):
                    buckets[name].append(s)
                    break
        
        result = {}
        for name, bucket_signals in buckets.items():
            if not bucket_signals:
                continue
            
            avg_prob = statistics.mean([s.bias_probability for s in bucket_signals])
            hit_rate_5d = self._calculate_hit_rate(bucket_signals, "hit_5d")
            
            # Calibration error for this bucket
            calibration_err = None
            if hit_rate_5d is not None:
                # Compare predicted probability to actual hit rate
                # For directional signals, probability should approximate hit rate
                calibration_err = abs(avg_prob / 100 - hit_rate_5d)
            
            result[name] = {
                "count": len(bucket_signals),
                "avg_probability": round(avg_prob, 2),
                "actual_hit_rate_5d": round(hit_rate_5d, 4) if hit_rate_5d is not None else None,
                "calibration_error": round(calibration_err, 4) if calibration_err is not None else None
            }
        
        return result
    
    def _compute_calibration_error(
        self,
        signals: List[TrackedSignal]
    ) -> Optional[float]:
        """
        Compute overall calibration error.
        
        Uses mean absolute error between predicted probability
        and actual hit rate across probability buckets.
        """
        bucket_metrics = self._compute_calibration_by_bucket(signals)
        
        errors = []
        for bucket_data in bucket_metrics.values():
            if bucket_data.get("calibration_error") is not None:
                # Weight by count
                errors.extend([bucket_data["calibration_error"]] * bucket_data["count"])
        
        if not errors:
            return None
        
        return statistics.mean(errors)
    
    def get_symbol_performance(self, symbol: str) -> Dict[str, Any]:
        """Get performance metrics for a specific symbol."""
        signals = self.store.get_signals_by_symbol(symbol)
        evaluated = [s for s in signals if s.status == SignalStatus.EVALUATED]
        
        if not evaluated:
            return {
                "symbol": symbol,
                "total_signals": 0,
                "message": "No evaluated signals for this symbol"
            }
        
        metrics = self.compute_metrics(evaluated)
        return {
            "symbol": symbol,
            **metrics.to_dict()
        }
    
    def get_recent_performance(self, days: int = 30) -> PerformanceMetrics:
        """Get performance metrics for the last N days."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        return self.compute_metrics(start_date=start_date, end_date=end_date)


# Singleton instance
_evaluator_instance: Optional[PerformanceEvaluator] = None


def get_performance_evaluator() -> PerformanceEvaluator:
    """Get singleton performance evaluator instance."""
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = PerformanceEvaluator()
    return _evaluator_instance
