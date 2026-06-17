"""Audit v6 Layer 2: top-50-per-strategy × manager-parameter grid.

Two-pass smart funnel:
  Pass 1: 1 strategy variant × all manager configs (find top managers)
  Pass 2: top 100 managers × top 10 strategy variants (refine)
"""
from __future__ import annotations

import argparse
import ast
import itertools
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import pandas as pd
from joblib import Parallel, delayed

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.filters import apply_filters
from quantumking.indicators import atr
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import (
    adx_trend, asian_breakout, fractal_breakout, ma_trend, macd_momentum, smc_orderblock,
)


# ============================================================
# Manager parameter grid
# ============================================================

TIME_PAUSE_OPTIONS = {
    "none": (),
    "23-00": (23, 0),
    "22-01": (22, 23, 0, 1),
    "23-01": (23, 0, 1),
    "00-02": (0, 1, 2),
    "22-00": (22, 23, 0),
    "21-00": (21, 22, 23, 0),
    "20-01": (20, 21, 22, 23, 0, 1),
    "news_block_13_14": (13, 14),
}

MGR_GRID_FULL = {
    "time_pause": list(TIME_PAUSE_OPTIONS.keys()),
    "regime_mult": [0.0, 1.0, 1.1, 1.2, 1.25, 1.3],   # 0.0 = OFF
    "cap": [2, 3, 4, 5, 6],
    "spread_cap": [200, 400, 700, 1200],
    "risk_pct": [0.005, 0.01, 0.015, 0.02, 0.03],
    "dd_thresh": [0.15, 0.20, 0.25, 0.30, 0.40],
}

MGR_GRID_QUICK = {k: v[:2] for k, v in MGR_GRID_FULL.items()}


# ============================================================
# Build strategy spec from row of layer1 top-50 CSV
# ============================================================

def _parse_trail(s: str) -> tuple:
    try:
        return tuple(ast.literal_eval(s))
    except Exception:
        return (1000, 1000, 200)


def _build_spec(name: str, row: dict, data: dict, weight: float) -> StratSpec:
    m15, h1, h4 = data["M15"], data["H1"], data["H4"]
    sigs = None
    trail = (1000, 1000, 200)

    if name == "MA_Trend":
        p = ma_trend.MAParams(
            fast_ema=int(row["fast_ema"]), slow_ema=int(row["slow_ema"]),
            kdj_period=int(row["kdj_p"]), kdj_d=int(row["kdj_d"]),
            fibo_bottom=float(row["fibo_b"]),
        )
        sigs = ma_trend.generate_signals(m15, h4, p)
        trail = (1400, 1400, 100)
    elif name == "MACD_Momentum":
        p = macd_momentum.MacdParams(fast=int(row["fast"]), slow=int(row["slow"]),
                                          signal=int(row["sig"]))
        sigs = macd_momentum.generate_signals(m15, h1, h4, p)
        mtf = str(row.get("mtf", "none"))
        if mtf == "H1":
            sigs = apply_filters(sigs, df_h1=h1)
        elif mtf == "H4":
            sigs = apply_filters(sigs, df_h4=h4)
        elif mtf == "H1+H4":
            sigs = apply_filters(sigs, df_h1=h1, df_h4=h4)
        sigs["sl_pts"] = sigs["sl_pts"] * float(row.get("sl_mult", 1.0))
        trail = _parse_trail(row.get("trail", "(1000,1000,200)"))
    elif name == "SMC_OrderBlock":
        p = smc_orderblock.SmcParams(sl_buffer_pts=int(row["sl_buf"]),
                                          fib_tolerance_pts=int(row["fib_tol"]),
                                          scan_window=int(row["scan"]))
        sigs = smc_orderblock.generate_signals(m15, p)
        mtf = str(row.get("mtf", "none"))
        if mtf == "H1": sigs = apply_filters(sigs, df_h1=h1)
        elif mtf == "H4": sigs = apply_filters(sigs, df_h4=h4)
        elif mtf == "H1+H4": sigs = apply_filters(sigs, df_h1=h1, df_h4=h4)
        sigs["sl_pts"] = sigs["sl_pts"] * float(row.get("sl_mult", 1.0))
        trail = _parse_trail(row.get("trail", "(750,1500,500)"))
    elif name == "ADX_Trend":
        p = adx_trend.AdxParams(period=int(row["period"]), threshold=float(row["threshold"]))
        sigs = adx_trend.generate_signals(m15, p)
        mtf = str(row.get("mtf", "none"))
        if mtf == "H1": sigs = apply_filters(sigs, df_h1=h1)
        elif mtf == "H4": sigs = apply_filters(sigs, df_h4=h4)
        elif mtf == "H1+H4": sigs = apply_filters(sigs, df_h1=h1, df_h4=h4)
        sigs["sl_pts"] = sigs["sl_pts"] * float(row.get("sl_mult", 1.0))
        trail = _parse_trail(row.get("trail", "(1250,750,300)"))
    elif name == "Asian_Breakout":
        p = asian_breakout.AsianParams(
            start_hour=int(row["start_hour"]), end_hour=int(row["end_hour"]),
            breakout_window_hours=int(row["window_hours"]),
            min_body_ratio=float(row["min_body"]), sl_buffer_pts=int(row["sl_buf"]),
        )
        sigs = asian_breakout.generate_signals(m15, p)
        trail = _parse_trail(row.get("trail", "(400,100,40)"))
    elif name == "Fractal_Breakout":
        p = fractal_breakout.FractalParams(buffer_pts=int(row["buf_pts"]),
                                                 sl_buffer_pts=int(row["sl_buf"]))
        sigs = fractal_breakout.generate_signals(m15, p)
        mtf = str(row.get("mtf", "none"))
        if mtf == "H1": sigs = apply_filters(sigs, df_h1=h1)
        elif mtf == "H4": sigs = apply_filters(sigs, df_h4=h4)
        elif mtf == "H1+H4": sigs = apply_filters(sigs, df_h1=h1, df_h4=h4)
        sigs["sl_pts"] = sigs["sl_pts"] * float(row.get("sl_mult", 1.0))
        trail = _parse_trail(row.get("trail", "(1400,1400,300)"))
    return StratSpec(name=name, signals=sigs, trail=TrailParams(*trail),
                       kind="trend", weight=weight)


