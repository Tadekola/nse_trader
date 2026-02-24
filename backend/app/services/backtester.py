"""
Walk-Forward Backtest Engine for NSE Trader.

Simulates the recommendation engine at each rebalance date using only
data available up to that point (no look-ahead bias). Compares engine
picks against benchmarks to measure alpha.

Benchmarks:
- ASI (All Share Index): Market return
- Equal-weight basket: Naive diversification across all symbols

Metrics:
- Cumulative return, annualised return
- Alpha vs ASI, alpha vs equal-weight
- Sharpe ratio (risk-free rate = 10% for NGN)
- Max drawdown
- Hit rate (% of picks that beat the benchmark over holding period)
- Win/loss ratio
"""
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

from app.core.recommendation_engine import (
    RecommendationEngine,
    TimeHorizon,
    RecommendationAction,
)
from app.core.market_regime import MarketRegimeDetector

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "historical_ohlcv.db"

# Nigerian risk-free rate (approx T-bill rate)
RISK_FREE_RATE_ANNUAL = 0.10


# ── Data loading ──────────────────────────────────────────────────────


def load_all_ohlcv(db_path: Path = DB_PATH) -> Dict[str, pd.DataFrame]:
    """Load all OHLCV data from historical DB, keyed by symbol."""
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql_query(
        "SELECT symbol, date, open, high, low, close, volume FROM ohlcv ORDER BY date",
        conn,
    )
    conn.close()

    result = {}
    for symbol, group in df.groupby("symbol"):
        sdf = group.copy()
        sdf["date"] = pd.to_datetime(sdf["date"])
        sdf = sdf.set_index("date").sort_index()
        sdf.columns = ["symbol", "Open", "High", "Low", "Close", "Volume"]
        sdf = sdf.drop(columns=["symbol"])
        result[symbol] = sdf
    return result


# ── Data classes ──────────────────────────────────────────────────────


@dataclass
class PickRecord:
    """A single pick made by the engine at a rebalance date."""
    rebalance_date: date
    symbol: str
    action: str
    confidence: float
    price_at_pick: float
    price_at_exit: Optional[float] = None
    return_pct: Optional[float] = None
    benchmark_return_pct: Optional[float] = None
    beat_benchmark: Optional[bool] = None


@dataclass
class RebalanceSnapshot:
    """Engine output at a single rebalance date."""
    rebalance_date: date
    picks: List[PickRecord]
    asi_return: Optional[float] = None
    equal_weight_return: Optional[float] = None
    portfolio_return: Optional[float] = None


@dataclass
class BacktestConfig:
    """Configuration for the walk-forward backtest."""
    warmup_sessions: int = 60       # Min sessions before first rebalance
    rebalance_every: int = 5        # Rebalance every N trading days
    holding_period: int = 5         # Hold for N trading days
    top_n: int = 5                  # Pick top N stocks
    horizon: TimeHorizon = TimeHorizon.SWING
    # Actions considered as "picks" (engine recommends buying)
    pick_actions: Tuple[str, ...] = (
        RecommendationAction.STRONG_BUY.value,
        RecommendationAction.BUY.value,
    )
    # If no BUY signals, use confidence ranking instead
    fallback_to_confidence_rank: bool = True


