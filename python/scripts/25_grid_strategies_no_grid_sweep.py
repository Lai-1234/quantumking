"""Audit v6 Layer 1b: fine grid on the 3 grid strategies with NO-GRID exits.

The 3 strategies (Bands_Extreme, Pivot_Divergence, VWAP_Reversion) were
originally designed with grid escape. v3 already showed grid kills the
account. v6 audits them in NO-GRID mode (sl_trail / sl_only / be_only).

Output: appends top-50 rows to layer1_top50_full.csv so Layer 2 sees them.
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

from quantumking.filters import apply_filters
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.variant_engine import VariantConfig, run_variant
from quantumking.strategies import bands_extreme, pivot_divergence, vwap_reversion


def _composite_score(s: dict, min_trades: int = 30) -> float:
    pf = s["pf"]
    t = s["trades"]
    dd = abs(s["max_dd_pct"])
    if pf <= 0 or t < min_trades:
        return -1.0
    conf = math.sqrt(min(t, 200) / 200)
    dd_penalty = 1.0 - min(dd, 0.4)
    return pf * conf * dd_penalty


GRID_BANDS = {
    "bb_period": [10, 20, 30, 50],
    "bb_dev": [1.5, 2.0, 2.5, 3.0],
    "rsi_ob": [70, 75, 80],
    "shadow_mult": [1.0, 1.5, 2.0],
    "mtf": ["none", "H1", "H4", "H1+H4"],
    "exit_mode": ["sl_trail", "sl_only", "be_only"],
    "be_pts": [150, 300],
}

GRID_PIVOT = {
    "rsi_period": [10, 14, 21],
    "touch_buffer_pts": [50, 150, 300],
    "mtf": ["none", "H1", "H4", "H1+H4"],
    "exit_mode": ["sl_trail", "sl_only", "be_only"],
    "sl_mult": [0.5, 1.0, 1.5],
    "be_pts": [150, 300],
}

GRID_VWAP = {
    "sigma_mult": [1.5, 2.0, 2.5, 3.0, 3.5],
    "shadow_mult": [1.0, 1.5, 2.0],
    "warmup_bars": [4, 8, 16],
    "mtf": ["none", "H1", "H4", "H1+H4"],
    "exit_mode": ["sl_trail", "sl_only", "be_only"],
    "be_pts": [100, 150, 200, 300],
}

QUICK_BANDS = {k: v[:2] for k, v in GRID_BANDS.items()}
QUICK_PIVOT = {k: v[:2] for k, v in GRID_PIVOT.items()}
QUICK_VWAP = {k: v[:2] for k, v in GRID_VWAP.items()}


def _eval_bands(params, data, reg):
    bb_p, bb_d, rsi_ob, shadow, mtf, exit_mode, be_pts = params
    p = bands_extreme.BandsParams(
        bb_period=bb_p, bb_dev=bb_d, rsi_period=14,
        rsi_ob=rsi_ob, rsi_os=100 - rsi_ob, shadow_mult=shadow,
        sl_pts=1500,
    )
    sigs = bands_extreme.generate_signals(data["M15"], p)
    if mtf == "H1": sigs = apply_filters(sigs, df_h1=data["H1"])
    elif mtf == "H4": sigs = apply_filters(sigs, df_h4=data["H4"])
    elif mtf == "H1+H4": sigs = apply_filters(sigs, df_h1=data["H1"], df_h4=data["H4"])
    cfg = VariantConfig(exit_mode=exit_mode, breakeven_pts=be_pts,
                          trail=TrailParams(1000, 1000, 200), use_regime=True)
    s = run_variant(data["M15"], sigs, cfg, regime=reg, strategy_kind="reversion")
    out = {"strategy": "Bands_Extreme_noGrid", "bb_p": bb_p, "bb_d": bb_d,
           "rsi_ob": rsi_ob, "shadow": shadow, "mtf": mtf,
           "exit_mode": exit_mode, "be_pts": be_pts,
           "pf": s["pf"], "net_pnl": s["net_pnl"], "win_rate": s["win_rate"],
           "max_dd_pct": s["max_dd_pct"], "sharpe": s["sharpe"], "trades": s["trades"]}
    out["score"] = _composite_score(out)
    return out


def _eval_pivot(params, data, reg):
    rsi_p, touch, mtf, exit_mode, sl_mult, be_pts = params
    p = pivot_divergence.PivotParams(rsi_period=rsi_p, touch_buffer_pts=touch, sl_pts=1500)
    sigs = pivot_divergence.generate_signals(data["M15"], data["D1"], p)
    if mtf == "H1": sigs = apply_filters(sigs, df_h1=data["H1"])
    elif mtf == "H4": sigs = apply_filters(sigs, df_h4=data["H4"])
    elif mtf == "H1+H4": sigs = apply_filters(sigs, df_h1=data["H1"], df_h4=data["H4"])
    sigs["sl_pts"] = sigs["sl_pts"] * sl_mult
    cfg = VariantConfig(exit_mode=exit_mode, breakeven_pts=be_pts,
                          trail=TrailParams(1000, 1000, 200), use_regime=True)
    s = run_variant(data["M15"], sigs, cfg, regime=reg, strategy_kind="reversion")
    out = {"strategy": "Pivot_Divergence_noGrid", "rsi_p": rsi_p, "touch": touch,
           "mtf": mtf, "exit_mode": exit_mode, "sl_mult": sl_mult, "be_pts": be_pts,
           "pf": s["pf"], "net_pnl": s["net_pnl"], "win_rate": s["win_rate"],
           "max_dd_pct": s["max_dd_pct"], "sharpe": s["sharpe"], "trades": s["trades"]}
    out["score"] = _composite_score(out)
    return out


def _eval_vwap(params, data, reg):
    sigma, shadow, warmup, mtf, exit_mode, be_pts = params
    p = vwap_reversion.VwapParams(sigma_mult=sigma, shadow_mult=shadow,
                                       warmup_bars=warmup, sl_pts=1500)
    sigs = vwap_reversion.generate_signals(data["M15"], p)
    if mtf == "H1": sigs = apply_filters(sigs, df_h1=data["H1"])
    elif mtf == "H4": sigs = apply_filters(sigs, df_h4=data["H4"])
    elif mtf == "H1+H4": sigs = apply_filters(sigs, df_h1=data["H1"], df_h4=data["H4"])
    cfg = VariantConfig(exit_mode=exit_mode, breakeven_pts=be_pts,
                          trail=TrailParams(1000, 1000, 200), use_regime=True)
    s = run_variant(data["M15"], sigs, cfg, regime=reg, strategy_kind="reversion")
    out = {"strategy": "VWAP_Reversion_noGrid", "sigma": sigma, "shadow": shadow,
           "warmup": warmup, "mtf": mtf, "exit_mode": exit_mode, "be_pts": be_pts,
           "pf": s["pf"], "net_pnl": s["net_pnl"], "win_rate": s["win_rate"],
           "max_dd_pct": s["max_dd_pct"], "sharpe": s["sharpe"], "trades": s["trades"]}
    out["score"] = _composite_score(out)
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
        "D1": pd.read_parquet(d / "XAUUSD_D1.parquet"),
    }
    reg = regime(data["M15"])

    label = "quick" if args.quick else "full"
    grids = {"Bands": (GRID_BANDS if args.full else QUICK_BANDS, _eval_bands),
             "Pivot": (GRID_PIVOT if args.full else QUICK_PIVOT, _eval_pivot),
             "VWAP":  (GRID_VWAP if args.full else QUICK_VWAP, _eval_vwap)}

    all_results = []
    for sname, (axes, evaluator) in grids.items():
        combos = list(itertools.product(*[axes[k] for k in axes]))
        print(f"\n=== {sname} no-grid grid: {len(combos)} combos ===")
        t0 = time.time()
        rows = Parallel(n_jobs=args.n_jobs, verbose=5)(
            delayed(evaluator)(c, data, reg) for c in combos
        )
        rows = [r for r in rows if r is not None]
        elapsed = time.time() - t0
        print(f"  {len(rows)} valid in {elapsed:.1f}s ({elapsed/max(len(rows),1)*1000:.0f} ms/run)")
        all_results.append(pd.DataFrame(rows))

    big = pd.concat(all_results, ignore_index=True)
    big.to_csv(d / f"layer1b_grid_strategies_noGrid_{label}.csv", index=False)

    # Top 50 per strategy
    top50_list = []
    for s in big["strategy"].unique():
        sub = big[big["strategy"] == s].sort_values("score", ascending=False).head(50)
        top50_list.append(sub)
    top50_df = pd.concat(top50_list)
    top50_path = d / f"layer1b_top50_{label}.csv"
    top50_df.to_csv(top50_path, index=False)

    # Print top 5 per strategy
    print("\n=== TOP 5 PER STRATEGY (no-grid mode) ===")
    for s in big["strategy"].unique():
        sub = big[big["strategy"] == s].sort_values("score", ascending=False).head(5)
        print(f"\n{s}:")
        cols = ["exit_mode", "mtf", "pf", "net_pnl", "win_rate", "max_dd_pct", "trades", "score"]
        cols = [c for c in cols if c in sub.columns]
        print(sub[cols].to_string(index=False))

    print(f"\nSaved {top50_path.relative_to(ROOT)} ({len(top50_df)} rows)")
    print(f"Append-merge instructions: cat this CSV into layer1_top50_full.csv after Layer 1 finishes")


if __name__ == "__main__":
    main()
