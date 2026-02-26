"""
Nigeria Growth Potential Scorer — identifies high-growth stocks aligned
with Nigeria's economic transformation thesis.

Combines:
  1. Revenue & earnings growth rates (from FundamentalsPeriodic)
  2. Quality score (from FundamentalsDerived / scanner)
  3. Sector macro alignment (Nigeria transformation thesis)
  4. Balance sheet strength
  5. Valuation attractiveness

Pure computation + DB reads.  No side-effects.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timezone, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session_factory
from app.db.models import FundamentalsPeriodic, FundamentalsDerived
from app.data.sources.ngx_stocks import NGXStockRegistry, Sector

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Nigeria Macro Thesis — Sector Alignment Scores
# ═══════════════════════════════════════════════════════════════════════

SECTOR_MACRO_ALIGNMENT: Dict[str, float] = {
    # Financial Services: banking the unbanked, digital payments, financial
    # inclusion, insurance penetration <1%, pension reform, AfCFTA trade finance
    Sector.FINANCIAL_SERVICES.value: 0.95,

    # ICT: digital economy, fintech, e-commerce, Africa's largest tech
    # ecosystem, broadband penetration growth, data centre demand
    Sector.ICT.value: 0.90,

    # Consumer Goods: 220M+ population, rising middle class, import
    # substitution (Dangote Sugar, Nestle local sourcing), FMCG demand
    Sector.CONSUMER_GOODS.value: 0.85,

    # Agriculture: food security, agricultural value chain, backward
    # integration incentives, export potential (cocoa, sesame, cashews)
    Sector.AGRICULTURE.value: 0.82,

    # Industrial Goods: infrastructure deficit ($3T over 30yr est.),
    # cement demand (Dangote, BUA), steel, housing deficit of 28M units
    Sector.INDUSTRIAL_GOODS.value: 0.80,

    # Construction: housing deficit, infrastructure (roads, rail, ports),
    # Dangote refinery multiplier effects, Lagos-Calabar coastal highway
    Sector.CONSTRUCTION.value: 0.80,

    # Oil & Gas: Dangote refinery (650kbpd), PIA reforms, gas monetisation,
    # Nigeria LNG expansion, fuel subsidy removal → downstream margins
    Sector.OIL_AND_GAS.value: 0.75,

    # Healthcare: healthcare spending growth, pharma manufacturing,
    # medical tourism reversal, health insurance expansion
    Sector.HEALTHCARE.value: 0.70,

    # Natural Resources: solid minerals development (gold, lithium, tin),
    # mining sector still nascent but high policy focus
    Sector.NATURAL_RESOURCES.value: 0.65,

    # Services: logistics, real estate (urbanisation), tourism
    Sector.SERVICES.value: 0.60,

    # Conglomerates: diversified but often unfocused, restructuring trend
    Sector.CONGLOMERATES.value: 0.55,
}


# ═══════════════════════════════════════════════════════════════════════
# GrowthProfile dataclass
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class GrowthProfile:
    """Complete growth assessment for a single stock."""
    symbol: str

    # Growth metrics (YoY from periodic data)
    revenue_growth: Optional[float] = None      # e.g. 0.25 = 25% YoY
    earnings_growth: Optional[float] = None     # e.g. 0.40 = 40% YoY
    revenue_cagr: Optional[float] = None        # compound annual growth rate

    # Quality metrics (from FundamentalsDerived)
    quality_score: Optional[float] = None       # 0-100
    roe: Optional[float] = None
    op_margin: Optional[float] = None
    net_margin: Optional[float] = None
    debt_to_equity: Optional[float] = None
    fcf: Optional[float] = None
    earnings_stability: Optional[float] = None

    # Sector & macro
    sector: Optional[str] = None
    sector_macro_alignment: float = 0.5         # 0-1

    # Market data from registry
    market_cap_billions: Optional[float] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    eps: Optional[float] = None

    # Composite growth potential score (0-100)
    growth_potential: float = 0.0

    # Explanations
    growth_factors: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "revenue_growth": _pct(self.revenue_growth),
            "earnings_growth": _pct(self.earnings_growth),
            "revenue_cagr": _pct(self.revenue_cagr),
            "quality_score": _r(self.quality_score),
            "roe": _pct(self.roe),
            "op_margin": _pct(self.op_margin),
            "net_margin": _pct(self.net_margin),
            "debt_to_equity": _r(self.debt_to_equity),
            "fcf": _r(self.fcf),
            "earnings_stability": _r(self.earnings_stability),
            "sector": self.sector,
            "sector_macro_alignment": _r(self.sector_macro_alignment),
            "market_cap_billions": _r(self.market_cap_billions),
            "pe_ratio": _r(self.pe_ratio),
            "growth_potential": _r(self.growth_potential),
            "growth_factors": self.growth_factors,
            "risk_factors": self.risk_factors,
        }


def _r(v: Optional[float], digits: int = 4) -> Optional[float]:
    return round(v, digits) if v is not None else None


def _pct(v: Optional[float]) -> Optional[float]:
    """Round percentage values to 4 decimal places."""
    return round(v, 4) if v is not None else None


# ═══════════════════════════════════════════════════════════════════════
# Growth computation helpers
# ═══════════════════════════════════════════════════════════════════════

def compute_yoy_growth(
    periods: List[Dict[str, Any]], field_name: str
) -> Optional[float]:
    """
    Compute year-over-year growth rate from the two most recent annual periods.
    Returns fractional growth (e.g. 0.25 = 25%).
    """
    annual = [
        p for p in periods
        if p.get("period_type", "ANNUAL") == "ANNUAL"
        and p.get(field_name) is not None
    ]
    annual.sort(key=lambda p: p["period_end_date"])

    if len(annual) < 2:
        return None

    prev_val = annual[-2][field_name]
    curr_val = annual[-1][field_name]

    if prev_val is None or prev_val == 0:
        return None

    return (curr_val - prev_val) / abs(prev_val)


def compute_cagr(
    periods: List[Dict[str, Any]], field_name: str
) -> Optional[float]:
    """
    Compute CAGR across all available annual periods.
    Returns fractional rate (e.g. 0.15 = 15% CAGR).
    """
    annual = [
        p for p in periods
        if p.get("period_type", "ANNUAL") == "ANNUAL"
        and p.get(field_name) is not None
        and p[field_name] > 0
    ]
    annual.sort(key=lambda p: p["period_end_date"])

    if len(annual) < 2:
        return None

    first_val = annual[0][field_name]
    last_val = annual[-1][field_name]

    if first_val <= 0 or last_val <= 0:
        return None

    first_date = annual[0]["period_end_date"]
    last_date = annual[-1]["period_end_date"]
    if isinstance(first_date, str):
        first_date = date.fromisoformat(first_date)
    if isinstance(last_date, str):
        last_date = date.fromisoformat(last_date)

    years = (last_date - first_date).days / 365.25
    if years < 0.5:
        return None

    try:
        return (last_val / first_val) ** (1 / years) - 1
    except (ZeroDivisionError, ValueError, OverflowError):
        return None


# ═══════════════════════════════════════════════════════════════════════
# Composite growth potential scoring
# ═══════════════════════════════════════════════════════════════════════

def _score_growth_rate(rate: Optional[float], high: float = 0.30) -> float:
    """Map a growth rate to 0-1 score.  >high → 1.0, negative → low."""
    if rate is None:
        return 0.3  # neutral when unknown
    if rate <= -0.10:
        return 0.0
    if rate <= 0:
        return 0.15
    if rate >= high:
        return 1.0
    return rate / high  # linear 0→1


def _score_roe(roe: Optional[float]) -> float:
    if roe is None:
        return 0.3
    if roe >= 0.25:
        return 1.0
    if roe >= 0.15:
        return 0.8
    if roe >= 0.10:
        return 0.6
    if roe >= 0.05:
        return 0.4
    if roe > 0:
        return 0.2
    return 0.0


def _score_quality(qs: Optional[float]) -> float:
    """Map quality_score (0-100) → 0-1."""
    if qs is None:
        return 0.3
    return max(0, min(1, qs / 80))  # 80+ quality → 1.0


def _score_balance_sheet(de: Optional[float]) -> float:
    """Lower D/E is better; banks naturally have higher leverage."""
    if de is None:
        return 0.4
    if de < 0.3:
        return 1.0
    if de < 0.7:
        return 0.8
    if de < 1.5:
        return 0.6
    if de < 3.0:
        return 0.4
    return 0.2  # very high leverage


def _score_valuation(pe: Optional[float], growth: Optional[float]) -> float:
    """PEG-like score: low P/E relative to growth is attractive."""
    if pe is None or pe <= 0:
        return 0.4  # can't assess
    if growth is not None and growth > 0.05:
        peg = pe / (growth * 100)
        if peg < 0.5:
            return 1.0
        if peg < 1.0:
            return 0.85
        if peg < 1.5:
            return 0.65
        if peg < 2.0:
            return 0.45
        return 0.25
    # No growth data — use absolute P/E
    if pe < 5:
        return 0.9
    if pe < 10:
        return 0.7
    if pe < 15:
        return 0.5
    if pe < 25:
        return 0.35
    return 0.2


def compute_growth_potential(profile: GrowthProfile) -> float:
    """
    Compute composite growth potential score (0-100).

    Weights:
      Revenue growth      20%
      Earnings growth     20%
      Quality score       15%
      Sector alignment    20%
      Balance sheet       10%
      Valuation           15%
    """
    rev_score = _score_growth_rate(profile.revenue_growth)
    earn_score = _score_growth_rate(profile.earnings_growth)
    qual_score = _score_quality(profile.quality_score)
    sector_score = profile.sector_macro_alignment
    bs_score = _score_balance_sheet(profile.debt_to_equity)
    val_score = _score_valuation(profile.pe_ratio, profile.revenue_growth)

    composite = (
        rev_score * 0.20 +
        earn_score * 0.20 +
        qual_score * 0.15 +
        sector_score * 0.20 +
        bs_score * 0.10 +
        val_score * 0.15
    )

    # Build explanation
    if profile.revenue_growth is not None and profile.revenue_growth > 0.15:
        profile.growth_factors.append(
            f"Strong revenue growth ({profile.revenue_growth:.0%} YoY)"
        )
    if profile.earnings_growth is not None and profile.earnings_growth > 0.20:
        profile.growth_factors.append(
            f"Strong earnings growth ({profile.earnings_growth:.0%} YoY)"
        )
    if profile.sector_macro_alignment >= 0.80:
        profile.growth_factors.append(
            f"Sector well-aligned with Nigeria growth thesis ({profile.sector})"
        )
    if profile.quality_score is not None and profile.quality_score >= 55:
        profile.growth_factors.append(
            f"High quality business (score {profile.quality_score:.0f}/100)"
        )
    if profile.roe is not None and profile.roe >= 0.15:
        profile.growth_factors.append(
            f"Efficient capital deployment (ROE {profile.roe:.0%})"
        )

    # Risk factors
    if profile.revenue_growth is not None and profile.revenue_growth < 0:
        profile.risk_factors.append(
            f"Revenue declining ({profile.revenue_growth:.0%} YoY)"
        )
    if profile.debt_to_equity is not None and profile.debt_to_equity > 2.0:
        profile.risk_factors.append(
            f"High leverage (D/E {profile.debt_to_equity:.1f})"
        )
    if profile.earnings_stability is not None and profile.earnings_stability < 0.4:
        profile.risk_factors.append("Unstable earnings history")
    if profile.quality_score is not None and profile.quality_score < 30:
        profile.risk_factors.append(
            f"Low quality score ({profile.quality_score:.0f}/100)"
        )

    return round(composite * 100, 2)


# ═══════════════════════════════════════════════════════════════════════
# GrowthScorer — loads from DB and computes profiles
# ═══════════════════════════════════════════════════════════════════════

class GrowthScorer:
    """
    Loads fundamental data from PostgreSQL and computes growth profiles
    for use by the recommendation engine.

    Thread-safe, async.  Profiles are cached for the session.
    """

    def __init__(self):
        self._registry = NGXStockRegistry()
        self._cache: Dict[str, GrowthProfile] = {}
        self._loaded = False

    async def load_all_profiles(self) -> Dict[str, GrowthProfile]:
        """Load growth profiles for all stocks with fundamentals data."""
        if self._loaded and self._cache:
            return self._cache

        factory = get_session_factory()
        async with factory() as session:
            profiles = await self._compute_profiles(session)

        self._cache = profiles
        self._loaded = True
        logger.info("Growth profiles loaded for %d symbols", len(profiles))
        return profiles

    async def get_profile(self, symbol: str) -> Optional[GrowthProfile]:
        """Get growth profile for a single symbol."""
        if not self._loaded:
            await self.load_all_profiles()
        return self._cache.get(symbol.upper())

    def get_cached_profile(self, symbol: str) -> Optional[GrowthProfile]:
        """Get cached profile (None if not loaded yet)."""
        return self._cache.get(symbol.upper())

    def invalidate_cache(self):
        """Force reload on next access."""
        self._cache.clear()
        self._loaded = False

    async def _compute_profiles(
        self, session: AsyncSession
    ) -> Dict[str, GrowthProfile]:
        """Core computation: fetch from DB, compute growth, score."""
        profiles: Dict[str, GrowthProfile] = {}

        # Step 1: Fetch all periodic fundamentals
        periodic_result = await session.execute(
            select(FundamentalsPeriodic).order_by(
                FundamentalsPeriodic.symbol,
                FundamentalsPeriodic.period_end_date.asc(),
            )
        )
        all_periodic = periodic_result.scalars().all()

        # Group by symbol
        periodic_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        for row in all_periodic:
            sym = row.symbol.upper()
            if sym not in periodic_by_symbol:
                periodic_by_symbol[sym] = []
            periodic_by_symbol[sym].append({
                "period_end_date": row.period_end_date,
                "period_type": row.period_type or "ANNUAL",
                "revenue": row.revenue,
                "operating_profit": row.operating_profit,
                "net_income": row.net_income,
                "total_equity": row.total_equity,
                "total_debt": row.total_debt,
                "cash": row.cash,
                "operating_cash_flow": row.operating_cash_flow,
                "capex": row.capex,
            })

        # Step 2: Fetch derived metrics (quality scores)
        derived_result = await session.execute(
            select(FundamentalsDerived).order_by(
                FundamentalsDerived.as_of_date.desc()
            )
        )
        all_derived = derived_result.scalars().all()

        # Keep latest derived per symbol
        derived_by_symbol: Dict[str, FundamentalsDerived] = {}
        for row in all_derived:
            sym = row.symbol.upper()
            if sym not in derived_by_symbol:
                derived_by_symbol[sym] = row

        # Step 3: Compute profiles for each symbol in the registry
        all_symbols = set(periodic_by_symbol.keys()) | set(derived_by_symbol.keys())

        for symbol in all_symbols:
            profile = GrowthProfile(symbol=symbol)

            # Registry data
            stock_info = self._registry.get_stock(symbol)
            if stock_info:
                profile.sector = stock_info.sector.value if hasattr(stock_info, 'sector') else None
                profile.market_cap_billions = stock_info.market_cap_billions
                profile.pe_ratio = stock_info.pe_ratio
                profile.dividend_yield = stock_info.dividend_yield
                profile.eps = stock_info.eps

            # Sector macro alignment
            if profile.sector:
                profile.sector_macro_alignment = SECTOR_MACRO_ALIGNMENT.get(
                    profile.sector, 0.50
                )

            # Growth from periodic data
            periods = periodic_by_symbol.get(symbol, [])
            if periods:
                profile.revenue_growth = compute_yoy_growth(periods, "revenue")
                profile.earnings_growth = compute_yoy_growth(periods, "net_income")
                profile.revenue_cagr = compute_cagr(periods, "revenue")

            # Quality metrics from derived
            derived = derived_by_symbol.get(symbol)
            if derived:
                profile.quality_score = derived.quality_score
                profile.roe = derived.roe
                profile.op_margin = derived.op_margin
                profile.net_margin = derived.net_margin
                profile.debt_to_equity = derived.debt_to_equity
                profile.fcf = derived.fcf
                profile.earnings_stability = derived.earnings_stability

            # Composite growth potential
            profile.growth_potential = compute_growth_potential(profile)
            profiles[symbol] = profile

        # Also create profiles for registry stocks without fundamentals
        # (they get sector alignment + registry data only)
        for symbol, info in self._registry.STOCKS.items():
            if symbol not in profiles:
                profile = GrowthProfile(symbol=symbol)
                profile.sector = info.sector.value
                profile.market_cap_billions = info.market_cap_billions
                profile.pe_ratio = info.pe_ratio
                profile.dividend_yield = info.dividend_yield
                profile.eps = info.eps
                profile.sector_macro_alignment = SECTOR_MACRO_ALIGNMENT.get(
                    info.sector.value, 0.50
                )
                profile.growth_potential = compute_growth_potential(profile)
                profiles[symbol] = profile

        return profiles


# Module-level singleton
_growth_scorer: Optional[GrowthScorer] = None


def get_growth_scorer() -> GrowthScorer:
    """Get or create the singleton GrowthScorer."""
    global _growth_scorer
    if _growth_scorer is None:
        _growth_scorer = GrowthScorer()
    return _growth_scorer
