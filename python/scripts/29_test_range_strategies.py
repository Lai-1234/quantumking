"""Test the 3 new range strategies (VWAP-opt, Volume Profile, Price Action).

Step 1: small grid per strategy, report solo PF/Sharpe/DD + RANGE-regime PnL
Step 2: add the best to the v6 5-strategy portfolio, check if Sharpe improves
        and coordination (range PnL share) increases.
"""
from __future__ import annotations

import itertools
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.backtest import BacktestConfig, run
from quantumking.filters import apply_filters
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import (
    adx_trend, ma_trend, macd_momentum, pivot_divergence, smc_orderblock,
    vwap_optimized, volume_profile_reversion, price_action_reversion,
)


def composite(s, min_t=30):
    pf, t, dd = s["pf"], s["trades"], abs(s["max_dd_pct"])
    if pf <= 0 or t < min_t:
        return -1
    import math
    return pf * math.sqrt(min(t, 200) / 200) * (1 - min(dd, 0.4))


def range_pnl_split(res, reg):
    trades = res.trades
    if trades.empty:
        return 0, 0
    reg_arr = reg.to_numpy()
    in_trend = [bool(reg_arr[int(t)]) if int(t) < len(reg_arr) else False
                for t in trades["bar_in"]]
    tr = trades.assign(in_trend=in_trend)
    return (tr.loc[tr["in_trend"], "pnl_usd"].sum(),
            tr.loc[~tr["in_trend"], "pnl_usd"].sum())


