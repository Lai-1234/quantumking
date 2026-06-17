"""Audit v6 Layer 3 — PARALLEL edition.

Runs top portfolio combinations in parallel using joblib.
Reduced scope vs original: top 10 managers × top 3 variants per strategy
= 10 * 3^5 = 2,430 portfolios (was 18,750 sequential).
With 5 strategies (4 actives + Pivot_Divergence_noGrid from layer1b).

Estimated runtime on 15 cores: ~15-20 min.
"""
from __future__ import annotations

import argparse
import itertools
import sys
import warnings
from pathlib import Path

import pandas as pd
from joblib import Parallel, delayed

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.filters import apply_filters
from quantumking.indicators import atr
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.risk import TrailParams
from quantumking.strategies import pivot_divergence

import importlib.util
_spec22 = importlib.util.spec_from_file_location(
    "layer2", ROOT / "scripts" / "22_layer2_strategy_x_manager.py"
)
_mod22 = importlib.util.module_from_spec(_spec22)
_spec22.loader.exec_module(_mod22)
_build_spec_22 = _mod22._build_spec
TIME_PAUSE_OPTIONS = _mod22.TIME_PAUSE_OPTIONS


def _build_pivot_nogrid_spec(row: dict, data: dict, weight: float) -> StratSpec:
    """Builder for Pivot_Divergence_noGrid using layer1b columns:
    rsi_p, touch, sl_mult, mtf, exit_mode, be_pts."""
    p = pivot_divergence.PivotParams(
        rsi_period=int(row["rsi_p"]),
        touch_buffer_pts=int(row["touch"]),
        sl_pts=1500,
    )
    sigs = pivot_divergence.generate_signals(data["M15"], data["D1"], p)
    mtf = str(row.get("mtf", "none"))
    if mtf == "H1":
        sigs = apply_filters(sigs, df_h1=data["H1"])
    elif mtf == "H4":
        sigs = apply_filters(sigs, df_h4=data["H4"])
    elif mtf == "H1+H4":
        sigs = apply_filters(sigs, df_h1=data["H1"], df_h4=data["H4"])
    sigs["sl_pts"] = sigs["sl_pts"] * float(row.get("sl_mult", 1.0))
    # Pivot_noGrid winners used sl_only mode — trail is irrelevant but engine needs it.
    return StratSpec(
        name="Pivot_Divergence", signals=sigs,
        trail=TrailParams(1400, 1400, 100),
        kind="reversion", weight=weight,
    )


def _safe_build_spec(sname: str, row: dict, data: dict, weight: float) -> StratSpec:
    """Dispatch to the right builder, handling Pivot_Divergence_noGrid."""
    if sname == "Pivot_Divergence_noGrid":
        return _build_pivot_nogrid_spec(row, data, weight)
    return _build_spec_22(sname, row, data, weight)


