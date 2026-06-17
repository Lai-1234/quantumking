"""Audit v6 Layer 1: exhaustive per-strategy fine grid.

Replicates the user's MT5 optimizer density (10k+ per strategy).
6 strategies tested: MA_Trend, MACD, SMC, ADX_MTF, Asian, Fractal.

Usage:
  --quick    Run with TINY subsets (~50 combos per strategy) to validate pipeline
  --full     Run the full ~46k-combo sweep (4-6 hours, multiprocessing)
"""
from __future__ import annotations

import argparse
import itertools
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.backtest import BacktestConfig, run
from quantumking.filters import apply_filters
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import (
    adx_trend, asian_breakout, fractal_breakout, ma_trend, macd_momentum, smc_orderblock,
)


# ============================================================
# Grid definitions
# ============================================================

GRID_FULL = {
    "MA_Trend": {
        "fast_ema": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        "slow_ema": [40, 60, 80, 100, 120, 140, 160, 180, 200],
        "kdj_period": [5, 7, 9, 11, 13, 15],
        "kdj_d": [2, 3, 4, 5],
        "fibo_bottom": [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70],
    },
    "MACD_Momentum": {
        "fast": [8, 10, 12, 14, 16, 18],
        "slow": [21, 26, 30, 35, 40],
        "signal": [5, 7, 9, 11],
        "mtf": ["none", "H1", "H4", "H1+H4"],
        "sl_mult": [0.5, 1.0, 1.5, 2.0],
        "trail": [(500, 500, 100), (1000, 1000, 200), (1400, 1400, 100), (1400, 1400, 300), (2000, 1500, 500), (300, 150, 50)],
    },
    "SMC_OrderBlock": {
        "sl_buf": [15, 30, 45, 60, 80, 100],
        "fib_tol": [50, 100, 150, 200, 300],
        "scan": [50, 60, 70, 80, 100],
        "mtf": ["none", "H1", "H4", "H1+H4"],
        "sl_mult": [0.5, 1.0, 1.5],
        "trail": [(500, 500, 100), (1000, 1000, 200), (1400, 1400, 300), (2000, 1500, 500), (750, 1500, 500), (1400, 1400, 100)],
    },
    "ADX_Trend": {
        "period": [7, 10, 14, 18, 21, 28],
        "threshold": [15, 20, 22.5, 25, 27.5, 30, 35],
        "mtf": ["none", "H1", "H4", "H1+H4"],
        "sl_mult": [0.5, 1.0, 1.5],
        "trail": [(500, 500, 100), (1000, 1000, 200), (1400, 1400, 300), (2000, 1500, 500), (1250, 750, 300), (300, 150, 50)],
    },
    "Asian_Breakout": {
        "start_hour": [0, 1, 2],
        "end_hour": [7, 8, 9],
        "window_hours": [3, 4, 5],
        "min_body": [0.4, 0.5, 0.6, 0.7],
        "sl_buf": [30, 50, 80, 120, 200],
        "trail": [(200, 150, 30), (300, 150, 50), (500, 500, 100), (1000, 1000, 200), (1400, 1400, 300), (400, 100, 40)],
    },
    "Fractal_Breakout": {
        "buffer_pts": [10, 20, 30, 50, 80],
        "sl_buf": [10, 20, 40, 60, 100],
        "mtf": ["none", "H1", "H4", "H1+H4"],
        "sl_mult": [0.5, 1.0, 1.5, 2.0],
        "trail": [(500, 500, 100), (1000, 1000, 200), (1400, 1400, 300), (2000, 1500, 500), (1400, 1400, 100), (300, 150, 50)],
    },
}

# Quick mode: take first 2 values from each axis to keep total ~50 combos per strategy.
GRID_QUICK = {s: {k: (v[:2] if len(v) > 2 else v) for k, v in axes.items()}
              for s, axes in GRID_FULL.items()}


# ============================================================
# Backtest wrappers (one per strategy)
# ============================================================

def _composite_score(s: dict, min_trades: int = 30) -> float:
    pf = s["pf"]
    t = s["trades"]
    dd = abs(s["max_dd_pct"])
    if pf <= 0 or t < min_trades:
        return -1.0
    import math
    conf = math.sqrt(min(t, 200) / 200)
    dd_penalty = 1.0 - min(dd, 0.4)
    return pf * conf * dd_penalty


