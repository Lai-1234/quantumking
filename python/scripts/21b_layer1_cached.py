"""Audit v6 Layer 1 — CACHED edition (~3x faster than 21_layer1_fine_grid.py).

Key optimization: signal generation is the slow step (involves indicator
calculation across 145k bars + MTF reindexing). Many param combos differ
ONLY in exit-side params (sl_mult, trail, mtf) — they share the same
base signal. We compute base signals once, cache them, then iterate
exit variants over the cached signal.

Speedup math:
  MACD: 6×5×4 (entry combos) × 96 (exit combos) = 11,520 evals
        Old: 11,520 signal recomputes
        New:    120 signal computes + 11,520 cheap backtests
  SMC, ADX, Fractal: similar pattern

This brings Layer 1 from ~50 min to ~15 min.
"""
from __future__ import annotations

import argparse
import itertools
import math
import sys
import time
import warnings
from pathlib import Path

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


def _composite_score(s: dict, min_trades: int = 30) -> float:
    pf = s.get("pf", 0)
    t = s.get("trades", 0)
    dd = abs(s.get("max_dd_pct", 0))
    if pf <= 0 or t < min_trades:
        return -1.0
    conf = math.sqrt(min(t, 200) / 200)
    dd_penalty = 1.0 - min(dd, 0.4)
    return pf * conf * dd_penalty


# ============================================================
# Trail presets and exit variants shared across strategies
# ============================================================

TRAIL_PRESETS = [
    (500, 500, 100),
    (1000, 1000, 200),
    (1400, 1400, 100),
    (1400, 1400, 300),
    (2000, 1500, 500),
    (300, 150, 50),
]
SL_MULTS = [0.5, 1.0, 1.5, 2.0]
MTFS = ["none", "H1", "H4", "H1+H4"]


def _backtest_cached(sigs, df_m15, reg, trail, sl_mult, kind="trend"):
    """Run backtest on a cached signal with the given exit variant."""
    s = sigs.copy()
    s["sl_pts"] = s["sl_pts"] * sl_mult
    res = run(df_m15, s, BacktestConfig(initial_equity=10_000,
                                          trail=TrailParams(*trail)),
              regime=reg, strategy_kind=kind)
    return res.stats


def _eval_variants_for_signal(base_sigs, df_m15, reg, h1, h4,
                                kind="trend",
                                use_mtf_filter=True,
                                use_sl_mult=True,
                                use_trail_grid=True,
                                extra_metadata=None):
    """Given a base signal, enumerate exit variants and return list of dicts.

    Filters/SL/trail combine to ~96 evaluations per base signal.
    """
    results = []
    mtfs_to_test = MTFS if use_mtf_filter else ["none"]
    sl_mults_to_test = SL_MULTS if use_sl_mult else [1.0]
    trails_to_test = TRAIL_PRESETS if use_trail_grid else [(1400, 1400, 100)]

    for mtf in mtfs_to_test:
        if mtf == "none":
            sigs = base_sigs
        elif mtf == "H1":
            sigs = apply_filters(base_sigs, df_h1=h1)
        elif mtf == "H4":
            sigs = apply_filters(base_sigs, df_h4=h4)
        else:
            sigs = apply_filters(base_sigs, df_h1=h1, df_h4=h4)
        for sl_m in sl_mults_to_test:
            for trail in trails_to_test:
                stats = _backtest_cached(sigs, df_m15, reg, trail, sl_m, kind=kind)
                row = {
                    "mtf": mtf,
                    "sl_mult": sl_m,
                    "trail": str(trail),
                    "pf": stats["pf"],
                    "net_pnl": stats["net_pnl"],
                    "win_rate": stats["win_rate"],
                    "max_dd_pct": stats["max_dd_pct"],
                    "sharpe": stats["sharpe"],
                    "trades": stats["trades"],
                }
                if extra_metadata:
                    row.update(extra_metadata)
                row["score"] = _composite_score(row)
                results.append(row)
    return results


# ============================================================
# Per-strategy "entry-side" workers that COMPUTE BASE SIGNAL ONCE
# then iterate exit variants
# ============================================================