# ============================================================
# Manager-config evaluator
# ============================================================

def _eval_manager_config(mgr_params: dict, specs: list[StratSpec],
                          data: dict) -> dict:
    pause = TIME_PAUSE_OPTIONS[mgr_params["time_pause"]]
    reg_mult = mgr_params["regime_mult"]
    if reg_mult == 0.0:
        reg = None
    else:
        a_fast = atr(data["M15"], 7)
        a_slow = atr(data["M15"], 50)
        reg = a_fast > a_slow * reg_mult
    cfg = PortfolioConfig(
        initial_equity=10_000,
        max_positions=int(mgr_params["cap"]),
        spread_cap_pts=int(mgr_params["spread_cap"]),
        danger_hours=pause,
        drawdown_kill_pct=float(mgr_params["dd_thresh"]),
        spread_pts=17, slippage_pts=5,
    )
    # Apply risk_pct via weight scaling
    rp_scale = mgr_params["risk_pct"] / 0.02
    specs_r = [StratSpec(s.name, s.signals, s.trail, s.kind, s.weight * rp_scale)
               for s in specs]
    res = run_portfolio(data["M15"], specs_r, cfg, regime=reg)
    return {
        **mgr_params,
        "trades": res["trades"],
        "pf": round(res["pf"], 3),
        "net_pnl": round(res["net_pnl"], 0),
        "win_rate": round(res["win_rate"] * 100, 1),
        "max_dd_pct": round(res["max_dd_pct"] * 100, 2),
        "sharpe": round(res["sharpe"], 2),
    }


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

    label = "quick" if args.quick else "full"
    top50_path = d / f"layer1_top50_{label}.csv"
    if not top50_path.exists():
        print(f"ERROR: {top50_path} does not exist. Run 21_layer1_fine_grid.py first.")
        return

    layer1 = pd.read_csv(top50_path)
    print(f"Loaded {len(layer1)} top-50 rows across {layer1['strategy'].nunique()} strategies")

    # Pass 1: top-1 per strategy → manager grid
    portfolios = []
    for sname in layer1["strategy"].unique():
        top1 = layer1[layer1["strategy"] == sname].iloc[0].to_dict()
        portfolios.append(top1)

    # Build specs (weights from v3.20: MA 1.0 / SMC 0.7 / MACD 0.3 / ADX 0.3, others 0.3)
    weights_map = {"MA_Trend": 1.0, "SMC_OrderBlock": 0.7, "MACD_Momentum": 0.3,
                    "ADX_Trend": 0.3, "Asian_Breakout": 0.3, "Fractal_Breakout": 0.3}
    specs_top1 = [_build_spec(p["strategy"], p, data,
                                  weights_map.get(p["strategy"], 0.3))
                    for p in portfolios]

    mgr_grid = MGR_GRID_QUICK if args.quick else MGR_GRID_FULL
    mgr_keys = list(mgr_grid.keys())
    combos = list(itertools.product(*[mgr_grid[k] for k in mgr_keys]))
    print(f"Pass 1: {len(combos)} manager configs × top-1 strategy variants")

    t0 = time.time()
    rows = Parallel(n_jobs=args.n_jobs, verbose=5)(
        delayed(_eval_manager_config)(dict(zip(mgr_keys, c)), specs_top1, data)
        for c in combos
    )
    print(f"Pass 1 done in {time.time()-t0:.1f}s")

    df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    df.to_csv(d / f"layer2_pass1_{label}.csv", index=False)
    print(f"Saved layer2_pass1_{label}.csv")
    print("\nTop 10 manager configs by Sharpe:")
    print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