@dataclass
class BacktestResults:
    """Complete backtest output."""
    config: BacktestConfig
    snapshots: List[RebalanceSnapshot]
    # Portfolio equity curve
    portfolio_equity: List[float] = field(default_factory=list)
    asi_equity: List[float] = field(default_factory=list)
    equal_weight_equity: List[float] = field(default_factory=list)
    # Aggregate metrics
    total_rebalances: int = 0
    total_picks: int = 0
    picks_with_buy_signal: int = 0
    picks_from_confidence_rank: int = 0
    # Returns
    portfolio_cumulative_return: float = 0.0
    asi_cumulative_return: float = 0.0
    equal_weight_cumulative_return: float = 0.0
    portfolio_annualised_return: float = 0.0
    # Alpha
    alpha_vs_asi: float = 0.0
    alpha_vs_equal_weight: float = 0.0
    # Risk
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    # Accuracy
    hit_rate_vs_asi: float = 0.0
    hit_rate_vs_equal_weight: float = 0.0
    avg_pick_return: float = 0.0
    win_loss_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to API-friendly dict."""
        return {
            "config": {
                "warmup_sessions": self.config.warmup_sessions,
                "rebalance_every": self.config.rebalance_every,
                "holding_period": self.config.holding_period,
                "top_n": self.config.top_n,
                "horizon": self.config.horizon.value,
            },
            "summary": {
                "total_rebalances": self.total_rebalances,
                "total_picks": self.total_picks,
                "picks_with_buy_signal": self.picks_with_buy_signal,
                "picks_from_confidence_rank": self.picks_from_confidence_rank,
            },
            "returns": {
                "portfolio_cumulative": round(self.portfolio_cumulative_return, 4),
                "asi_cumulative": round(self.asi_cumulative_return, 4),
                "equal_weight_cumulative": round(self.equal_weight_cumulative_return, 4),
                "portfolio_annualised": round(self.portfolio_annualised_return, 4),
            },
            "alpha": {
                "vs_asi": round(self.alpha_vs_asi, 4),
                "vs_equal_weight": round(self.alpha_vs_equal_weight, 4),
            },
            "risk": {
                "sharpe_ratio": round(self.sharpe_ratio, 4),
                "max_drawdown": round(self.max_drawdown, 4),
            },
            "accuracy": {
                "hit_rate_vs_asi": round(self.hit_rate_vs_asi, 4),
                "hit_rate_vs_equal_weight": round(self.hit_rate_vs_equal_weight, 4),
                "avg_pick_return_pct": round(self.avg_pick_return, 4),
                "win_loss_ratio": round(self.win_loss_ratio, 4),
            },
            "equity_curves": {
                "portfolio": [round(v, 4) for v in self.portfolio_equity],
                "asi": [round(v, 4) for v in self.asi_equity],
                "equal_weight": [round(v, 4) for v in self.equal_weight_equity],
            },
        }


# ── Engine runner ─────────────────────────────────────────────────────


def _run_engine_at_date(
    engine: RecommendationEngine,
    all_data: Dict[str, pd.DataFrame],
    as_of: pd.Timestamp,
    horizon: TimeHorizon,
) -> List[Tuple[str, str, float, float]]:
    """
    Run the recommendation engine for all symbols using data up to `as_of`.

    Returns: list of (symbol, action, confidence, current_price)
    """
    # Get ASI data up to as_of for regime detection
    asi_df = all_data.get("ASI")
    market_df = asi_df.loc[:as_of] if asi_df is not None else None
    if market_df is not None and len(market_df) < 50:
        market_df = None

    results = []
    for symbol, full_df in all_data.items():
        if symbol == "ASI":
            continue

        # Slice data up to as_of (no look-ahead)
        df = full_df.loc[:as_of].copy()
        if len(df) < 50:
            continue

        try:
            rec = engine.generate_recommendation(
                symbol=symbol,
                name=symbol,
                price_data=df,
                horizon=horizon,
                market_data=market_df,
            )
            if rec is not None:
                results.append((
                    symbol,
                    rec.action.value,
                    rec.confidence,
                    rec.current_price,
                ))
        except Exception as e:
            logger.debug("Engine error for %s at %s: %s", symbol, as_of, e)

    return results


# ── Main backtester ───────────────────────────────────────────────────


def run_backtest(
    config: Optional[BacktestConfig] = None,
    db_path: Path = DB_PATH,
) -> BacktestResults:
    """
    Run a walk-forward backtest.

    At each rebalance date:
    1. Run the engine on all symbols using data up to that date.
    2. Pick the top N stocks (by BUY signal or confidence rank).
    3. Measure the forward return over the holding period.
    4. Compare to ASI return and equal-weight basket return.
    """
    if config is None:
        config = BacktestConfig()

    logger.info("Loading OHLCV data from %s", db_path)
    all_data = load_all_ohlcv(db_path)

    # Get the common trading dates (excluding ASI)
    stock_symbols = [s for s in all_data if s != "ASI"]
    if not stock_symbols:
        raise ValueError("No stock data found in historical DB")

    # Use dates from the symbol with the most data
    reference = max(stock_symbols, key=lambda s: len(all_data[s]))
    trading_dates = all_data[reference].index.tolist()

    engine = RecommendationEngine()
    snapshots: List[RebalanceSnapshot] = []

    # Determine rebalance dates
    rebalance_indices = list(range(
        config.warmup_sessions,
        len(trading_dates) - config.holding_period,
        config.rebalance_every,
    ))

    logger.info(
        "Backtesting %d rebalances over %d sessions (%s → %s), %d symbols",
        len(rebalance_indices),
        len(trading_dates),
        trading_dates[0].date(),
        trading_dates[-1].date(),
        len(stock_symbols),
    )

    total_buy_picks = 0
    total_rank_picks = 0

    for idx in rebalance_indices:
        as_of = trading_dates[idx]
        exit_date = trading_dates[idx + config.holding_period]

        # 1. Run engine
        engine_results = _run_engine_at_date(
            engine, all_data, as_of, config.horizon
        )

        if not engine_results:
            continue

        # 2. Select picks
        # First try: stocks with BUY/STRONG_BUY action
        buy_picks = [
            (sym, act, conf, price)
            for sym, act, conf, price in engine_results
            if act in config.pick_actions
        ]
        buy_picks.sort(key=lambda x: x[2], reverse=True)

        if buy_picks:
            selected = buy_picks[: config.top_n]
            total_buy_picks += len(selected)
        elif config.fallback_to_confidence_rank:
            # Fallback: rank all by confidence, pick top N
            engine_results.sort(key=lambda x: x[2], reverse=True)
            selected = engine_results[: config.top_n]
            total_rank_picks += len(selected)
        else:
            continue

        # 3. Measure forward returns
        picks: List[PickRecord] = []
        for sym, act, conf, entry_price in selected:
            sym_df = all_data.get(sym)
            if sym_df is None:
                continue

            # Get exit price
            exit_rows = sym_df.loc[sym_df.index >= exit_date]
            if exit_rows.empty:
                continue
            exit_price = float(exit_rows.iloc[0]["Close"])

            ret = (exit_price - entry_price) / entry_price * 100

            pick = PickRecord(
                rebalance_date=as_of.date(),
                symbol=sym,
                action=act,
                confidence=conf,
                price_at_pick=entry_price,
                price_at_exit=exit_price,
                return_pct=ret,
            )
            picks.append(pick)

        if not picks:
            continue

        # 4. Benchmark: ASI return over same period
        asi_df = all_data.get("ASI")
        asi_return = None
        if asi_df is not None:
            asi_at_entry = asi_df.loc[asi_df.index <= as_of]
            asi_at_exit = asi_df.loc[asi_df.index >= exit_date]
            if not asi_at_entry.empty and not asi_at_exit.empty:
                asi_entry = float(asi_at_entry.iloc[-1]["Close"])
                asi_exit = float(asi_at_exit.iloc[0]["Close"])
                asi_return = (asi_exit - asi_entry) / asi_entry * 100

        # 5. Benchmark: equal-weight basket return
        ew_returns = []
        for sym in stock_symbols:
            sym_df = all_data.get(sym)
            if sym_df is None:
                continue
            entry_rows = sym_df.loc[sym_df.index <= as_of]
            exit_rows = sym_df.loc[sym_df.index >= exit_date]
            if not entry_rows.empty and not exit_rows.empty:
                ep = float(entry_rows.iloc[-1]["Close"])
                xp = float(exit_rows.iloc[0]["Close"])
                if ep > 0:
                    ew_returns.append((xp - ep) / ep * 100)

        ew_return = float(np.mean(ew_returns)) if ew_returns else None

        # Tag picks with benchmark comparison
        portfolio_return = float(np.mean([p.return_pct for p in picks]))
        for pick in picks:
            if asi_return is not None:
                pick.benchmark_return_pct = asi_return
                pick.beat_benchmark = pick.return_pct > asi_return

        snapshot = RebalanceSnapshot(
            rebalance_date=as_of.date(),
            picks=picks,
            asi_return=asi_return,
            equal_weight_return=ew_return,
            portfolio_return=portfolio_return,
        )
        snapshots.append(snapshot)

    # ── Compute aggregate metrics ─────────────────────────────────────

    results = BacktestResults(config=config, snapshots=snapshots)
    results.total_rebalances = len(snapshots)
    results.total_picks = sum(len(s.picks) for s in snapshots)
    results.picks_with_buy_signal = total_buy_picks
    results.picks_from_confidence_rank = total_rank_picks

    if not snapshots:
        logger.warning("No rebalance snapshots produced")
        return results

    # Equity curves (compounding)
    port_equity = [1.0]
    asi_equity = [1.0]
    ew_equity = [1.0]

    all_pick_returns = []
    beats_asi = 0
    beats_ew = 0
    total_comparable_asi = 0
    total_comparable_ew = 0

    for snap in snapshots:
        if snap.portfolio_return is not None:
            port_equity.append(port_equity[-1] * (1 + snap.portfolio_return / 100))
            all_pick_returns.append(snap.portfolio_return)
        if snap.asi_return is not None:
            asi_equity.append(asi_equity[-1] * (1 + snap.asi_return / 100))
        if snap.equal_weight_return is not None:
            ew_equity.append(ew_equity[-1] * (1 + snap.equal_weight_return / 100))

        # Hit rates
        if snap.portfolio_return is not None and snap.asi_return is not None:
            total_comparable_asi += 1
            if snap.portfolio_return > snap.asi_return:
                beats_asi += 1
        if snap.portfolio_return is not None and snap.equal_weight_return is not None:
            total_comparable_ew += 1
            if snap.portfolio_return > snap.equal_weight_return:
                beats_ew += 1

    results.portfolio_equity = port_equity
    results.asi_equity = asi_equity
    results.equal_weight_equity = ew_equity

    results.portfolio_cumulative_return = (port_equity[-1] - 1) * 100
    results.asi_cumulative_return = (asi_equity[-1] - 1) * 100
    results.equal_weight_cumulative_return = (ew_equity[-1] - 1) * 100

    # Alpha
    results.alpha_vs_asi = results.portfolio_cumulative_return - results.asi_cumulative_return
    results.alpha_vs_equal_weight = results.portfolio_cumulative_return - results.equal_weight_cumulative_return

    # Annualised return (approximate)
    n_days = (snapshots[-1].rebalance_date - snapshots[0].rebalance_date).days
    if n_days > 0:
        years = n_days / 365.25
        results.portfolio_annualised_return = (
            (port_equity[-1] ** (1 / years)) - 1
        ) * 100

    # Sharpe ratio
    if all_pick_returns and len(all_pick_returns) > 1:
        period_rf = RISK_FREE_RATE_ANNUAL / (252 / config.holding_period) * 100
        excess = [r - period_rf for r in all_pick_returns]
        if np.std(excess) > 0:
            results.sharpe_ratio = float(
                np.mean(excess) / np.std(excess) * np.sqrt(252 / config.holding_period)
            )

    # Max drawdown
    peak = 1.0
    max_dd = 0.0
    for v in port_equity:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd
    results.max_drawdown = max_dd * 100

    # Hit rates
    results.hit_rate_vs_asi = (beats_asi / total_comparable_asi * 100) if total_comparable_asi else 0
    results.hit_rate_vs_equal_weight = (beats_ew / total_comparable_ew * 100) if total_comparable_ew else 0

    # Win/loss
    wins = [r for r in all_pick_returns if r > 0]
    losses = [r for r in all_pick_returns if r < 0]
    results.avg_pick_return = float(np.mean(all_pick_returns)) if all_pick_returns else 0
    if losses:
        avg_win = float(np.mean(wins)) if wins else 0
        avg_loss = abs(float(np.mean(losses)))
        results.win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")
    elif wins:
        results.win_loss_ratio = float("inf")

    logger.info(
        "Backtest complete: %d rebalances, portfolio %.2f%% vs ASI %.2f%% vs EW %.2f%%",
        results.total_rebalances,
        results.portfolio_cumulative_return,
        results.asi_cumulative_return,
        results.equal_weight_cumulative_return,
    )

    return results