def _eval_ma_trend(params, data, reg):
    fast, slow, kdj_p, kdj_d, fibo_b = params
    if slow <= fast:
        return None
    p = ma_trend.MAParams(
        fast_ema=fast, slow_ema=slow, kdj_period=kdj_p, kdj_d=kdj_d, kdj_s=2,
        stoch_ob=70, stoch_os=40, fibo_top=0.5, fibo_bottom=fibo_b,
        zone_buffer_pts=150, sl_buffer_pts=300, max_sl_pts=800,
    )
    sigs = ma_trend.generate_signals(data["M15"], data["H4"], p)
    res = run(data["M15"], sigs, BacktestConfig(initial_equity=10_000,
                                                  trail=TrailParams(1400, 1400, 100)),
              regime=reg, strategy_kind="trend")
    s = res.stats
    s.update({"strategy": "MA_Trend", "fast_ema": fast, "slow_ema": slow,
              "kdj_p": kdj_p, "kdj_d": kdj_d, "fibo_b": fibo_b,
              "score": _composite_score(s)})
    return s


def _eval_macd(params, data, reg):
    fast, slow, sig_, mtf, sl_m, trail = params
    if slow <= fast:
        return None
    base = macd_momentum.generate_signals(data["M15"], data["H1"], data["H4"],
                                             macd_momentum.MacdParams(fast=fast, slow=slow, signal=sig_))
    if mtf == "H1":
        base = apply_filters(base, df_h1=data["H1"])
    elif mtf == "H4":
        base = apply_filters(base, df_h4=data["H4"])
    elif mtf == "H1+H4":
        base = apply_filters(base, df_h1=data["H1"], df_h4=data["H4"])
    base["sl_pts"] = base["sl_pts"] * sl_m
    res = run(data["M15"], base, BacktestConfig(initial_equity=10_000,
                                                  trail=TrailParams(*trail)),
              regime=reg, strategy_kind="trend")
    s = res.stats
    s.update({"strategy": "MACD_Momentum", "fast": fast, "slow": slow, "sig": sig_,
              "mtf": mtf, "sl_mult": sl_m, "trail": str(trail),
              "score": _composite_score(s)})
    return s


def _eval_smc(params, data, reg):
    sl_buf, fib_tol, scan, mtf, sl_m, trail = params
    p = smc_orderblock.SmcParams(sl_buffer_pts=sl_buf, fib_tolerance_pts=fib_tol, scan_window=scan)
    base = smc_orderblock.generate_signals(data["M15"], p)
    if mtf == "H1":
        base = apply_filters(base, df_h1=data["H1"])
    elif mtf == "H4":
        base = apply_filters(base, df_h4=data["H4"])
    elif mtf == "H1+H4":
        base = apply_filters(base, df_h1=data["H1"], df_h4=data["H4"])
    base["sl_pts"] = base["sl_pts"] * sl_m
    res = run(data["M15"], base, BacktestConfig(initial_equity=10_000,
                                                  trail=TrailParams(*trail)),
              regime=reg, strategy_kind="trend")
    s = res.stats
    s.update({"strategy": "SMC_OrderBlock", "sl_buf": sl_buf, "fib_tol": fib_tol,
              "scan": scan, "mtf": mtf, "sl_mult": sl_m, "trail": str(trail),
              "score": _composite_score(s)})
    return s


def _eval_adx(params, data, reg):
    period, thresh, mtf, sl_m, trail = params
    p = adx_trend.AdxParams(period=period, threshold=thresh)
    base = adx_trend.generate_signals(data["M15"], p)
    if mtf == "H1":
        base = apply_filters(base, df_h1=data["H1"])
    elif mtf == "H4":
        base = apply_filters(base, df_h4=data["H4"])
    elif mtf == "H1+H4":
        base = apply_filters(base, df_h1=data["H1"], df_h4=data["H4"])
    base["sl_pts"] = base["sl_pts"] * sl_m
    res = run(data["M15"], base, BacktestConfig(initial_equity=10_000,
                                                  trail=TrailParams(*trail)),
              regime=reg, strategy_kind="trend")
    s = res.stats
    s.update({"strategy": "ADX_Trend", "period": period, "threshold": thresh,
              "mtf": mtf, "sl_mult": sl_m, "trail": str(trail),
              "score": _composite_score(s)})
    return s


def _eval_asian(params, data, reg):
    sh, eh, wh, body, sl_buf, trail = params
    if eh <= sh:
        return None
    p = asian_breakout.AsianParams(start_hour=sh, end_hour=eh,
                                       breakout_window_hours=wh,
                                       min_body_ratio=body, sl_buffer_pts=sl_buf)
    base = asian_breakout.generate_signals(data["M15"], p)
    res = run(data["M15"], base, BacktestConfig(initial_equity=10_000,
                                                  trail=TrailParams(*trail)),
              regime=reg, strategy_kind="trend")
    s = res.stats
    s.update({"strategy": "Asian_Breakout", "start_hour": sh, "end_hour": eh,
              "window_hours": wh, "min_body": body, "sl_buf": sl_buf,
              "trail": str(trail), "score": _composite_score(s)})
    return s


