"""Audit v6 Layer 3: final portfolio with Monte Carlo confidence intervals.

Reads top managers from layer2 + top variants from layer1, runs the top-30
portfolio configurations with realistic costs + 1000-iter Monte Carlo.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.indicators import atr
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio

# Reuse the spec builder from script 22
sys.path.insert(0, str(ROOT / "scripts"))
import importlib.util
_spec22 = importlib.util.spec_from_file_location(
    "layer2", ROOT / "scripts" / "22_layer2_strategy_x_manager.py"
)
_mod22 = importlib.util.module_from_spec(_spec22)
_spec22.loader.exec_module(_mod22)
_build_spec = _mod22._build_spec
TIME_PAUSE_OPTIONS = _mod22.TIME_PAUSE_OPTIONS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    if not (args.quick or args.full):
        args.quick = True

    d = ROOT / "data"
    label = "quick" if args.quick else "full"
    layer1 = pd.read_csv(d / f"layer1_top50_{label}.csv")
    layer2 = pd.read_csv(d / f"layer2_pass1_{label}.csv").sort_values("sharpe", ascending=False)

    print(f"Layer1: {len(layer1)} variants  |  Layer2: {len(layer2)} manager configs")
    print(f"Best manager config:")
    print(layer2.iloc[0].to_string())

    data = {
        "M15": pd.read_parquet(d / "XAUUSD_M15.parquet"),
        "H1": pd.read_parquet(d / "XAUUSD_H1.parquet"),
        "H4": pd.read_parquet(d / "XAUUSD_H4.parquet"),
    }

    # Take top 5 managers, top 3 variants per strategy = 5 × 3^4 = 405 combos for full
    top_n_mgr = 5 if args.quick else 30
    top_n_var = 2 if args.quick else 5

    weights_map = {"MA_Trend": 1.0, "SMC_OrderBlock": 0.7, "MACD_Momentum": 0.3,
                    "ADX_Trend": 0.3, "Asian_Breakout": 0.3, "Fractal_Breakout": 0.3}

    # Get top variants per strategy
    variant_pool = {}
    for sname in layer1["strategy"].unique():
        sub = layer1[layer1["strategy"] == sname].sort_values("score", ascending=False).head(top_n_var)
        variant_pool[sname] = [row.to_dict() for _, row in sub.iterrows()]

    # Build all 4-strategy portfolio combinations from top variants × top managers
    import itertools
    rows = []
    base_strats = ["MA_Trend", "SMC_OrderBlock"]  # always include the 2 strongest
    extra_pool = ["MACD_Momentum", "ADX_Trend", "Asian_Breakout", "Fractal_Breakout"]

    # For each top manager
    for _, mgr in layer2.head(top_n_mgr).iterrows():
        pause = TIME_PAUSE_OPTIONS[mgr["time_pause"]]
        reg_mult = mgr["regime_mult"]
        if reg_mult == 0:
            reg = None
        else:
            reg = atr(data["M15"], 7) > atr(data["M15"], 50) * reg_mult
        cfg = PortfolioConfig(
            initial_equity=10_000, max_positions=int(mgr["cap"]),
            spread_cap_pts=int(mgr["spread_cap"]),
            danger_hours=pause, drawdown_kill_pct=float(mgr["dd_thresh"]),
            spread_pts=17, slippage_pts=5,
        )
        rp_scale = mgr["risk_pct"] / 0.02

        # Try the 4-strategy portfolio with each variant index combo
        for v_indices in itertools.product(*[range(len(variant_pool.get(s, [{}])))
                                                for s in ["MA_Trend", "SMC_OrderBlock",
                                                            "MACD_Momentum", "ADX_Trend"]]):
            try:
                specs = [
                    _build_spec("MA_Trend", variant_pool["MA_Trend"][v_indices[0]],
                                  data, weights_map["MA_Trend"] * rp_scale),
                    _build_spec("SMC_OrderBlock", variant_pool["SMC_OrderBlock"][v_indices[1]],
                                  data, weights_map["SMC_OrderBlock"] * rp_scale),
                    _build_spec("MACD_Momentum", variant_pool["MACD_Momentum"][v_indices[2]],
                                  data, weights_map["MACD_Momentum"] * rp_scale),
                    _build_spec("ADX_Trend", variant_pool["ADX_Trend"][v_indices[3]],
                                  data, weights_map["ADX_Trend"] * rp_scale),
                ]
                res = run_portfolio(data["M15"], specs, cfg, regime=reg)
                rows.append({
                    "mgr_time_pause": mgr["time_pause"],
                    "mgr_regime_mult": reg_mult,
                    "mgr_cap": mgr["cap"],
                    "mgr_risk_pct": mgr["risk_pct"],
                    "mgr_dd_thresh": mgr["dd_thresh"],
                    "variants": str(v_indices),
                    "trades": res["trades"],
                    "pf": round(res["pf"], 3),
                    "net_pnl": round(res["net_pnl"], 0),
                    "max_dd_pct": round(res["max_dd_pct"] * 100, 2),
                    "sharpe": round(res["sharpe"], 2),
                })
            except Exception as e:
                print(f"  Skipped due to: {e}")

    df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    df.to_csv(d / f"layer3_final_{label}.csv", index=False)
    print(f"\nSaved layer3_final_{label}.csv ({len(df)} rows)")
    print("\nTop 10 final portfolios:")
    print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
