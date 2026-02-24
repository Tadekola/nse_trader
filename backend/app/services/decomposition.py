"""
Portfolio Return Decomposition Engine (Milestone C — PR1).

Decomposes portfolio returns into components:
  - equity_component: local NGN equity/TRI return
  - fx_component: currency effect (NGN→USD)
  - inflation_component: purchasing power effect (nominal→real)

Math convention (MULTIPLICATIVE, exact — no approximation):

  USD decomposition:
    (1 + r_usd) = (1 + r_equity_ngn) * (1 + r_fx)
    where r_fx = (fx[t-1] / fx[t]) - 1   (fx = USDNGN = NGN per 1 USD)

    Per-day additive decomposition (exact):
      equity_component = r_equity_ngn
      fx_component     = r_usd - r_equity_ngn
                       = (1 + r_equity_ngn) * r_fx
      total_return     = equity_component + fx_component  [exact]

  REAL_NGN decomposition:
    (1 + r_real) = (1 + r_nominal) / (1 + r_inflation)
    where r_inflation = (cpi[t] / cpi[t-1]) - 1

    Per-day additive decomposition (exact):
      equity_component      = r_nominal
      inflation_component   = r_real - r_nominal
      total_return          = equity_component + inflation_component  [exact]

  NGN decomposition:
    equity_component = r_nominal
    fx_component = 0, inflation_component = 0
    total_return = equity_component

  Cumulative summary:
    equity_cumulative = chain-link equity_component series
    total_cumulative  = chain-link total_return series
    fx_cumulative     = total_cumulative - equity_cumulative  [residual, exact]
    inflation_cumulative = total_cumulative - equity_cumulative  [residual, exact]

    The residual method ensures exact additivity in the summary and absorbs
    the interaction term, which is economically correct (interaction IS part
    of the FX/inflation effect on your equity gains).

Design: Pure computation. No DB access. Callers pass daily values + FX/CPI.

Usage::

    engine = DecompositionEngine()
    result = engine.compute(
        daily_ngn_values=[...],
        dates=[...],
        reporting="USD",
        fx_service=fx_svc,
    )
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DecompositionQuality:
    """Quality flags for decomposition — mirrors PerformanceEngine flags."""
    data_mode: str = "PRICE_ONLY"
    fx_mode: str = "FX_NOT_REQUESTED"
    inflation_mode: str = "CPI_NOT_REQUESTED"

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
class DecompositionSummary:
    """Cumulative return decomposition."""
    total_cumulative: float = 0.0
    equity_cumulative: float = 0.0
    fx_cumulative: float = 0.0
    inflation_cumulative: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cumulative": round(self.total_cumulative, 8),
            "equity_cumulative": round(self.equity_cumulative, 8),
            "fx_cumulative": round(self.fx_cumulative, 8),
            "inflation_cumulative": round(self.inflation_cumulative, 8),
        }


@dataclass
class DecompositionResult:
    """Full decomposition result."""
    portfolio_id: int
    start: date
    end: date
    reporting: str
    quality: DecompositionQuality
    series: List[Dict[str, Any]] = field(default_factory=list)
    summary: DecompositionSummary = field(default_factory=DecompositionSummary)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "reporting": self.reporting,
            "quality": self.quality.to_dict(),
            "series": self.series,
            "summary": self.summary.to_dict(),
            "provenance": self.provenance,
        }


class DecompositionEngine:
    """
    Pure computation engine for return decomposition.
    Stateless — all data passed in.
    """

    def compute(
        self,
        portfolio_id: int,
        dates: List[date],
        ngn_values: List[float],
        reporting: str = "NGN",
        fx_service=None,
        cpi_service=None,
        fx_pair: str = "USDNGN",
        cpi_base_date: Optional[date] = None,
        data_quality: str = "FULL",
    ) -> DecompositionResult:
        """
        Compute return decomposition.

        Args:
            portfolio_id: Portfolio identifier
            dates: sorted daily dates
            ngn_values: daily portfolio value in NGN (aligned with dates)
            reporting: "NGN", "USD", or "REAL_NGN"
            fx_service: FxRateService (required for USD)
            cpi_service: CpiService (required for REAL_NGN)
            fx_pair: FX pair for conversion
            cpi_base_date: base date for CPI deflation
            data_quality: "FULL" or "PARTIAL" from daily values
        """
        reporting = reporting.upper()
        quality = DecompositionQuality()
        quality.data_mode = "TRI_FULL" if data_quality == "FULL" else "PRICE_ONLY"

        if len(dates) < 2 or len(ngn_values) < 2:
            return DecompositionResult(
                portfolio_id=portfolio_id,
                start=dates[0] if dates else date.today(),
                end=dates[-1] if dates else date.today(),
                reporting=reporting,
                quality=quality,
                provenance={"note": "Insufficient data for decomposition (need ≥2 days)"},
            )

        if reporting == "USD":
            return self._decompose_usd(
                portfolio_id, dates, ngn_values, quality,
                fx_service, fx_pair,
            )
        elif reporting == "REAL_NGN":
            return self._decompose_real_ngn(
                portfolio_id, dates, ngn_values, quality,
                cpi_service, cpi_base_date,
            )
        else:
            return self._decompose_ngn(
                portfolio_id, dates, ngn_values, quality,
            )

    # ── NGN decomposition (trivial) ──────────────────────────────────

    def _decompose_ngn(
        self,
        portfolio_id: int,
        dates: List[date],
        ngn_values: List[float],
        quality: DecompositionQuality,
    ) -> DecompositionResult:

        series = []
        equity_chain = 1.0
        total_chain = 1.0

        for i in range(len(dates)):
            if i == 0:
                series.append({
                    "date": dates[i].isoformat(),
                    "total_return": None,
                    "equity_component": None,
                    "fx_component": 0.0,
                    "inflation_component": 0.0,
                })
                continue

            r_equity = (ngn_values[i] / ngn_values[i - 1]) - 1.0 if ngn_values[i - 1] > 0 else 0.0
            equity_chain *= (1.0 + r_equity)
            total_chain *= (1.0 + r_equity)

            series.append({
                "date": dates[i].isoformat(),
                "total_return": round(r_equity, 10),
                "equity_component": round(r_equity, 10),
                "fx_component": 0.0,
                "inflation_component": 0.0,
            })

        equity_cum = equity_chain - 1.0
        total_cum = total_chain - 1.0

        return DecompositionResult(
            portfolio_id=portfolio_id,
            start=dates[0],
            end=dates[-1],
            reporting="NGN",
            quality=quality,
            series=series,
            summary=DecompositionSummary(
                total_cumulative=total_cum,
                equity_cumulative=equity_cum,
                fx_cumulative=0.0,
                inflation_cumulative=0.0,
            ),
            provenance={
                "method": "ngn_nominal",
                "convention": "equity_component = r_nominal; fx/inflation = 0",
                "num_days": len(dates),
            },
        )

    # ── USD decomposition ────────────────────────────────────────────

    def _decompose_usd(
        self,
        portfolio_id: int,
        dates: List[date],
        ngn_values: List[float],
        quality: DecompositionQuality,
        fx_service,
        fx_pair: str,
    ) -> DecompositionResult:

        if fx_service is None:
            quality.fx_mode = "FX_MISSING"
            return self._decompose_ngn_with_missing(
                portfolio_id, dates, ngn_values, quality, "USD",
                missing="fx",
            )

        # Get FX rates for all dates
        fx_rates = []
        missing_fx = 0
        for d in dates:
            rate = fx_service.get_rate(fx_pair, d)
            if rate is None:
                missing_fx += 1
            fx_rates.append(rate)

        if missing_fx == len(dates):
            quality.fx_mode = "FX_MISSING"
            return self._decompose_ngn_with_missing(
                portfolio_id, dates, ngn_values, quality, "USD",
                missing="fx",
            )

        # Forward-fill None rates
        fx_rates = self._forward_fill(fx_rates)

        quality.fx_mode = "FX_FULL" if missing_fx == 0 else "FX_MISSING"

        series = []
        equity_chain = 1.0
        total_chain = 1.0

        for i in range(len(dates)):
            if i == 0:
                series.append({
                    "date": dates[i].isoformat(),
                    "total_return": None,
                    "equity_component": None,
                    "fx_component": None,
                    "inflation_component": 0.0,
                })
                continue

            # Equity return in NGN
            r_equity = (ngn_values[i] / ngn_values[i - 1]) - 1.0 if ngn_values[i - 1] > 0 else 0.0

            # FX return: r_fx = (fx[t-1] / fx[t]) - 1
            # If Naira weakens (fx goes up), r_fx < 0 (bad for USD holder)
            fx_prev = fx_rates[i - 1]
            fx_curr = fx_rates[i]

            if fx_prev and fx_curr and fx_curr > 0:
                r_fx = (fx_prev / fx_curr) - 1.0
            else:
                r_fx = 0.0

            # Total USD return: (1 + r_usd) = (1 + r_equity) * (1 + r_fx)
            r_usd = (1.0 + r_equity) * (1.0 + r_fx) - 1.0

            # Additive decomposition (exact):
            # equity_component = r_equity
            # fx_component = r_usd - r_equity = (1 + r_equity) * r_fx
            equity_component = r_equity
            fx_component = r_usd - r_equity

            equity_chain *= (1.0 + equity_component)
            total_chain *= (1.0 + r_usd)

            series.append({
                "date": dates[i].isoformat(),
                "total_return": round(r_usd, 10),
                "equity_component": round(equity_component, 10),
                "fx_component": round(fx_component, 10),
                "inflation_component": 0.0,
            })

        equity_cum = equity_chain - 1.0
        total_cum = total_chain - 1.0
        # Residual method: fx absorbs interaction term
        fx_cum = total_cum - equity_cum

        return DecompositionResult(
            portfolio_id=portfolio_id,
            start=dates[0],
            end=dates[-1],
            reporting="USD",
            quality=quality,
            series=series,
            summary=DecompositionSummary(
                total_cumulative=total_cum,
                equity_cumulative=equity_cum,
                fx_cumulative=fx_cum,
                inflation_cumulative=0.0,
            ),
            provenance={
                "method": "multiplicative_usd",
                "convention": (
                    "(1+r_usd) = (1+r_equity_ngn)*(1+r_fx); "
                    "equity_component = r_equity_ngn; "
                    "fx_component = r_usd - r_equity_ngn = (1+r_equity)*r_fx; "
                    "cumulative: fx_cumulative = total - equity (residual, exact)"
                ),
                "fx_pair": fx_pair,
                "num_days": len(dates),
            },
        )

    # ── REAL_NGN decomposition ───────────────────────────────────────

    def _decompose_real_ngn(
        self,
        portfolio_id: int,
        dates: List[date],
        ngn_values: List[float],
        quality: DecompositionQuality,
        cpi_service,
        cpi_base_date: Optional[date],
    ) -> DecompositionResult:

        if cpi_service is None:
            quality.inflation_mode = "CPI_MISSING"
            return self._decompose_ngn_with_missing(
                portfolio_id, dates, ngn_values, quality, "REAL_NGN",
                missing="cpi",
            )

        # Get CPI values for all dates
        cpi_values = []
        missing_cpi = 0
        for d in dates:
            val = cpi_service.get_value(d)
            if val is None:
                missing_cpi += 1
            cpi_values.append(val)

        if missing_cpi == len(dates):
            quality.inflation_mode = "CPI_MISSING"
            return self._decompose_ngn_with_missing(
                portfolio_id, dates, ngn_values, quality, "REAL_NGN",
                missing="cpi",
            )

        # Forward-fill None CPI values
        cpi_values = self._forward_fill(cpi_values)

        quality.inflation_mode = "CPI_FULL" if missing_cpi == 0 else "CPI_MISSING"

        series = []
        equity_chain = 1.0
        total_chain = 1.0

        for i in range(len(dates)):
            if i == 0:
                series.append({
                    "date": dates[i].isoformat(),
                    "total_return": None,
                    "equity_component": None,
                    "fx_component": 0.0,
                    "inflation_component": None,
                })
                continue

            # Nominal equity return
            r_nominal = (ngn_values[i] / ngn_values[i - 1]) - 1.0 if ngn_values[i - 1] > 0 else 0.0

            # Inflation rate: r_inflation = (cpi[t] / cpi[t-1]) - 1
            cpi_prev = cpi_values[i - 1]
            cpi_curr = cpi_values[i]

            if cpi_prev and cpi_curr and cpi_prev > 0:
                r_inflation = (cpi_curr / cpi_prev) - 1.0
            else:
                r_inflation = 0.0

            # Real return: (1 + r_real) = (1 + r_nominal) / (1 + r_inflation)
            if (1.0 + r_inflation) != 0:
                r_real = (1.0 + r_nominal) / (1.0 + r_inflation) - 1.0
            else:
                r_real = r_nominal

            # Additive decomposition (exact):
            # equity_component = r_nominal
            # inflation_component = r_real - r_nominal
            equity_component = r_nominal
            inflation_component = r_real - r_nominal

            equity_chain *= (1.0 + equity_component)
            total_chain *= (1.0 + r_real)

            series.append({
                "date": dates[i].isoformat(),
                "total_return": round(r_real, 10),
                "equity_component": round(equity_component, 10),
                "fx_component": 0.0,
                "inflation_component": round(inflation_component, 10),
            })

        equity_cum = equity_chain - 1.0
        total_cum = total_chain - 1.0
        # Residual method
        inflation_cum = total_cum - equity_cum

        return DecompositionResult(
            portfolio_id=portfolio_id,
            start=dates[0],
            end=dates[-1],
            reporting="REAL_NGN",
            quality=quality,
            series=series,
            summary=DecompositionSummary(
                total_cumulative=total_cum,
                equity_cumulative=equity_cum,
                fx_cumulative=0.0,
                inflation_cumulative=inflation_cum,
            ),
            provenance={
                "method": "multiplicative_real_ngn",
                "convention": (
                    "(1+r_real) = (1+r_nominal)/(1+r_inflation); "
                    "equity_component = r_nominal; "
                    "inflation_component = r_real - r_nominal; "
                    "cumulative: inflation_cumulative = total - equity (residual, exact)"
                ),
                "num_days": len(dates),
            },
        )

    # ── Degraded fallback ────────────────────────────────────────────

    def _decompose_ngn_with_missing(
        self,
        portfolio_id: int,
        dates: List[date],
        ngn_values: List[float],
        quality: DecompositionQuality,
        reporting: str,
        missing: str,
    ) -> DecompositionResult:
        """Fallback: return NGN-only decomposition with explicit DEGRADED flags."""
        ngn_result = self._decompose_ngn(portfolio_id, dates, ngn_values, quality)
        ngn_result.reporting = reporting

        # Mark missing components as None in series
        for entry in ngn_result.series:
            if missing == "fx":
                entry["fx_component"] = None
            elif missing == "cpi":
                entry["inflation_component"] = None

        ngn_result.provenance["degraded"] = True
        ngn_result.provenance["missing"] = missing
        ngn_result.provenance["note"] = (
            f"Decomposition DEGRADED: {missing.upper()} data unavailable. "
            f"Equity component is nominal NGN only."
        )
        return ngn_result

    # ── Utility ──────────────────────────────────────────────────────

    @staticmethod
    def _forward_fill(values: list) -> list:
        """Replace None with last known value."""
        result = []
        last = None
        for v in values:
            if v is not None:
                last = v
            result.append(last)
        return result
