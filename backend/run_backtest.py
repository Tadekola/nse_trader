"""
CLI runner for the walk-forward backtest.

Usage:
    python run_backtest.py
    python run_backtest.py --holding 20 --top 3 --horizon long_term
"""
import argparse
import json
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(__file__))
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

from app.services.backtester import run_backtest, BacktestConfig
from app.core.recommendation_engine import TimeHorizon


def main():
    parser = argparse.ArgumentParser(description="Walk-forward backtest for NSE Trader")
    parser.add_argument("--warmup", type=int, default=60, help="Warmup sessions before first rebalance")
    parser.add_argument("--rebalance", type=int, default=5, help="Rebalance every N days")
    parser.add_argument("--holding", type=int, default=5, help="Holding period in trading days")
    parser.add_argument("--top", type=int, default=5, help="Number of top picks per rebalance")
    parser.add_argument("--horizon", choices=["short_term", "swing", "long_term"], default="swing")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted report")
    args = parser.parse_args()

    config = BacktestConfig(
        warmup_sessions=args.warmup,
        rebalance_every=args.rebalance,
        holding_period=args.holding,
        top_n=args.top,
        horizon=TimeHorizon(args.horizon),
    )

    print(f"\n{'='*70}")
    print(f"  NSE Trader Walk-Forward Backtest")
    print(f"{'='*70}")
    print(f"  Horizon:    {config.horizon.value}")
    print(f"  Rebalance:  every {config.rebalance_every} trading days")
    print(f"  Holding:    {config.holding_period} trading days")
    print(f"  Top picks:  {config.top_n}")
    print(f"  Warmup:     {config.warmup_sessions} sessions")
    print(f"{'='*70}\n")

    results = run_backtest(config)

    if args.json:
        print(json.dumps(results.to_dict(), indent=2))
        return

    # ── Formatted report ──────────────────────────────────────────────

    print(f"\n{'─'*70}")
    print(f"  BACKTEST RESULTS")
    print(f"{'─'*70}\n")

    print(f"  Rebalances:           {results.total_rebalances}")
    print(f"  Total picks:          {results.total_picks}")
    print(f"  BUY signal picks:     {results.picks_with_buy_signal}")
    print(f"  Confidence-rank picks:{results.picks_from_confidence_rank}")

    print(f"\n  {'CUMULATIVE RETURNS':─<40}")
    print(f"  Engine portfolio:     {results.portfolio_cumulative_return:+.2f}%")
    print(f"  ASI (market):         {results.asi_cumulative_return:+.2f}%")
    print(f"  Equal-weight basket:  {results.equal_weight_cumulative_return:+.2f}%")
    print(f"  Annualised return:    {results.portfolio_annualised_return:+.2f}%")

    print(f"\n  {'ALPHA':─<40}")
    print(f"  vs ASI:               {results.alpha_vs_asi:+.2f}%")
    print(f"  vs Equal-weight:      {results.alpha_vs_equal_weight:+.2f}%")

    print(f"\n  {'RISK':─<40}")
    print(f"  Sharpe ratio:         {results.sharpe_ratio:.2f}")
    print(f"  Max drawdown:         {results.max_drawdown:.2f}%")

    print(f"\n  {'ACCURACY':─<40}")
    print(f"  Hit rate vs ASI:      {results.hit_rate_vs_asi:.1f}%")
    print(f"  Hit rate vs EW:       {results.hit_rate_vs_equal_weight:.1f}%")
    print(f"  Avg pick return:      {results.avg_pick_return:+.2f}%")
    print(f"  Win/loss ratio:       {results.win_loss_ratio:.2f}")

    # Interpretation
    print(f"\n{'─'*70}")
    print(f"  INTERPRETATION")
    print(f"{'─'*70}\n")

    if results.alpha_vs_asi > 0 and results.alpha_vs_equal_weight > 0:
        print("  ✅ Engine picks outperformed BOTH benchmarks.")
    elif results.alpha_vs_asi > 0:
        print("  ⚠️  Engine picks beat ASI but not equal-weight basket.")
    elif results.alpha_vs_equal_weight > 0:
        print("  ⚠️  Engine picks beat equal-weight but not ASI.")
    else:
        print("  ❌ Engine picks underperformed both benchmarks.")

    if results.sharpe_ratio > 1.0:
        print("  ✅ Sharpe > 1.0 — good risk-adjusted returns.")
    elif results.sharpe_ratio > 0.5:
        print("  ⚠️  Sharpe 0.5-1.0 — moderate risk-adjusted returns.")
    else:
        print("  ❌ Sharpe < 0.5 — poor risk-adjusted returns.")

    if results.hit_rate_vs_asi > 50:
        print(f"  ✅ Engine beat ASI {results.hit_rate_vs_asi:.0f}% of rebalance periods.")
    else:
        print(f"  ❌ Engine beat ASI only {results.hit_rate_vs_asi:.0f}% of rebalance periods.")

    if results.picks_with_buy_signal == 0:
        print("\n  ℹ️  No BUY signals were generated — all picks are by confidence rank.")
        print("     This means the engine is being tested as a RANKING tool, not a")
        print("     BUY/SELL classifier. Genuine BUY signals require more data history")
        print("     or stronger price divergences.")

    print()


if __name__ == "__main__":
    main()