def main():
    d = ROOT / "data"
    m15 = pd.read_parquet(d / "XAUUSD_M15.parquet")
    h1 = pd.read_parquet(d / "XAUUSD_H1.parquet")
    h4 = pd.read_parquet(d / "XAUUSD_H4.parquet")
    d1 = pd.read_parquet(d / "XAUUSD_D1.parquet")
    reg = regime(m15)
    trail = TrailParams(2000, 1500, 500)

    # ============================================================
    # STEP 1: small grid per new strategy
    # ============================================================
    print("=" * 70)
    print("STEP 1: New range strategies — solo performance (reversion regime)")
    print("=" * 70)

    candidates = {}

    print("\n--- VWAP_Optimized ---")
    best_vwap = None
    for k in [2.0, 2.5, 3.0]:
        for shadow in [1.0, 1.2, 1.5]:
            for vf in [True, False]:
                p = vwap_optimized.VwapOptParams(sigma_k=k, shadow_mult=shadow, vol_filter=vf, sl_pts=600)
                sigs = vwap_optimized.generate_signals(m15, p)
                res = run(m15, sigs, BacktestConfig(trail=trail), regime=reg, strategy_kind="reversion")
                sc = composite(res.stats)
                if best_vwap is None or sc > best_vwap[0]:
                    best_vwap = (sc, res, p, sigs)
    s = best_vwap[1].stats
    tp, rp = range_pnl_split(best_vwap[1], reg)
    print(f"  best: k={best_vwap[2].sigma_k} shadow={best_vwap[2].shadow_mult} vf={best_vwap[2].vol_filter}")
    print(f"  PF={s['pf']:.2f} Sharpe={s['sharpe']:.2f} DD={s['max_dd_pct']*100:.1f}% trades={s['trades']} | trendPnL=${tp:.0f} rangePnL=${rp:.0f}")
    candidates["VWAP_Opt"] = best_vwap

    print("\n--- Volume_Profile_Reversion ---")
    best_vp = None
    for ext in [100, 200, 300]:
        for shadow in [0.8, 1.0, 1.5]:
            for nb in [30, 50]:
                p = volume_profile_reversion.VPParams(n_bins=nb, extension_pts=ext, shadow_mult=shadow, sl_pts=600)
                sigs = volume_profile_reversion.generate_signals(m15, p)
                res = run(m15, sigs, BacktestConfig(trail=trail), regime=reg, strategy_kind="reversion")
                sc = composite(res.stats)
                if best_vp is None or sc > best_vp[0]:
                    best_vp = (sc, res, p, sigs)
    s = best_vp[1].stats
    tp, rp = range_pnl_split(best_vp[1], reg)
    print(f"  best: ext={best_vp[2].extension_pts} shadow={best_vp[2].shadow_mult} bins={best_vp[2].n_bins}")
    print(f"  PF={s['pf']:.2f} Sharpe={s['sharpe']:.2f} DD={s['max_dd_pct']*100:.1f}% trades={s['trades']} | trendPnL=${tp:.0f} rangePnL=${rp:.0f}")
    candidates["VolProfile"] = best_vp

    print("\n--- Price_Action_Reversion ---")
    best_pa = None
    for pin in [1.5, 2.0, 2.5]:
        for dist in [200, 300, 400]:
            p = price_action_reversion.PAParams(pin_ratio=pin, vwap_dist_pts=dist, sl_pts=500)
            sigs = price_action_reversion.generate_signals(m15, p)
            res = run(m15, sigs, BacktestConfig(trail=trail), regime=reg, strategy_kind="reversion")
            sc = composite(res.stats)
            if best_pa is None or sc > best_pa[0]:
                best_pa = (sc, res, p, sigs)
    s = best_pa[1].stats
    tp, rp = range_pnl_split(best_pa[1], reg)
    print(f"  best: pin={best_pa[2].pin_ratio} dist={best_pa[2].vwap_dist_pts}")
    print(f"  PF={s['pf']:.2f} Sharpe={s['sharpe']:.2f} DD={s['max_dd_pct']*100:.1f}% trades={s['trades']} | trendPnL=${tp:.0f} rangePnL=${rp:.0f}")
    candidates["PriceAction"] = best_pa

    # ============================================================
    # STEP 2: build base v6 portfolio specs, test each addition
    # ============================================================
    print("\n" + "=" * 70)
    print("STEP 2: Portfolio coordination test (base v6 + each new strategy)")
    print("=" * 70)

    def base_specs():
        ma_p = ma_trend.MAParams(fast_ema=10, slow_ema=80, kdj_period=9, kdj_d=2, kdj_s=2, fibo_bottom=0.4)
        ma = ma_trend.generate_signals(m15, h4, ma_p)
        macd_p = macd_momentum.MacdParams(fast=18, slow=35, signal=7)
        macd = apply_filters(macd_momentum.generate_signals(m15, h1, h4, macd_p), df_h1=h1, df_h4=h4); macd["sl_pts"] *= 0.5
        smc_p = smc_orderblock.SmcParams(sl_buffer_pts=60, fib_tolerance_pts=200, scan_window=100)
        smc = apply_filters(smc_orderblock.generate_signals(m15, smc_p), df_h1=h1, df_h4=h4); smc["sl_pts"] *= 0.5
        adx = apply_filters(adx_trend.generate_signals(m15, adx_trend.AdxParams(14, 25.0)), df_h1=h1, df_h4=h4)
        piv_p = pivot_divergence.PivotParams(rsi_period=10, touch_buffer_pts=300, sl_pts=1500)
        piv = apply_filters(pivot_divergence.generate_signals(m15, d1, piv_p), df_h1=h1, df_h4=h4); piv["sl_pts"] *= 0.5
        return [
            StratSpec("MA_Trend", ma, trail, "trend", 1.0),
            StratSpec("SMC", smc, trail, "trend", 0.7),
            StratSpec("MACD", macd, trail, "trend", 0.3),
            StratSpec("ADX", adx, trail, "trend", 0.3),
            StratSpec("Pivot", piv, trail, "reversion", 0.4),
        ]

    cfg = PortfolioConfig(initial_equity=10_000, max_positions=6, danger_hours=(),
                          drawdown_kill_pct=0.25, spread_pts=17, slippage_pts=5)

    base = run_portfolio(m15, base_specs(), cfg, regime=reg)
    print(f"\nBASE v6 (5 strat): PF={base['pf']:.3f} Sharpe={base['sharpe']:.2f} "
          f"DD={base['max_dd_pct']*100:.1f}% PnL=${base['net_pnl']:.0f}")

    add_map = {
        "VWAP_Opt": (candidates["VWAP_Opt"][3], "reversion", 0.4),
        "VolProfile": (candidates["VolProfile"][3], "reversion", 0.4),
        "PriceAction": (candidates["PriceAction"][3], "reversion", 0.4),
    }
    for name, (sigs, kind, w) in add_map.items():
        specs = base_specs() + [StratSpec(name, sigs, trail, kind, w)]
        res = run_portfolio(m15, specs, cfg, regime=reg)
        delta = res["sharpe"] - base["sharpe"]
        verdict = "ADD" if delta > 0.02 else ("neutral" if delta > -0.02 else "HURTS")
        print(f"+ {name:12s}: PF={res['pf']:.3f} Sharpe={res['sharpe']:.2f} "
              f"DD={res['max_dd_pct']*100:.1f}% PnL=${res['net_pnl']:.0f}  "
              f"dSharpe={delta:+.2f}  [{verdict}]")

    # Also test ALL three added together
    specs = base_specs()
    for name, (sigs, kind, w) in add_map.items():
        specs.append(StratSpec(name, sigs, trail, kind, w))
    res = run_portfolio(m15, specs, cfg, regime=reg)
    print(f"\n+ ALL THREE: PF={res['pf']:.3f} Sharpe={res['sharpe']:.2f} "
          f"DD={res['max_dd_pct']*100:.1f}% PnL=${res['net_pnl']:.0f}  "
          f"dSharpe={res['sharpe']-base['sharpe']:+.2f}")


if __name__ == "__main__":
    main()
