"""Monte Carlo bootstrap on the realistic-cost portfolio.

Resamples the trade sequence 5000 times to estimate confidence intervals
on PF, MaxDD, and final equity. Tells you: "PF 1.32 with 95% CI of [1.10, 1.55]
and 5% chance of MaxDD > 35%" — much more honest than a single number.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.filters import apply_filters
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import (
    adx_trend, ma_trend, macd_momentum, smc_orderblock,
)


def main():
    d = ROOT / "data"
    m15 = pd.read_parquet(d / "XAUUSD_M15.parquet")
    h1 = pd.read_parquet(d / "XAUUSD_H1.parquet")
    h4 = pd.read_parquet(d / "XAUUSD_H4.parquet")
    reg = regime(m15)

    specs = [
        StratSpec("MA_Trend", apply_filters(ma_trend.generate_signals(m15, h4), df_h1=h1, df_h4=h4),
                  TrailParams(1400, 1400, 300), kind="trend", weight=1.0),
        StratSpec("MACD_Momentum", apply_filters(macd_momentum.generate_signals(m15, h1, h4), df_h1=h1, df_h4=h4),
                  TrailParams(1000, 1000, 100), kind="trend", weight=0.5),
        StratSpec("SMC_OrderBlock", apply_filters(smc_orderblock.generate_signals(m15), df_h1=h1, df_h4=h4),
                  TrailParams(750, 1500, 500), kind="trend", weight=0.7),
        StratSpec("ADX_Trend", apply_filters(adx_trend.generate_signals(m15), df_h1=h1, df_h4=h4),
                  TrailParams(2000, 1500, 500), kind="trend", weight=0.4),
    ]

    cfg = PortfolioConfig(initial_equity=10_000, spread_pts=17, slippage_pts=5)
    print("Running base backtest...")
    res = run_portfolio(m15, specs, cfg, regime=reg)
    trades_df = res["trades_df"]
    initial = 10_000

    print(f"Base: {len(trades_df)} trades, PF {res['pf']:.3f}, "
          f"Final ${res['final_equity']:.0f}, MaxDD {res['max_dd_pct']*100:.1f}%")
    print()
    print("Running 5000 Monte Carlo bootstraps...")

    pnls = trades_df["pnl_usd"].to_numpy()
    n_trades = len(pnls)
    n_iter = 5000
    rng = np.random.default_rng(42)

    pfs = np.zeros(n_iter)
    max_dds = np.zeros(n_iter)
    finals = np.zeros(n_iter)

    for k in range(n_iter):
        order = rng.permutation(n_trades)
        seq = pnls[order]
        # Compute PF
        wins = seq[seq > 0].sum()
        losses = -seq[seq < 0].sum()
        pfs[k] = wins / losses if losses > 0 else 99
        # Equity curve + max DD
        eq = initial + np.cumsum(seq)
        running_max = np.maximum.accumulate(eq)
        dd = (eq - running_max) / running_max
        max_dds[k] = dd.min()
        finals[k] = eq[-1]

    pct = lambda arr, p: np.percentile(arr, p)
    print()
    print(f"PF        median={np.median(pfs):.3f}  90% CI=[{pct(pfs,5):.3f}, {pct(pfs,95):.3f}]  worst-1%={pct(pfs,1):.3f}")
    print(f"MaxDD %   median={np.median(max_dds)*100:.2f}%  90% CI=[{pct(max_dds,5)*100:.2f}%, {pct(max_dds,95)*100:.2f}%]  worst-1%={pct(max_dds,1)*100:.2f}%")
    print(f"Final $   median={np.median(finals):.0f}  90% CI=[{pct(finals,5):.0f}, {pct(finals,95):.0f}]  worst-1%={pct(finals,1):.0f}")
    print()
    # Probability ruin
    ruin_prob = (max_dds <= -0.20).mean()
    pf_above_one = (pfs > 1.0).mean()
    pf_above_one_two = (pfs > 1.2).mean()
    print(f"P(MaxDD > 20%) = {ruin_prob*100:.1f}%")
    print(f"P(PF > 1.0)    = {pf_above_one*100:.1f}%   (statistically real edge?)")
    print(f"P(PF > 1.2)    = {pf_above_one_two*100:.1f}%")

    out = pd.DataFrame({"pf": pfs, "max_dd": max_dds, "final": finals})
    out.to_csv(ROOT / "data" / "monte_carlo_results.csv", index=False)


if __name__ == "__main__":
    main()