def _eval_fractal(params, data, reg):
    buf, sl_buf, mtf, sl_m, trail = params
    p = fractal_breakout.FractalParams(buffer_pts=buf, sl_buffer_pts=sl_buf)
    base = fractal_breakout.generate_signals(data["M15"], p)
    if mtf == "H1":
        base = apply_filters(base, df_h1=data["H1"])
    elif mtf == "H4":
        base = apply_filters(base, df_h4=data["H4"])
    elif mtf == "H1+H4":
        base = apply_filters(base, df_h1=data["H1"], df_h4=data["H4"])
    base["sl_pts"] = base["sl_pts"] * sl_m
    res = run(data["M15"], base, BacktestConfig(initial_equity=10_000,
                                                  trail=TrailParams(*trail)),
              regime=reg, strategy_kind="trend")
    s = res.stats
    s.update({"strategy": "Fractal_Breakout", "buf_pts": buf, "sl_buf": sl_buf,
              "mtf": mtf, "sl_mult": sl_m, "trail": str(trail),
              "score": _composite_score(s)})
    return s


EVALUATORS = {
    "MA_Trend": _eval_ma_trend,
    "MACD_Momentum": _eval_macd,
    "SMC_OrderBlock": _eval_smc,
    "ADX_Trend": _eval_adx,
    "Asian_Breakout": _eval_asian,
    "Fractal_Breakout": _eval_fractal,
}


def _grid_for(strategy: str, axes: dict) -> list:
    """Produce list of parameter tuples for the strategy."""
    keys = list(axes.keys())
    values = [axes[k] for k in keys]
    return list(itertools.product(*values))


def run_grid_for_strategy(strategy: str, axes: dict, data: dict, reg,
                           n_jobs: int = -2) -> pd.DataFrame:
    combos = _grid_for(strategy, axes)
    evaluator = EVALUATORS[strategy]
    print(f"  [{strategy}] grid size: {len(combos)}")
    t0 = time.time()
    rows = Parallel(n_jobs=n_jobs, verbose=5)(
        delayed(evaluator)(c, data, reg) for c in combos
    )
    rows = [r for r in rows if r is not None]
    elapsed = time.time() - t0
    print(f"  [{strategy}] {len(rows)} valid results in {elapsed:.1f}s "
          f"({elapsed/max(len(rows),1)*1000:.0f} ms/run)")
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="50-combo subset per strategy (validate pipeline)")
    ap.add_argument("--full", action="store_true", help="Full ~46k sweep (4-6 hours)")
    ap.add_argument("--n_jobs", type=int, default=-2, help="Parallel jobs (-2 = all-but-one core)")
    args = ap.parse_args()
    if not (args.quick or args.full):
        args.quick = True  # default safety

    d = ROOT / "data"
    data = {
        "M15": pd.read_parquet(d / "XAUUSD_M15.parquet"),
        "H1": pd.read_parquet(d / "XAUUSD_H1.parquet"),
        "H4": pd.read_parquet(d / "XAUUSD_H4.parquet"),
    }
    reg = regime(data["M15"])

    grid = GRID_QUICK if args.quick else GRID_FULL
    label = "quick" if args.quick else "full"
    print(f"Mode: {label}")

    all_results = []
    for strategy, axes in grid.items():
        print(f"\n=== Strategy: {strategy} ===")
        df = run_grid_for_strategy(strategy, axes, data, reg, n_jobs=args.n_jobs)
        if df.empty:
            print(f"  (no valid results)")
            continue
        all_results.append(df)
        # Top 10 per strategy
        top10 = df.sort_values("score", ascending=False).head(10)
        cols = [c for c in ["pf", "net_pnl", "win_rate", "max_dd_pct", "sharpe",
                             "trades", "score"] if c in top10.columns]
        print(f"  Top 5 by score:")
        print(top10[cols].head(5).to_string(index=False))

    if all_results:
        big = pd.concat(all_results, ignore_index=True)
        out = d / f"layer1_fine_grid_{label}.csv"
        big.to_csv(out, index=False)
        print(f"\nSaved {out.relative_to(ROOT)} ({len(big):,} rows)")

        # Top 50 per strategy → for Layer 2
        top50_list = []
        for s in big["strategy"].unique():
            sub = big[big["strategy"] == s].sort_values("score", ascending=False).head(50)
            top50_list.append(sub)
        pd.concat(top50_list).to_csv(d / f"layer1_top50_{label}.csv", index=False)
        print(f"Saved layer1_top50_{label}.csv (top 50 per strategy for Layer 2)")


if __name__ == "__main__":
    main()
