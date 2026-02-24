"""
Portfolio Timeseries Service (Milestone D — PR2).

Pre-shapes daily portfolio data for charting:
  - date, value (in reporting currency), cumulative_return, drawdown
  - Optional: rolling_vol_30d (annualized 30-day rolling volatility)

Design: Pure computation. Re-uses PortfolioService for daily values and
PerformanceEngine for currency conversion. No duplicate logic.

Usage::

    service = TimeseriesService()
    result = service.compute(
        transactions=[...], price_series={...},
        start_date=..., end_date=..., reporting="USD",
        fx_service=fx_svc, cpi_service=cpi_svc,
    )
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from app.services.portfolio import PortfolioService
from app.services.performance import PerformanceEngine, QualityFlags

logger = logging.getLogger(__name__)

ROLLING_VOL_WINDOW = 30  # trading days


@dataclass
class TimeseriesPoint:
    """Single point in the timeseries."""
    date: date
    value: Optional[float]
    value_ngn: float
    cumulative_return: Optional[float]
    drawdown: float  # 0 = at peak, positive = below peak
    rolling_vol_30d: Optional[float]  # annualized, None if insufficient data

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "value": round(self.value, 4) if self.value is not None else None,
            "value_ngn": round(self.value_ngn, 4),
            "cumulative_return": (
                round(self.cumulative_return, 8)
                if self.cumulative_return is not None else None
            ),
            "drawdown": round(self.drawdown, 6),
            "rolling_vol_30d": (
                round(self.rolling_vol_30d, 6)
                if self.rolling_vol_30d is not None else None
            ),
        }


@dataclass
class TimeseriesResult:
    """Full timeseries computation result."""
    reporting: str
    start_date: date
    end_date: date
    num_points: int
    quality: QualityFlags
    series: List[TimeseriesPoint] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reporting": self.reporting,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "num_points": self.num_points,
            "quality": self.quality.to_dict(),
            "series": [p.to_dict() for p in self.series],
            "provenance": self.provenance,
        }


class TimeseriesService:
    """
    Pure computation engine for portfolio timeseries.

    Composes PortfolioService (daily values) and PerformanceEngine
    (currency conversion helpers) into chart-ready series.
    """

    def __init__(self):
        self._portfolio_svc = PortfolioService()
        self._perf_engine = PerformanceEngine()

    def compute(
        self,
        transactions: List[Dict[str, Any]],
        price_series: Dict[str, Dict[date, float]],
        start_date: date,
        end_date: date,
        reporting: str = "NGN",
        fx_service=None,
        cpi_service=None,
    ) -> TimeseriesResult:
        """
        Compute chart-ready timeseries for a portfolio.

        Args:
            transactions: List of transaction dicts
            price_series: symbol -> {date -> price}
            start_date: Series start
            end_date: Series end
            reporting: "NGN", "USD", or "REAL_NGN"
            fx_service: FxRateService (required for USD)
            cpi_service: CpiService (required for REAL_NGN)
        """
        reporting = reporting.upper()
        quality = QualityFlags()

        # Compute daily NGN values
        daily_values = self._portfolio_svc.compute_daily_values(
            transactions, price_series, start_date, end_date,
        )

        if not daily_values:
            return TimeseriesResult(
                reporting=reporting,
                start_date=start_date,
                end_date=end_date,
                num_points=0,
                quality=quality,
                provenance={"note": "No price data in range"},
            )

        # Set data quality
        qualities = {dv.get("data_quality", "FULL") for dv in daily_values}
        if all(q == "FULL" for q in qualities):
            quality.data_mode = "TRI_FULL"
        else:
            quality.data_mode = "PRICE_ONLY"

        dates = [dv["date"] for dv in daily_values]
        ngn_values = [dv["value_ngn"] for dv in daily_values]

        # Convert to reporting currency
        if reporting == "USD":
            if fx_service is None:
                quality.fx_mode = "FX_MISSING"
                values = ngn_values
            else:
                values, quality.fx_mode = fx_service.convert_series(
                    "USDNGN", dates, ngn_values,
                )
                values = self._perf_engine._forward_fill_nones(values)
        elif reporting == "REAL_NGN":
            if cpi_service is None:
                quality.inflation_mode = "CPI_MISSING"
                values = ngn_values
            else:
                base = dates[0]
                values, quality.inflation_mode = cpi_service.deflate_series(
                    dates, ngn_values, base_date=base,
                )
                values = self._perf_engine._forward_fill_nones(values)
        else:
            values = ngn_values

        # Compute daily returns for rolling vol
        daily_returns = self._compute_daily_returns(values)

        # Build series
        base_value = values[0] if values[0] is not None and values[0] > 0 else None
        peak = 0.0
        series: List[TimeseriesPoint] = []

        for i, d in enumerate(dates):
            v = values[i]
            ngn_v = ngn_values[i]

            # Cumulative return
            cum_ret = None
            if base_value is not None and v is not None:
                cum_ret = (v / base_value) - 1.0

            # Drawdown from peak
            if v is not None and v > peak:
                peak = v
            dd = 0.0
            if peak > 0 and v is not None:
                dd = (peak - v) / peak
                dd = max(dd, 0.0)

            # Rolling volatility (30-day)
            rolling_vol = self._compute_rolling_vol(daily_returns, i, ROLLING_VOL_WINDOW)

            series.append(TimeseriesPoint(
                date=d,
                value=v,
                value_ngn=ngn_v,
                cumulative_return=cum_ret,
                drawdown=dd,
                rolling_vol_30d=rolling_vol,
            ))

        provenance = {
            "engine": "TimeseriesService",
            "reporting": reporting,
            "num_trading_days": len(dates),
            "calendar_days": (dates[-1] - dates[0]).days if len(dates) > 1 else 0,
            "quality": quality.to_dict(),
        }

        return TimeseriesResult(
            reporting=reporting,
            start_date=dates[0],
            end_date=dates[-1],
            num_points=len(series),
            quality=quality,
            series=series,
            provenance=provenance,
        )

    # ── Internal ─────────────────────────────────────────────────────

    @staticmethod
    def _compute_daily_returns(values: list) -> List[Optional[float]]:
        """Compute daily returns. Returns list with None at index 0."""
        returns: List[Optional[float]] = [None]  # no return on day 0
        for i in range(1, len(values)):
            if (values[i] is not None and values[i - 1] is not None
                    and values[i - 1] > 0):
                returns.append((values[i] / values[i - 1]) - 1.0)
            else:
                returns.append(None)
        return returns

    @staticmethod
    def _compute_rolling_vol(
        daily_returns: List[Optional[float]],
        current_idx: int,
        window: int,
    ) -> Optional[float]:
        """
        Annualized rolling volatility ending at current_idx.

        Needs at least `window` valid returns before current_idx.
        """
        if current_idx < window:
            return None

        # Gather last `window` returns ending at current_idx
        window_returns = []
        for j in range(current_idx - window + 1, current_idx + 1):
            if j >= 0 and j < len(daily_returns) and daily_returns[j] is not None:
                window_returns.append(daily_returns[j])

        if len(window_returns) < window:
            return None

        mean = sum(window_returns) / len(window_returns)
        var = sum((r - mean) ** 2 for r in window_returns) / (len(window_returns) - 1)
        daily_vol = math.sqrt(var)
        return daily_vol * math.sqrt(252)  # annualize
