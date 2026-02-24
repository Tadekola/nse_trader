"""
Portfolio Performance Engine (Milestone B — PR3).

Computes:
  - Time-Weighted Return (TWR) — eliminates cash flow effects
  - Money-Weighted Return (MWR / XIRR) — IRR of actual cash flows
  - CAGR, annualized volatility, max drawdown
  - Multi-currency reporting: NGN nominal, USD, Real NGN

Reporting modes:
  NGN     — raw nominal NGN values and returns
  USD     — convert via FX series: value_usd = value_ngn / fx_usdngn
  REAL_NGN — deflate by CPI: value_real = value_ngn / (cpi/cpi_base)

Quality flags per response:
  data_mode:      TRI_FULL / PRICE_ONLY
  fx_mode:        FX_FULL / FX_MISSING / FX_NOT_REQUESTED
  inflation_mode: CPI_FULL / CPI_MISSING / CPI_NOT_REQUESTED
  overall_quality: FULL / DEGRADED

Design: Pure computation. Callers pass daily value series + FX/CPI services.

Usage::

    engine = PerformanceEngine()
    result = engine.compute(
        daily_values=[{date, value_ngn, ...}, ...],
        cash_flows=[{date, amount}, ...],
        fx_service=fx_svc,         # optional
        cpi_service=cpi_svc,       # optional
        reporting="USD",           # or "NGN" or "REAL_NGN"
    )
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class QualityFlags:
    """Quality flags for a performance result."""
    data_mode: str = "PRICE_ONLY"       # TRI_FULL / PRICE_ONLY
    fx_mode: str = "FX_NOT_REQUESTED"   # FX_FULL / FX_MISSING / FX_NOT_REQUESTED
    inflation_mode: str = "CPI_NOT_REQUESTED"  # CPI_FULL / CPI_MISSING / CPI_NOT_REQUESTED

    @property
    def overall_quality(self) -> str:
        if self.fx_mode == "FX_MISSING" or self.inflation_mode == "CPI_MISSING":
            return "DEGRADED"
        if self.data_mode == "PRICE_ONLY":
            return "DEGRADED"
        return "FULL"

    def to_dict(self) -> Dict[str, str]:
        return {
            "data_mode": self.data_mode,
            "fx_mode": self.fx_mode,
            "inflation_mode": self.inflation_mode,
            "overall_quality": self.overall_quality,
        }


@dataclass
class PerformanceMetrics:
    """Summary performance metrics."""
    twr: Optional[float] = None            # time-weighted return (cumulative)
    twr_annualized: Optional[float] = None
    mwr: Optional[float] = None            # money-weighted return (XIRR)
    cagr: Optional[float] = None
    volatility_daily: Optional[float] = None
    volatility_annualized: Optional[float] = None
    max_drawdown: Optional[float] = None
    max_drawdown_start: Optional[date] = None
    max_drawdown_end: Optional[date] = None
    sharpe_ratio: Optional[float] = None   # excess return / vol (risk-free = 0 for now)
    total_return: Optional[float] = None
    start_value: Optional[float] = None
    end_value: Optional[float] = None
    num_days: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, date):
                d[k] = v.isoformat()
            elif isinstance(v, float) and v is not None:
                d[k] = round(v, 8)
            else:
                d[k] = v
        return d


@dataclass
class PerformanceResult:
    """Full performance computation result."""
    reporting_mode: str  # NGN / USD / REAL_NGN
    metrics: PerformanceMetrics
    quality: QualityFlags
    series: List[Dict[str, Any]] = field(default_factory=list)  # daily values + returns
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reporting_mode": self.reporting_mode,
            "metrics": self.metrics.to_dict(),
            "quality": self.quality.to_dict(),
            "series": self.series,
            "provenance": self.provenance,
        }


class PerformanceEngine:
    """
    Pure computation engine for portfolio performance.
    Stateless — all data passed in.
    """

    def compute(
        self,
        daily_values: List[Dict[str, Any]],
        cash_flows: List[Dict[str, Any]],
        reporting: str = "NGN",
        fx_service=None,
        cpi_service=None,
        fx_pair: str = "USDNGN",
        cpi_base_date: Optional[date] = None,
    ) -> PerformanceResult:
        """
        Compute performance for a portfolio.

        Args:
            daily_values: list of {date, value_ngn, cash_ngn, holdings_ngn, data_quality}
            cash_flows: list of {date, amount} — external cash flows (CASH_IN positive, CASH_OUT negative)
            reporting: "NGN", "USD", or "REAL_NGN"
            fx_service: FxRateService instance (required for USD)
            cpi_service: CpiService instance (required for REAL_NGN)
            fx_pair: FX pair for conversion (default "USDNGN")
            cpi_base_date: base date for CPI deflation (default: start of series)
        """
        quality = QualityFlags()
        reporting = reporting.upper()

        if not daily_values:
            return PerformanceResult(
                reporting_mode=reporting,
                metrics=PerformanceMetrics(),
                quality=quality,
                provenance={"note": "No daily values provided"},
            )

        # Check data quality from daily values
        qualities = {dv.get("data_quality", "FULL") for dv in daily_values}
        if all(q == "FULL" for q in qualities):
            quality.data_mode = "TRI_FULL"
        else:
            quality.data_mode = "PRICE_ONLY"

        dates = [dv["date"] for dv in daily_values]
        ngn_values = [dv["value_ngn"] for dv in daily_values]

        # ── Convert to reporting currency ─────────────────────────────
        if reporting == "USD":
            if fx_service is None:
                quality.fx_mode = "FX_MISSING"
                values = ngn_values  # fallback to NGN
            else:
                values, quality.fx_mode = fx_service.convert_series(
                    fx_pair, dates, ngn_values
                )
                # Replace None with last known value for continuity
                values = self._forward_fill_nones(values)
        elif reporting == "REAL_NGN":
            if cpi_service is None:
                quality.inflation_mode = "CPI_MISSING"
                values = ngn_values
            else:
                base = cpi_base_date or dates[0]
                values, quality.inflation_mode = cpi_service.deflate_series(
                    dates, ngn_values, base_date=base
                )
                values = self._forward_fill_nones(values)
        else:
            # NGN nominal
            values = ngn_values

        # ── Compute metrics ───────────────────────────────────────────
        # Build daily returns
        daily_returns = self._compute_daily_returns(values)

        # TWR
        twr = self._compute_twr(daily_returns)

        # CAGR
        num_days = (dates[-1] - dates[0]).days
        cagr = self._compute_cagr(values[0], values[-1], num_days)

        # Annualized TWR
        twr_ann = self._annualize_return(twr, num_days) if twr is not None else None

        # Volatility
        vol_daily = self._compute_volatility(daily_returns)
        vol_ann = vol_daily * math.sqrt(252) if vol_daily is not None else None

        # Max drawdown
        dd, dd_start, dd_end = self._compute_max_drawdown(values, dates)

        # MWR / XIRR
        mwr = self._compute_xirr(cash_flows, values[-1], dates[0], dates[-1])

        # Sharpe (excess return / vol, risk-free = 0)
        sharpe = None
        if twr_ann is not None and vol_ann is not None and vol_ann > 0:
            sharpe = twr_ann / vol_ann

        # Total return
        total_ret = None
        if values[0] and values[0] > 0 and values[-1]:
            total_ret = (values[-1] / values[0]) - 1.0

        metrics = PerformanceMetrics(
            twr=twr,
            twr_annualized=twr_ann,
            mwr=mwr,
            cagr=cagr,
            volatility_daily=vol_daily,
            volatility_annualized=vol_ann,
            max_drawdown=dd,
            max_drawdown_start=dd_start,
            max_drawdown_end=dd_end,
            sharpe_ratio=sharpe,
            total_return=total_ret,
            start_value=values[0],
            end_value=values[-1],
            num_days=num_days,
        )

        # ── Build series ──────────────────────────────────────────────
        series = []
        for i, d in enumerate(dates):
            entry = {
                "date": d.isoformat(),
                "value": round(values[i], 4) if values[i] is not None else None,
                "value_ngn": round(ngn_values[i], 4),
            }
            if i > 0 and daily_returns[i - 1] is not None:
                entry["daily_return"] = round(daily_returns[i - 1], 8)
            else:
                entry["daily_return"] = None
            series.append(entry)

        provenance = {
            "reporting_mode": reporting,
            "num_trading_days": len(dates),
            "calendar_days": num_days,
            "quality": quality.to_dict(),
        }

        return PerformanceResult(
            reporting_mode=reporting,
            metrics=metrics,
            quality=quality,
            series=series,
            provenance=provenance,
        )

    # ── Internal computations ─────────────────────────────────────────

    @staticmethod
    def _forward_fill_nones(values: list) -> list:
        """Replace None values with last known non-None value."""
        result = []
        last = None
        for v in values:
            if v is not None:
                last = v
            result.append(last)
        return result

    @staticmethod
    def _compute_daily_returns(values: list) -> List[Optional[float]]:
        """Compute daily returns from value series."""
        returns = []
        for i in range(1, len(values)):
            if values[i] is not None and values[i - 1] is not None and values[i - 1] > 0:
                returns.append((values[i] / values[i - 1]) - 1.0)
            else:
                returns.append(None)
        return returns

    @staticmethod
    def _compute_twr(daily_returns: List[Optional[float]]) -> Optional[float]:
        """Time-Weighted Return: chain-link daily returns."""
        if not daily_returns:
            return None
        product = 1.0
        valid = 0
        for r in daily_returns:
            if r is not None:
                product *= (1.0 + r)
                valid += 1
        if valid == 0:
            return None
        return product - 1.0

    @staticmethod
    def _annualize_return(ret: float, num_days: int) -> Optional[float]:
        """Annualize a cumulative return."""
        if num_days <= 0:
            return None
        years = num_days / 365.25
        if years <= 0:
            return None
        if 1.0 + ret <= 0:
            return None
        return (1.0 + ret) ** (1.0 / years) - 1.0

    @staticmethod
    def _compute_cagr(start_val, end_val, num_days: int) -> Optional[float]:
        """Compound Annual Growth Rate."""
        if not start_val or start_val <= 0 or not end_val or num_days <= 0:
            return None
        years = num_days / 365.25
        if years <= 0:
            return None
        return (end_val / start_val) ** (1.0 / years) - 1.0

    @staticmethod
    def _compute_volatility(daily_returns: List[Optional[float]]) -> Optional[float]:
        """Daily standard deviation of returns."""
        valid = [r for r in daily_returns if r is not None]
        if len(valid) < 2:
            return None
        mean = sum(valid) / len(valid)
        var = sum((r - mean) ** 2 for r in valid) / (len(valid) - 1)
        return math.sqrt(var)

    @staticmethod
    def _compute_max_drawdown(
        values: list, dates: list,
    ) -> Tuple[Optional[float], Optional[date], Optional[date]]:
        """
        Maximum peak-to-trough drawdown.
        Returns (drawdown_fraction, peak_date, trough_date).
        """
        if len(values) < 2:
            return None, None, None

        max_dd = 0.0
        peak = values[0] if values[0] else 0
        peak_idx = 0
        dd_start = dates[0]
        dd_end = dates[0]

        for i in range(1, len(values)):
            if values[i] is None:
                continue
            if values[i] > peak:
                peak = values[i]
                peak_idx = i
            if peak > 0:
                dd = (peak - values[i]) / peak
                if dd > max_dd:
                    max_dd = dd
                    dd_start = dates[peak_idx]
                    dd_end = dates[i]

        return max_dd if max_dd > 0 else 0.0, dd_start, dd_end

    @staticmethod
    def _compute_xirr(
        cash_flows: List[Dict[str, Any]],
        end_value: float,
        start_date: date,
        end_date: date,
    ) -> Optional[float]:
        """
        Money-Weighted Return via XIRR (simplified Newton-Raphson).

        cash_flows: [{date, amount}] — positive = inflow, negative = outflow
        end_value: terminal portfolio value (treated as final outflow)
        """
        if not cash_flows or end_value is None:
            return None

        # Build cash flow list: all external flows + terminal value as outflow
        flows: List[Tuple[date, float]] = []
        for cf in cash_flows:
            flows.append((cf["date"], cf["amount"]))

        # Add terminal value as a positive outflow (as if we liquidate)
        flows.append((end_date, end_value))

        if len(flows) < 2:
            return None

        # Check that we have at least one sign change
        positives = sum(1 for _, a in flows if a > 0)
        negatives = sum(1 for _, a in flows if a < 0)
        if positives == 0 or negatives == 0:
            # No sign change needed for XIRR when we have initial investment + terminal value
            # But if all flows are same sign, XIRR is undefined
            pass

        base_date = flows[0][0]

        def npv(rate):
            """Net present value at given annual rate."""
            total = 0.0
            for d, amount in flows:
                days = (d - base_date).days
                years = days / 365.25
                if rate <= -1.0:
                    return float('inf')
                try:
                    total += amount / ((1.0 + rate) ** years)
                except (OverflowError, ZeroDivisionError):
                    return float('inf')
            return total

        def npv_deriv(rate):
            """Derivative of NPV with respect to rate."""
            total = 0.0
            for d, amount in flows:
                days = (d - base_date).days
                years = days / 365.25
                if years == 0:
                    continue
                if rate <= -1.0:
                    return float('inf')
                try:
                    total -= years * amount / ((1.0 + rate) ** (years + 1))
                except (OverflowError, ZeroDivisionError):
                    return float('inf')
            return total

        # Newton-Raphson
        guess = 0.1
        for _ in range(100):
            f = npv(guess)
            fp = npv_deriv(guess)
            if abs(fp) < 1e-12:
                break
            new_guess = guess - f / fp
            if abs(new_guess - guess) < 1e-9:
                guess = new_guess
                break
            guess = new_guess
            # Clamp to reasonable range
            if guess < -0.99:
                guess = -0.99
            elif guess > 10.0:
                guess = 10.0

        # Verify convergence
        if abs(npv(guess)) > 1.0:
            return None

        return guess
