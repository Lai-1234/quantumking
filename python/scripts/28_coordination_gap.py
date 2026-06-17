"""Analyze coordination of the v6 5-strategy portfolio.

1. Per-strategy monthly-return correlation matrix
2. Regime breakdown: which strategies make money in trend vs range?
3. Identify the coordination gap (what kind of new strategy would help)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.backtest import BacktestConfig, run
from quantumking.filters import apply_filters
from quantumking.indicators import atr
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import (
    adx_trend, ma_trend, macd_momentum, pivot_divergence, smc_orderblock,
)


def main():
    d = ROOT / "data"
    m15 = pd.read_parquet(d / "XAUUSD_M15.parquet")
    h1 = pd.read_parquet(d / "XAUUSD_H1.parquet")
    h4 = pd.read_parquet(d / "XAUUSD_H4.parquet")
    d1 = pd.read_parquet(d / "XAUUSD_D1.parquet")
    reg = regime(m15)
    trail = TrailParams(2000, 1500, 500)

    # Build the 5 v6 strategies, run each solo, collect equity + trades-by-month
    sigs = {}
    ma_p = ma_trend.MAParams(fast_ema=10, slow_ema=80, kdj_period=9, kdj_d=2, kdj_s=2,
                                fibo_top=0.5, fibo_bottom=0.4)
    sigs["MA_Trend"] = (ma_trend.generate_signals(m15, h4, ma_p), "trend")
    macd_p = macd_momentum.MacdParams(fast=18, slow=35, signal=7)
    msig = apply_filters(macd_momentum.generate_signals(m15, h1, h4, macd_p), df_h1=h1, df_h4=h4)
    msig["sl_pts"] *= 0.5
    sigs["MACD"] = (msig, "trend")
    smc_p = smc_orderblock.SmcParams(sl_buffer_pts=60, fib_tolerance_pts=200, scan_window=100)
    ssig = apply_filters(smc_orderblock.generate_signals(m15, smc_p), df_h1=h1, df_h4=h4)
    ssig["sl_pts"] *= 0.5
    sigs["SMC"] = (ssig, "trend")
    adx_p = adx_trend.AdxParams(period=14, threshold=25.0)
    sigs["ADX"] = (apply_filters(adx_trend.generate_signals(m15, adx_p), df_h1=h1, df_h4=h4), "trend")
    piv_p = pivot_divergence.PivotParams(rsi_period=10, touch_buffer_pts=300, sl_pts=1500)
    psig = apply_filters(pivot_divergence.generate_signals(m15, d1, piv_p), df_h1=h1, df_h4=h4)
    psig["sl_pts"] *= 0.5
    sigs["Pivot"] = (psig, "reversion")

    monthly = {}
    regime_pnl = {}
    for name, (sg, kind) in sigs.items():
        res = run(m15, sg, BacktestConfig(initial_equity=10_000, trail=trail),
                  regime=reg, strategy_kind=kind)
        eq = res.equity_curve
        monthly[name] = eq.resample("ME").last().pct_change().dropna()
        # PnL split by regime at entry
        trades = res.trades
        if not trades.empty:
            reg_arr = reg.to_numpy()
            in_trend = []
            for _, t in trades.iterrows():
                bi = int(t["bar_in"])
                in_trend.append(bool(reg_arr[bi]) if bi < len(reg_arr) else False)
            trades = trades.assign(in_trend=in_trend)
            regime_pnl[name] = {
                "trend_pnl": trades.loc[trades["in_trend"], "pnl_usd"].sum(),
                "range_pnl": trades.loc[~trades["in_trend"], "pnl_usd"].sum(),
                "trend_trades": int(trades["in_trend"].sum()),
                "range_trades": int((~trades["in_trend"]).sum()),
            }

    print("=== MONTHLY-RETURN CORRELATION MATRIX ===")
    mdf = pd.DataFrame(monthly).corr()
    print(mdf.round(2).to_string())
    print()
    print("Average pairwise correlation:",
          round(mdf.values[np.triu_indices(len(mdf), 1)].mean(), 3))
    print()

    print("=== REGIME PnL BREAKDOWN (where does each make money?) ===")
    rdf = pd.DataFrame(regime_pnl).T
    print(rdf.to_string())
    print()
    total_trend = rdf["trend_pnl"].sum()
    total_range = rdf["range_pnl"].sum()
    print(f"Portfolio PnL in TREND regime: ${total_trend:.0f}")
    print(f"Portfolio PnL in RANGE regime: ${total_range:.0f}")


if __name__ == "__main__":
    main()