def _eval_ma_entry(entry_params, data, reg):
    fast, slow, kdj_p, kdj_d, fibo_b = entry_params
    if slow <= fast:
        return []
    p = ma_trend.MAParams(
        fast_ema=fast, slow_ema=slow, kdj_period=kdj_p, kdj_d=kdj_d, kdj_s=2,
        stoch_ob=70, stoch_os=40, fibo_top=0.5, fibo_bottom=fibo_b,
        zone_buffer_pts=150, sl_buffer_pts=300, max_sl_pts=800,
    )
    base = ma_trend.generate_signals(data["M15"], data["H4"], p)
    rows = _eval_variants_for_signal(
        base, data["M15"], reg, data["H1"], data["H4"],
        kind="trend",
        use_mtf_filter=False,   # MA already has H4 baked in
        use_sl_mult=False,      # MA computes SL from swing+buffer; mult less meaningful
        use_trail_grid=True,
        extra_metadata={"strategy": "MA_Trend", "fast_ema": fast, "slow_ema": slow,
                          "kdj_p": kdj_p, "kdj_d": kdj_d, "fibo_b": fibo_b},
    )
    return rows


def _eval_macd_entry(entry_params, data, reg):
    fast, slow, sig_ = entry_params
    if slow <= fast:
        return []
    p = macd_momentum.MacdParams(fast=fast, slow=slow, signal=sig_)
    base = macd_momentum.generate_signals(data["M15"], data["H1"], data["H4"], p)
    rows = _eval_variants_for_signal(
        base, data["M15"], reg, data["H1"], data["H4"],
        kind="trend",
        extra_metadata={"strategy": "MACD_Momentum", "fast": fast, "slow": slow, "sig": sig_},
    )
    return rows


def _eval_smc_entry(entry_params, data, reg):
    sl_buf, fib_tol, scan = entry_params
    p = smc_orderblock.SmcParams(sl_buffer_pts=sl_buf, fib_tolerance_pts=fib_tol, scan_window=scan)
    base = smc_orderblock.generate_signals(data["M15"], p)
    rows = _eval_variants_for_signal(
        base, data["M15"], reg, data["H1"], data["H4"],
        kind="trend",
        extra_metadata={"strategy": "SMC_OrderBlock", "sl_buf": sl_buf,
                          "fib_tol": fib_tol, "scan": scan},
    )
    return rows


def _eval_adx_entry(entry_params, data, reg):
    period, threshold = entry_params
    p = adx_trend.AdxParams(period=period, threshold=threshold)
    base = adx_trend.generate_signals(data["M15"], p)
    rows = _eval_variants_for_signal(
        base, data["M15"], reg, data["H1"], data["H4"],
        kind="trend",
        extra_metadata={"strategy": "ADX_Trend", "period": period, "threshold": threshold},
    )
    return rows


def _eval_asian_entry(entry_params, data, reg):
    sh, eh, wh, body, sl_buf = entry_params
    if eh <= sh:
        return []
    p = asian_breakout.AsianParams(start_hour=sh, end_hour=eh,
                                       breakout_window_hours=wh,
                                       min_body_ratio=body, sl_buffer_pts=sl_buf)
    base = asian_breakout.generate_signals(data["M15"], p)
    rows = _eval_variants_for_signal(
        base, data["M15"], reg, data["H1"], data["H4"],
        kind="trend",
        use_mtf_filter=False,   # session-based, MTF would over-restrict
        extra_metadata={"strategy": "Asian_Breakout", "start_hour": sh, "end_hour": eh,
                          "window_hours": wh, "min_body": body, "sl_buf": sl_buf},
    )
    return rows


def _eval_fractal_entry(entry_params, data, reg):
    buf, sl_buf = entry_params
    p = fractal_breakout.FractalParams(buffer_pts=buf, sl_buffer_pts=sl_buf)
    base = fractal_breakout.generate_signals(data["M15"], p)
    rows = _eval_variants_for_signal(
        base, data["M15"], reg, data["H1"], data["H4"],
        kind="trend",
        extra_metadata={"strategy": "Fractal_Breakout", "buf_pts": buf, "sl_buf": sl_buf},
    )
    return rows


# ============================================================
# Grids (entry-side only — exit variants enumerated inside)
# ============================================================