def _eval_portfolio(args):
    """Run one portfolio config."""
    mgr_row, variant_indices, variant_pool_dict, data_dict, weights_map = args
    pause = TIME_PAUSE_OPTIONS[mgr_row["time_pause"]]
    reg_mult = mgr_row["regime_mult"]
    if reg_mult == 0:
        reg = None
    else:
        reg = atr(data_dict["M15"], 7) > atr(data_dict["M15"], 50) * reg_mult
    cfg = PortfolioConfig(
        initial_equity=10_000, max_positions=int(mgr_row["cap"]),
        spread_cap_pts=int(mgr_row["spread_cap"]),
        danger_hours=pause, drawdown_kill_pct=float(mgr_row["dd_thresh"]),
        spread_pts=17, slippage_pts=5,
    )
    rp_scale = mgr_row["risk_pct"] / 0.02
    specs = []
    for i, sname in enumerate(["MA_Trend", "SMC_OrderBlock", "MACD_Momentum",
                                "ADX_Trend", "Pivot_Divergence_noGrid"]):
        pool = variant_pool_dict.get(sname, [])
        if not pool:
            continue
        idx = variant_indices[i] if i < len(variant_indices) else 0
        if idx >= len(pool):
            idx = 0
        try:
            spec = _safe_build_spec(sname, pool[idx], data_dict,
                                       weights_map.get(sname, 0.3) * rp_scale)
            if spec is not None and spec.signals is not None:
                specs.append(spec)
        except Exception:
            continue
    if len(specs) < 2:
        return None
    res = run_portfolio(data_dict["M15"], specs, cfg, regime=reg)
    return {
        "mgr_time_pause": mgr_row["time_pause"],
        "mgr_regime_mult": reg_mult,
        "mgr_cap": int(mgr_row["cap"]),
        "mgr_risk_pct": float(mgr_row["risk_pct"]),
        "mgr_dd_thresh": float(mgr_row["dd_thresh"]),
        "variants": str(variant_indices),
        "n_strats": len(specs),
        "trades": res["trades"],
        "pf": round(res["pf"], 3),
        "net_pnl": round(res["net_pnl"], 0),
        "max_dd_pct": round(res["max_dd_pct"] * 100, 2),
        "sharpe": round(res["sharpe"], 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top_mgr", type=int, default=10, help="Top N manager configs")
    ap.add_argument("--top_var", type=int, default=3, help="Top N variants per strategy")
    ap.add_argument("--n_jobs", type=int, default=-2)
    args = ap.parse_args()

    d = ROOT / "data"
    layer1 = pd.read_csv(d / "layer1_top50_full.csv")

    # Try to also include layer1b's Pivot_Divergence_noGrid
    layer1b_path = d / "layer1b_top50_full.csv"
    if layer1b_path.exists():
        layer1b = pd.read_csv(layer1b_path)
        # Filter to Pivot only
        pivot_layer1b = layer1b[layer1b["strategy"] == "Pivot_Divergence_noGrid"].head(args.top_var)
        layer1_combined = pd.concat([layer1, pivot_layer1b], ignore_index=True)
    else:
        layer1_combined = layer1

    layer2 = pd.read_csv(d / "layer2_pass1_full.csv").sort_values("sharpe", ascending=False)
    print(f"Layer1 variants: {len(layer1_combined)} | Layer2 mgr configs: {len(layer2)}")

    data = {
        "M15": pd.read_parquet(d / "XAUUSD_M15.parquet"),
        "H1": pd.read_parquet(d / "XAUUSD_H1.parquet"),
        "H4": pd.read_parquet(d / "XAUUSD_H4.parquet"),
        "D1": pd.read_parquet(d / "XAUUSD_D1.parquet"),
    }

    weights_map = {"MA_Trend": 1.0, "SMC_OrderBlock": 0.7, "MACD_Momentum": 0.3,
                    "ADX_Trend": 0.3, "Asian_Breakout": 0.3, "Fractal_Breakout": 0.3,
                    "Pivot_Divergence_noGrid": 0.4}

    # Build variant pool
    variant_pool = {}
    for sname in ["MA_Trend", "SMC_OrderBlock", "MACD_Momentum", "ADX_Trend",
                   "Pivot_Divergence_noGrid"]:
        sub = layer1_combined[layer1_combined["strategy"] == sname]\
            .sort_values("score", ascending=False).head(args.top_var)
        variant_pool[sname] = [row.to_dict() for _, row in sub.iterrows()]
        print(f"  {sname}: {len(variant_pool[sname])} variants in pool")

    # Build all jobs: top_mgr × variant index product
    top_mgrs = layer2.head(args.top_mgr).to_dict("records")
    n_strats = 5
    var_combos = list(itertools.product(*[range(args.top_var) for _ in range(n_strats)]))
    print(f"Total portfolios: {len(top_mgrs)} mgrs × {len(var_combos)} variant combos "
          f"= {len(top_mgrs) * len(var_combos)}")

    jobs = []
    for mgr in top_mgrs:
        for vidx in var_combos:
            jobs.append((mgr, vidx, variant_pool, data, weights_map))

    print(f"Running {len(jobs)} portfolio backtests on {args.n_jobs} cores...")
    rows = Parallel(n_jobs=args.n_jobs, verbose=5)(
        delayed(_eval_portfolio)(j) for j in jobs
    )
    rows = [r for r in rows if r is not None]

    df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    df.to_csv(d / "layer3_final_full.csv", index=False)
    print(f"\nSaved layer3_final_full.csv ({len(df)} rows)")
    print("\nTop 20 portfolios by Sharpe:")
    print(df.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
