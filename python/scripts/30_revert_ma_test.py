"""Test: original PF-1.77 MA_Trend params + the 4 v6 strategies.

Also sweep weights to find a config with DD < 25% (real-tick showed 27%).
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.filters import apply_filters
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import (
    adx_trend, ma_trend, macd_momentum, pivot_divergence, smc_orderblock,
)


def build_specs(weights, ma_trail=(1400, 1400, 100)):
    d = ROOT / "data"
    m15 = pd.read_parquet(d / "XAUUSD_M15.parquet")
    h1 = pd.read_parquet(d / "XAUUSD_H1.parquet")
    h4 = pd.read_parquet(d / "XAUUSD_H4.parquet")
    d1 = pd.read_parquet(d / "XAUUSD_D1.parquet")

    # ORIGINAL MA_Trend (PF 1.77): Fast 10, Slow 40, KDJ 7/2/2, Fibo 0.5/0.677
    ma_p = ma_trend.MAParams(fast_ema=10, slow_ema=40, kdj_period=7, kdj_d=2, kdj_s=2,
                                stoch_ob=70, stoch_os=40, fibo_top=0.5, fibo_bottom=0.677,
                                zone_buffer_pts=150, sl_buffer_pts=300, max_sl_pts=800)
    ma = ma_trend.generate_signals(m15, h4, ma_p)

    macd_p = macd_momentum.MacdParams(fast=18, slow=35, signal=7)
    macd = apply_filters(macd_momentum.generate_signals(m15, h1, h4, macd_p), df_h1=h1, df_h4=h4); macd["sl_pts"] *= 0.5
    smc_p = smc_orderblock.SmcParams(sl_buffer_pts=60, fib_tolerance_pts=200, scan_window=100)
    smc = apply_filters(smc_orderblock.generate_signals(m15, smc_p), df_h1=h1, df_h4=h4); smc["sl_pts"] *= 0.5
    adx = apply_filters(adx_trend.generate_signals(m15, adx_trend.AdxParams(14, 25.0)), df_h1=h1, df_h4=h4)
    piv_p = pivot_divergence.PivotParams(rsi_period=10, touch_buffer_pts=300, sl_pts=1500)
    piv = apply_filters(pivot_divergence.generate_signals(m15, d1, piv_p), df_h1=h1, df_h4=h4); piv["sl_pts"] *= 0.5

    other_trail = TrailParams(2000, 1500, 500)
    return [
        StratSpec("MA_Trend", ma, TrailParams(*ma_trail), "trend", weights["MA"]),
        StratSpec("SMC", smc, other_trail, "trend", weights["SMC"]),
        StratSpec("MACD", macd, other_trail, "trend", weights["MACD"]),
        StratSpec("ADX", adx, other_trail, "trend", weights["ADX"]),
        StratSpec("Pivot", piv, other_trail, "reversion", weights["Pivot"]),
    ], m15


def main():
    reg = None
    configs = {
        "v6 weights (MA 1.0/SMC 0.7/MACD 0.3/ADX 0.3/Piv 0.4)":
            {"MA": 1.0, "SMC": 0.7, "MACD": 0.3, "ADX": 0.3, "Pivot": 0.4},
        "Lower-risk (all x0.6)":
            {"MA": 0.6, "SMC": 0.42, "MACD": 0.18, "ADX": 0.18, "Pivot": 0.24},
        "MA-heavy (MA 1.0, others 0.2)":
            {"MA": 1.0, "SMC": 0.2, "MACD": 0.2, "ADX": 0.2, "Pivot": 0.2},
        "Balanced-trim (MA 0.8/SMC 0.5/MACD 0.2/ADX 0.3/Piv 0.3)":
            {"MA": 0.8, "SMC": 0.5, "MACD": 0.2, "ADX": 0.3, "Pivot": 0.3},
    }
    cfg = PortfolioConfig(initial_equity=10_000, max_positions=6, danger_hours=(),
                          drawdown_kill_pct=0.25, spread_pts=17, slippage_pts=5)

    rows = []
    for label, w in configs.items():
        specs, m15 = build_specs(w)
        if reg is None:
            reg = regime(m15)
        res = run_portfolio(m15, specs, cfg, regime=reg)
        rows.append({
            "config": label, "trades": res["trades"], "pf": round(res["pf"], 3),
            "net_pnl": round(res["net_pnl"], 0),
            "max_dd_pct": round(res["max_dd_pct"] * 100, 1),
            "sharpe": round(res["sharpe"], 2),
        })
        print(f"{label}")
        print(f"   PF={res['pf']:.3f}  Sharpe={res['sharpe']:.2f}  "
              f"DD={res['max_dd_pct']*100:.1f}%  PnL=${res['net_pnl']:.0f}  trades={res['trades']}")
        print(f"   per-strat:")
        print(res["by_strat"].to_string().replace("\n", "\n   "))
        print()

    pd.DataFrame(rows).to_csv(ROOT / "data" / "revert_ma_test.csv", index=False)


if __name__ == "__main__":
    main()
