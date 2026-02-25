"""
Universe Pipeline — Liquidity-first symbol selection for NGX Quality Scanner.

Selects Top N symbols by liquidity proxy:
  liquidity_score = avg_daily_value / max(avg_daily_value)  [0-1 normalized]
  avg_daily_value = mean(volume * close) over trailing window

Exclusion rules:
  - Symbols with > max_zero_pct zero-volume days are excluded
  - Symbols with < min_sessions trading days are excluded

Usage:
  from app.scanner.universe import UniverseBuilder
  builder = UniverseBuilder(session)
  members = await builder.build("top_liquid_50", as_of=date.today(), top_n=50)
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Any

from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OHLCVPrice, UniverseMember

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_LOOKBACK_DAYS = 120    # ~6 months of trading days
DEFAULT_TOP_N = 50
DEFAULT_MIN_SESSIONS = 30      # must have at least 30 trading days in window
DEFAULT_MAX_ZERO_PCT = 0.40    # exclude if >40% of days are zero-volume

# Indices and non-tradable symbols to exclude from universe
EXCLUDED_SYMBOLS = {"ASI", "NGXASI", "NGX-ASI", "NGX30", "NGXBNK", "NGXINS", "NGXOILGAS"}


@dataclass
class LiquidityResult:
    """Per-symbol liquidity metrics."""
    symbol: str
    avg_daily_value: float         # mean(volume * close) in NGN
    total_sessions: int
    zero_volume_days: int
    zero_volume_pct: float
    liquidity_score: float = 0.0   # normalized 0-1
    rank: int = 0
    excluded: bool = False
    exclude_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "avg_daily_value": round(self.avg_daily_value, 2),
            "total_sessions": self.total_sessions,
            "zero_volume_days": self.zero_volume_days,
            "zero_volume_pct": round(self.zero_volume_pct, 4),
            "liquidity_score": round(self.liquidity_score, 6),
            "rank": self.rank,
            "excluded": self.excluded,
            "exclude_reason": self.exclude_reason,
        }


@dataclass
class UniverseSnapshot:
    """Result of a universe build."""
    universe_name: str
    as_of_date: date
    top_n: int
    lookback_days: int
    members: List[LiquidityResult] = field(default_factory=list)
    excluded: List[LiquidityResult] = field(default_factory=list)
    total_symbols_evaluated: int = 0


def compute_liquidity(
    rows: List[Dict[str, Any]],
    min_sessions: int = DEFAULT_MIN_SESSIONS,
    max_zero_pct: float = DEFAULT_MAX_ZERO_PCT,
    top_n: int = DEFAULT_TOP_N,
) -> List[LiquidityResult]:
    """
    Pure computation: rank symbols by liquidity from pre-fetched OHLCV aggregates.

    Args:
        rows: list of dicts with keys: symbol, avg_daily_value, total_sessions,
              zero_volume_days
        min_sessions: minimum required sessions
        max_zero_pct: max fraction of zero-volume days before exclusion
        top_n: how many to include

    Returns:
        All LiquidityResult objects (included + excluded), sorted by rank.
        Excluded items have rank=0 and excluded=True.
    """
    results: List[LiquidityResult] = []

    for r in rows:
        symbol = r["symbol"]
        total = r["total_sessions"]
        zero_days = r["zero_volume_days"]
        adv = r["avg_daily_value"]
        zero_pct = zero_days / total if total > 0 else 1.0

        lr = LiquidityResult(
            symbol=symbol,
            avg_daily_value=adv,
            total_sessions=total,
            zero_volume_days=zero_days,
            zero_volume_pct=zero_pct,
        )

        if symbol in EXCLUDED_SYMBOLS:
            lr.excluded = True
            lr.exclude_reason = "index_or_non_tradable"
        elif total < min_sessions:
            lr.excluded = True
            lr.exclude_reason = f"insufficient_sessions ({total} < {min_sessions})"
        elif zero_pct > max_zero_pct:
            lr.excluded = True
            lr.exclude_reason = f"chronic_illiquid (zero_vol_pct={zero_pct:.1%} > {max_zero_pct:.0%})"

        results.append(lr)

    # Sort eligible by avg_daily_value descending
    eligible = [r for r in results if not r.excluded]
    eligible.sort(key=lambda x: x.avg_daily_value, reverse=True)

    # Normalize liquidity_score to [0, 1]
    if eligible:
        max_adv = eligible[0].avg_daily_value if eligible[0].avg_daily_value > 0 else 1.0
        for i, lr in enumerate(eligible):
            lr.liquidity_score = lr.avg_daily_value / max_adv
            lr.rank = i + 1

    # Truncate to top_n
    selected = eligible[:top_n]
    excluded_from_topn = eligible[top_n:]
    for lr in excluded_from_topn:
        lr.excluded = True
        lr.exclude_reason = f"outside_top_{top_n} (rank={lr.rank})"

    # Return all results
    all_results = selected + excluded_from_topn + [r for r in results if r.excluded and r.exclude_reason and "outside" not in r.exclude_reason]
    return all_results


class UniverseBuilder:
    """Builds a liquid universe from OHLCV data in the database."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _fetch_liquidity_aggregates(
        self, as_of: date, lookback_days: int
    ) -> List[Dict[str, Any]]:
        """Query OHLCV for per-symbol liquidity metrics."""
        start_date = as_of - timedelta(days=lookback_days)

        stmt = (
            select(
                OHLCVPrice.symbol,
                func.avg(OHLCVPrice.volume * OHLCVPrice.close).label("avg_daily_value"),
                func.count().label("total_sessions"),
                func.sum(
                    case(
                        (OHLCVPrice.volume == 0, 1),
                        else_=0,
                    )
                ).label("zero_volume_days"),
            )
            .where(
                and_(
                    OHLCVPrice.ts >= start_date,
                    OHLCVPrice.ts <= as_of,
                )
            )
            .group_by(OHLCVPrice.symbol)
        )

        result = await self.session.execute(stmt)
        return [
            {
                "symbol": row.symbol,
                "avg_daily_value": float(row.avg_daily_value or 0),
                "total_sessions": int(row.total_sessions),
                "zero_volume_days": int(row.zero_volume_days or 0),
            }
            for row in result.all()
        ]

    async def build(
        self,
        universe_name: str = "top_liquid_50",
        as_of: Optional[date] = None,
        top_n: int = DEFAULT_TOP_N,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        min_sessions: int = DEFAULT_MIN_SESSIONS,
        max_zero_pct: float = DEFAULT_MAX_ZERO_PCT,
        persist: bool = True,
    ) -> UniverseSnapshot:
        """
        Build a universe snapshot: fetch OHLCV aggregates, rank, persist.

        Args:
            universe_name: identifier for the universe (e.g. "top_liquid_50")
            as_of: date to evaluate (default: today)
            top_n: max members
            lookback_days: window for liquidity calculation
            min_sessions: minimum trading days required
            max_zero_pct: max zero-volume day fraction
            persist: if True, write to universe_members table

        Returns:
            UniverseSnapshot with ranked members and excluded list.
        """
        if as_of is None:
            as_of = date.today()

        rows = await self._fetch_liquidity_aggregates(as_of, lookback_days)
        all_results = compute_liquidity(rows, min_sessions, max_zero_pct, top_n)

        members = [r for r in all_results if not r.excluded]
        excluded = [r for r in all_results if r.excluded]

        snapshot = UniverseSnapshot(
            universe_name=universe_name,
            as_of_date=as_of,
            top_n=top_n,
            lookback_days=lookback_days,
            members=members,
            excluded=excluded,
            total_symbols_evaluated=len(rows),
        )

        if persist and members:
            await self._persist(snapshot)

        logger.info(
            "Universe '%s' as_of=%s: %d members from %d evaluated (%d excluded)",
            universe_name, as_of, len(members), len(rows), len(excluded),
        )

        return snapshot

    async def _persist(self, snapshot: UniverseSnapshot) -> None:
        """Write universe members to the database (upsert-style: delete old + insert)."""
        from sqlalchemy import delete

        # Remove previous snapshot for same universe+date
        await self.session.execute(
            delete(UniverseMember).where(
                and_(
                    UniverseMember.universe_name == snapshot.universe_name,
                    UniverseMember.as_of_date == snapshot.as_of_date,
                )
            )
        )

        for m in snapshot.members:
            self.session.add(UniverseMember(
                symbol=m.symbol,
                universe_name=snapshot.universe_name,
                as_of_date=snapshot.as_of_date,
                rank=m.rank,
                liquidity_score=m.liquidity_score,
                avg_daily_value=m.avg_daily_value,
                zero_volume_days=m.zero_volume_days,
                provenance={
                    "lookback_days": snapshot.lookback_days,
                    "total_evaluated": snapshot.total_symbols_evaluated,
                    "zero_volume_pct": m.zero_volume_pct,
                },
            ))

        await self.session.commit()
        logger.info("Persisted %d universe members for '%s' as_of=%s",
                     len(snapshot.members), snapshot.universe_name, snapshot.as_of_date)