GRIDS_FULL = {
    "MA_Trend": {
        "fn": _eval_ma_entry,
        "axes": {
            "fast_ema": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
            "slow_ema": [40, 60, 80, 100, 120, 140, 160, 180, 200],
            "kdj_period": [5, 7, 9, 11, 13, 15],
            "kdj_d": [2, 3, 4, 5],
            "fibo_bottom": [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70],
        },
    },
    "MACD_Momentum": {
        "fn": _eval_macd_entry,
        "axes": {
            "fast": [8, 10, 12, 14, 16, 18],
            "slow": [21, 26, 30, 35, 40],
            "signal": [5, 7, 9, 11],
        },
    },
    "SMC_OrderBlock": {
        "fn": _eval_smc_entry,
        "axes": {
            "sl_buf": [15, 30, 45, 60, 80, 100],
            "fib_tol": [50, 100, 150, 200, 300],
            "scan": [50, 60, 70, 80, 100],
        },
    },
    "ADX_Trend": {
        "fn": _eval_adx_entry,
        "axes": {
            "period": [7, 10, 14, 18, 21, 28],
            "threshold": [15, 20, 22.5, 25, 27.5, 30, 35],
        },
    },
    "Asian_Breakout": {
        "fn": _eval_asian_entry,
        "axes": {
            "start_hour": [0, 1, 2],
            "end_hour": [7, 8, 9],
            "window_hours": [3, 4, 5],
            "min_body": [0.4, 0.5, 0.6, 0.7],
            "sl_buf": [30, 50, 80, 120, 200],
        },
    },
    "Fractal_Breakout": {
        "fn": _eval_fractal_entry,
        "axes": {
            "buffer_pts": [10, 20, 30, 50, 80],
            "sl_buf": [10, 20, 40, 60, 100],
        },
    },
}

# Quick mode: take first 2 of each axis (~50 entry combos per strategy
# × ~96 exit variants = ~5000 total per strategy. Tiny but validates.)
GRIDS_QUICK = {s: {"fn": d["fn"],
                    "axes": {k: (v[:2] if len(v) > 2 else v) for k, v in d["axes"].items()}}
                for s, d in GRIDS_FULL.items()}


def _flatten_results(parallel_results):
    """parallel_results is a list[list[dict]]; flatten."""
    out = []
    for sub in parallel_results:
        if isinstance(sub, list):
            out.extend(sub)
        elif sub is not None:
            out.append(sub)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--n_jobs", type=int, default=-2)
    args = ap.parse_args()
    if not (args.quick or args.full):
        args.quick = True

    d = ROOT / "data"
    data = {
        "M15": pd.read_parquet(d / "XAUUSD_M15.parquet"),
        "H1": pd.read_parquet(d / "XAUUSD_H1.parquet"),
        "H4": pd.read_parquet(d / "XAUUSD_H4.parquet"),
    }
    reg = regime(data["M15"])

    grids = GRIDS_QUICK if args.quick else GRIDS_FULL
    label = "quick" if args.quick else "full"
    print(f"Mode: {label}")

    all_results = []
    for strategy, conf in grids.items():
        fn = conf["fn"]
        axes = conf["axes"]
        keys = list(axes.keys())
        entry_combos = list(itertools.product(*[axes[k] for k in keys]))
        # Estimate total evals (entry × exit) -- exit count varies per strategy
        print(f"\n=== {strategy}: {len(entry_combos)} entry combos ===")
        t0 = time.time()
        results = Parallel(n_jobs=args.n_jobs, verbose=5)(
            delayed(fn)(c, data, reg) for c in entry_combos
        )
        rows = _flatten_results(results)
        elapsed = time.time() - t0
        print(f"  {len(rows)} evals in {elapsed:.1f}s "
              f"({elapsed/max(len(rows),1)*1000:.1f} ms/eval)")
        if rows:
            df = pd.DataFrame(rows)
            all_results.append(df)
            top5 = df.sort_values("score", ascending=False).head(5)
            cols = [c for c in ["pf", "net_pnl", "win_rate", "max_dd_pct",
                                  "sharpe", "trades", "score", "mtf", "sl_mult"]
                    if c in top5.columns]
            print("  Top 5 by score:")
            print(top5[cols].to_string(index=False))

    if all_results:
        big = pd.concat(all_results, ignore_index=True)
        out = d / f"layer1_fine_grid_{label}.csv"
        big.to_csv(out, index=False)
        print(f"\nSaved {out.relative_to(ROOT)} ({len(big):,} rows)")

        top50_list = []
        for s in big["strategy"].unique():
            sub = big[big["strategy"] == s].sort_values("score", ascending=False).head(50)
            top50_list.append(sub)
        pd.concat(top50_list).to_csv(d / f"layer1_top50_{label}.csv", index=False)
        print(f"Saved layer1_top50_{label}.csv (top 50 per strategy)")


if __name__ == "__main__":
    main()
