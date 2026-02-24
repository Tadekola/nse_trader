"""
Portfolio Summary Service (Milestone D — PR1).

Aggregates all portfolio dimensions into a single dashboard-ready response:
  - Current valuation (reporting currency + NGN always)
  - Return windows: YTD, 1Y, 3Y, since inception
  - Current drawdown from peak
  - Top holdings: symbol, shares, market_value, weight, tri_quality
  - Concentration: HHI + max position weight
  - Data freshness: last_price_date, last_fx_date, last_cpi_date
  - Quality flags + provenance

Design: Pure computation. Callers pass in pre-fetched data.
Re-uses PerformanceEngine for return calculations — no duplicate logic.

Usage::

    service = SummaryService()
    result = service.compute(
        portfolio_id=1, as_of=date.today(), reporting="USD",
        transactions=[...], price_series={...}, latest_prices={...},
        fx_service=fx_svc, cpi_service=cpi_svc,
        tri_quality_map={"DANGCEM": "FULL", ...},
        freshness={...},
    )
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.services.portfolio import PortfolioService
from app.services.performance import PerformanceEngine, QualityFlags

logger = logging.getLogger(__name__)


@dataclass
class HoldingDetail:
    """Single holding in the summary."""
    symbol: str
    shares: float
    market_value_ngn: float
    market_value_reporting: Optional[float]
    weight: float  # fraction of total portfolio value (0-1)
    tri_quality: str  # FULL / PRICE_ONLY / UNKNOWN
    avg_cost_ngn: float
    gain_loss_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "shares": round(self.shares, 6),
            "market_value_ngn": round(self.market_value_ngn, 2),
            "market_value_reporting": (
                round(self.market_value_reporting, 2)
                if self.market_value_reporting is not None else None
            ),
            "weight": round(self.weight, 6),
            "tri_quality": self.tri_quality,
            "avg_cost_ngn": round(self.avg_cost_ngn, 4),
            "gain_loss_pct": round(self.gain_loss_pct, 2),
        }


@dataclass
class ConcentrationMetrics:
    """Portfolio concentration metrics."""
    hhi: float  # Herfindahl-Hirschman Index (0-10000 scale)
    max_position_weight: float  # largest single-position weight (0-1)
    max_position_symbol: Optional[str]
    num_positions: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hhi": round(self.hhi, 2),
            "max_position_weight": round(self.max_position_weight, 6),
            "max_position_symbol": self.max_position_symbol,
            "num_positions": self.num_positions,
        }


@dataclass
class ReturnWindow:
    """Return over a named window."""
    label: str  # "YTD", "1Y", "3Y", "SINCE_INCEPTION"
    value: Optional[float]  # cumulative return (decimal, e.g. 0.15 = 15%)
    annualized: Optional[float]  # annualized if > 1 year
    start_date: Optional[date]
    end_date: Optional[date]
    available: bool  # False if insufficient data

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "value": round(self.value, 8) if self.value is not None else None,
            "annualized": round(self.annualized, 8) if self.annualized is not None else None,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "available": self.available,
        }


@dataclass
class DataFreshness:
    """Freshness metadata for underlying data sources."""
    last_price_date: Optional[date] = None
    last_fx_date: Optional[date] = None
    last_cpi_date: Optional[date] = None
    last_action_date: Optional[date] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "last_price_date": self.last_price_date.isoformat() if self.last_price_date else None,
            "last_fx_date": self.last_fx_date.isoformat() if self.last_fx_date else None,
            "last_cpi_date": self.last_cpi_date.isoformat() if self.last_cpi_date else None,
            "last_action_date": self.last_action_date.isoformat() if self.last_action_date else None,
        }


@dataclass
class SummaryResult:
    """Complete portfolio summary for dashboard rendering."""
    portfolio_id: int
    as_of: date
    reporting: str
    value_ngn: float
    value_reporting: Optional[float]
    cash_ngn: float
    holdings_value_ngn: float
    total_invested_ngn: float
    returns: List[ReturnWindow]
    current_drawdown: Optional[float]  # current drawdown from peak (0-1)
    top_holdings: List[HoldingDetail]
    concentration: ConcentrationMetrics
    freshness: DataFreshness
    quality: QualityFlags
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
            "as_of": self.as_of.isoformat(),
            "reporting": self.reporting,
            "value_ngn": round(self.value_ngn, 2),
            "value_reporting": (
                round(self.value_reporting, 2)
                if self.value_reporting is not None else None
            ),
            "cash_ngn": round(self.cash_ngn, 2),
            "holdings_value_ngn": round(self.holdings_value_ngn, 2),
            "total_invested_ngn": round(self.total_invested_ngn, 2),
            "returns": [r.to_dict() for r in self.returns],
            "current_drawdown": (
                round(self.current_drawdown, 6)
                if self.current_drawdown is not None else None
            ),
            "top_holdings": [h.to_dict() for h in self.top_holdings],
            "concentration": self.concentration.to_dict(),
            "freshness": self.freshness.to_dict(),
            "quality": self.quality.to_dict(),
            "provenance": self.provenance,
        }


class SummaryService:
    """
    Pure computation engine for portfolio summaries.

    Composes PortfolioService (holdings/valuation) and PerformanceEngine
    (return calculations) into a single dashboard-ready response.
    """

    def __init__(self):
        self._portfolio_svc = PortfolioService()
        self._perf_engine = PerformanceEngine()

    def compute(
        self,
        portfolio_id: int,
        as_of: date,
        reporting: str,
        transactions: List[Dict[str, Any]],
        price_series: Dict[str, Dict[date, float]],
        latest_prices: Dict[str, float],
        fx_service=None,
        cpi_service=None,
        tri_quality_map: Optional[Dict[str, str]] = None,
        freshness: Optional[DataFreshness] = None,
        top_n: int = 10,
    ) -> SummaryResult:
        """
        Compute a full portfolio summary.

        Args:
            portfolio_id: ID of the portfolio
            as_of: Date for the snapshot
            reporting: "NGN", "USD", or "REAL_NGN"
            transactions: List of transaction dicts
            price_series: symbol -> {date -> price} for daily values
            latest_prices: symbol -> latest price (for current valuation)
            fx_service: FxRateService (required for USD)
            cpi_service: CpiService (required for REAL_NGN)
            tri_quality_map: symbol -> tri_quality ("FULL"/"PRICE_ONLY")
            freshness: pre-computed freshness metadata
            top_n: number of top holdings to include (default 10)
        """
        reporting = reporting.upper()
        tri_quality_map = tri_quality_map or {}
        freshness = freshness or DataFreshness()

        # ── 1. Current holdings + valuation ──────────────────────────
        snapshot = self._portfolio_svc.compute_holdings(transactions, as_of=as_of)
        valuation = self._portfolio_svc.compute_valuation(snapshot, latest_prices)

        value_ngn = valuation.total_value_ngn
        cash_ngn = valuation.cash_ngn
        holdings_ngn = valuation.holdings_value_ngn
        total_invested = snapshot.total_invested_ngn

        # ── 2. Quality flags ─────────────────────────────────────────
        quality = QualityFlags()

        # Data quality from valuation
        if valuation.data_quality == "FULL":
            quality.data_mode = "TRI_FULL"
        else:
            quality.data_mode = "PRICE_ONLY"

        # FX/CPI quality
        if reporting == "USD":
            if fx_service is None:
                quality.fx_mode = "FX_MISSING"
            else:
                quality.fx_mode = "FX_FULL"
        elif reporting == "REAL_NGN":
            if cpi_service is None:
                quality.inflation_mode = "CPI_MISSING"
            else:
                quality.inflation_mode = "CPI_FULL"

        # ── 3. Convert to reporting currency ─────────────────────────
        value_reporting = None
        fx_rate_as_of = None

        if reporting == "USD" and fx_service is not None:
            fx_rate_as_of = fx_service.get_rate("USDNGN", as_of)
            if fx_rate_as_of and fx_rate_as_of > 0:
                value_reporting = value_ngn / fx_rate_as_of
        elif reporting == "REAL_NGN" and cpi_service is not None:
            deflator = cpi_service.get_deflator(as_of)
            if deflator and deflator > 0:
                value_reporting = value_ngn / deflator
        elif reporting == "NGN":
            value_reporting = value_ngn

        # ── 4. Top holdings ──────────────────────────────────────────
        top_holdings = self._compute_top_holdings(
            valuation, value_ngn, tri_quality_map,
            fx_rate=fx_rate_as_of if reporting == "USD" else None,
            cpi_deflator=(
                cpi_service.get_deflator(as_of)
                if reporting == "REAL_NGN" and cpi_service else None
            ),
            reporting=reporting,
            top_n=top_n,
        )

        # ── 5. Concentration ─────────────────────────────────────────
        concentration = self._compute_concentration(valuation, value_ngn)

        # ── 6. Return windows ────────────────────────────────────────
        returns = self._compute_return_windows(
            as_of=as_of,
            transactions=transactions,
            price_series=price_series,
            reporting=reporting,
            fx_service=fx_service,
            cpi_service=cpi_service,
        )

        # ── 7. Current drawdown ──────────────────────────────────────
        current_drawdown = self._compute_current_drawdown(
            as_of=as_of,
            transactions=transactions,
            price_series=price_series,
            reporting=reporting,
            fx_service=fx_service,
            cpi_service=cpi_service,
        )

        # ── 8. Provenance ────────────────────────────────────────────
        provenance = {
            "engine": "SummaryService",
            "reporting": reporting,
            "as_of": as_of.isoformat(),
            "num_positions": len(snapshot.holdings),
            "num_transactions": len(transactions),
            "quality": quality.to_dict(),
        }
        if quality.overall_quality == "DEGRADED":
            provenance["degraded"] = True
            missing = []
            if quality.fx_mode == "FX_MISSING":
                missing.append("FX")
            if quality.inflation_mode == "CPI_MISSING":
                missing.append("CPI")
            if quality.data_mode == "PRICE_ONLY":
                missing.append("TRI")
            provenance["missing"] = missing

        return SummaryResult(
            portfolio_id=portfolio_id,
            as_of=as_of,
            reporting=reporting,
            value_ngn=value_ngn,
            value_reporting=value_reporting,
            cash_ngn=cash_ngn,
            holdings_value_ngn=holdings_ngn,
            total_invested_ngn=total_invested,
            returns=returns,
            current_drawdown=current_drawdown,
            top_holdings=top_holdings,
            concentration=concentration,
            freshness=freshness,
            quality=quality,
            provenance=provenance,
        )

    # ── Internal: Top Holdings ───────────────────────────────────────

    def _compute_top_holdings(
        self,
        valuation,
        total_value_ngn: float,
        tri_quality_map: Dict[str, str],
        fx_rate: Optional[float],
        cpi_deflator: Optional[float],
        reporting: str,
        top_n: int,
    ) -> List[HoldingDetail]:
        """Build top-N holdings sorted by market value descending."""
        if total_value_ngn <= 0:
            return []

        details = []
        for pos in valuation.positions:
            mv_ngn = pos["market_value_ngn"]
            weight = mv_ngn / total_value_ngn if total_value_ngn > 0 else 0.0

            mv_reporting = None
            if reporting == "USD" and fx_rate and fx_rate > 0:
                mv_reporting = mv_ngn / fx_rate
            elif reporting == "REAL_NGN" and cpi_deflator and cpi_deflator > 0:
                mv_reporting = mv_ngn / cpi_deflator
            elif reporting == "NGN":
                mv_reporting = mv_ngn

            details.append(HoldingDetail(
                symbol=pos["symbol"],
                shares=pos["quantity"],
                market_value_ngn=mv_ngn,
                market_value_reporting=mv_reporting,
                weight=weight,
                tri_quality=tri_quality_map.get(pos["symbol"], "UNKNOWN"),
                avg_cost_ngn=pos["avg_cost_ngn"],
                gain_loss_pct=pos["gain_loss_pct"],
            ))

        # Sort by market value descending, take top_n
        details.sort(key=lambda h: h.market_value_ngn, reverse=True)
        return details[:top_n]

    # ── Internal: Concentration ──────────────────────────────────────

    @staticmethod
    def _compute_concentration(valuation, total_value_ngn: float) -> ConcentrationMetrics:
        """
        Compute Herfindahl-Hirschman Index and max position weight.

        HHI = sum of (weight_i * 100)^2 across all positions INCLUDING cash.
        Scale: 0 = perfectly diversified, 10000 = single position.
        """
        if total_value_ngn <= 0:
            return ConcentrationMetrics(
                hhi=0.0, max_position_weight=0.0,
                max_position_symbol=None, num_positions=0,
            )

        # Compute weights for holdings
        weights: List[tuple] = []  # (symbol, weight)
        for pos in valuation.positions:
            w = pos["market_value_ngn"] / total_value_ngn if total_value_ngn > 0 else 0
            weights.append((pos["symbol"], w))

        # Cash weight
        cash_w = valuation.cash_ngn / total_value_ngn if total_value_ngn > 0 else 0
        if cash_w > 0:
            weights.append(("_CASH", cash_w))

        # HHI on 100-scale weights
        hhi = sum((w * 100) ** 2 for _, w in weights)

        # Max position
        max_w = 0.0
        max_sym = None
        for sym, w in weights:
            if w > max_w and sym != "_CASH":
                max_w = w
                max_sym = sym

        return ConcentrationMetrics(
            hhi=hhi,
            max_position_weight=max_w,
            max_position_symbol=max_sym,
            num_positions=len(valuation.positions),
        )

    # ── Internal: Return Windows ─────────────────────────────────────

    def _compute_return_windows(
        self,
        as_of: date,
        transactions: List[Dict[str, Any]],
        price_series: Dict[str, Dict[date, float]],
        reporting: str,
        fx_service=None,
        cpi_service=None,
    ) -> List[ReturnWindow]:
        """Compute YTD, 1Y, 3Y, and since-inception returns."""
        if not transactions:
            return []

        inception_date = min(tx["ts"] for tx in transactions)

        windows = [
            ("YTD", date(as_of.year, 1, 1)),
            ("1Y", as_of - timedelta(days=365)),
            ("3Y", as_of - timedelta(days=365 * 3)),
            ("SINCE_INCEPTION", inception_date),
        ]

        results = []
        for label, start in windows:
            # Start must not be before inception
            effective_start = max(start, inception_date)
            if effective_start >= as_of:
                results.append(ReturnWindow(
                    label=label, value=None, annualized=None,
                    start_date=None, end_date=None, available=False,
                ))
                continue

            result = self._compute_return_for_window(
                start=effective_start, end=as_of,
                transactions=transactions,
                price_series=price_series,
                reporting=reporting,
                fx_service=fx_service,
                cpi_service=cpi_service,
            )
            results.append(result._replace_label(label) if hasattr(result, '_replace_label') else
                ReturnWindow(
                    label=label,
                    value=result.value,
                    annualized=result.annualized,
                    start_date=result.start_date,
                    end_date=result.end_date,
                    available=result.available,
                ))

        return results

    def _compute_return_for_window(
        self,
        start: date,
        end: date,
        transactions: List[Dict[str, Any]],
        price_series: Dict[str, Dict[date, float]],
        reporting: str,
        fx_service=None,
        cpi_service=None,
    ) -> ReturnWindow:
        """Compute return for a single date window using PerformanceEngine."""
        daily_values = self._portfolio_svc.compute_daily_values(
            transactions, price_series, start, end,
        )

        if len(daily_values) < 2:
            return ReturnWindow(
                label="", value=None, annualized=None,
                start_date=start, end_date=end, available=False,
            )

        # Build cash flows for the window
        cash_flows = []
        for tx in transactions:
            if tx["tx_type"] in ("CASH_IN", "CASH_OUT"):
                tx_date = tx["ts"]
                if start <= tx_date <= end:
                    sign = 1.0 if tx["tx_type"] == "CASH_IN" else -1.0
                    cash_flows.append({
                        "date": tx_date,
                        "amount": sign * abs(tx.get("amount_ngn", 0)),
                    })

        perf = self._perf_engine.compute(
            daily_values=daily_values,
            cash_flows=cash_flows,
            reporting=reporting,
            fx_service=fx_service,
            cpi_service=cpi_service,
        )

        num_days = (end - start).days
        annualized = None
        if perf.metrics.total_return is not None and num_days > 365:
            annualized = self._perf_engine._annualize_return(
                perf.metrics.total_return, num_days,
            )

        return ReturnWindow(
            label="",
            value=perf.metrics.total_return,
            annualized=annualized,
            start_date=start,
            end_date=end,
            available=perf.metrics.total_return is not None,
        )

    # ── Internal: Current Drawdown ───────────────────────────────────

    def _compute_current_drawdown(
        self,
        as_of: date,
        transactions: List[Dict[str, Any]],
        price_series: Dict[str, Dict[date, float]],
        reporting: str,
        fx_service=None,
        cpi_service=None,
    ) -> Optional[float]:
        """
        Compute current drawdown from all-time high.

        Returns fraction (0.0 = at peak, 0.25 = 25% below peak).
        """
        inception_date = min(tx["ts"] for tx in transactions) if transactions else as_of

        daily_values = self._portfolio_svc.compute_daily_values(
            transactions, price_series, inception_date, as_of,
        )

        if len(daily_values) < 2:
            return None

        # Get values in reporting currency
        dates = [dv["date"] for dv in daily_values]
        ngn_values = [dv["value_ngn"] for dv in daily_values]

        if reporting == "USD" and fx_service is not None:
            values, _ = fx_service.convert_series("USDNGN", dates, ngn_values)
            values = self._perf_engine._forward_fill_nones(values)
        elif reporting == "REAL_NGN" and cpi_service is not None:
            base = dates[0]
            values, _ = cpi_service.deflate_series(dates, ngn_values, base_date=base)
            values = self._perf_engine._forward_fill_nones(values)
        else:
            values = ngn_values

        # Find peak and current drawdown
        peak = 0.0
        for v in values:
            if v is not None and v > peak:
                peak = v

        current_value = values[-1] if values[-1] is not None else 0.0

        if peak <= 0:
            return 0.0

        drawdown = (peak - current_value) / peak
        return max(drawdown, 0.0)
