"""Test grid-feature variants: spacing, breakeven, max layers.

The user specifically asked what variants of the grid feature work best.
We sweep grid_spacing (500-2000), breakeven_pts (100-300), max_grids (3-15)
on the 3 grid strategies.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.grid_backtest import GridConfig, run_grid
from quantumking.regime import regime
from quantumking.strategies import bands_extreme, pivot_divergence, vwap_reversion


def main():
    m15 = pd.read_parquet(ROOT / "data" / "XAUUSD_M15.parquet")
    d1 = pd.read_parquet(ROOT / "data" / "XAUUSD_D1.parquet")
    reg = regime(m15)

    signals_set = [
        ("Bands_Extreme", bands_extreme.generate_signals(m15)),
        ("Pivot_Divergence", pivot_divergence.generate_signals(m15, d1)),
        ("VWAP_Reversion", vwap_reversion.generate_signals(m15)),
    ]

    rows = []
    for name, sigs in signals_set:
        for spacing in [500, 750, 1000, 1500, 2000]:
            for be in [100, 150, 200, 300]:
                for max_g in [5, 10, 15]:
                    cfg = GridConfig(
                        grid_spacing_pts=spacing,
                        breakeven_pts=be,
                        max_grids=max_g,
                    )
                    res = run_grid(m15, sigs, cfg, regime=reg, strategy_kind="reversion")
                    s = res["stats"]
                    rows.append({
                        "strategy": name,
                        "spacing": spacing,
                        "breakeven": be,
                        "max_grids": max_g,
                        "trades": s.get("trades", 0),
                        "pf": s.get("pf", 0),
                        "net_pnl": s.get("net_pnl", 0),
                        "max_dd": s.get("max_dd_pct", 0),
                        "kill_events": s.get("kill_events", 0),
                        "avg_layers": s.get("avg_layers", 0),
                    })
        print(f"  done: {name}")

    df = pd.DataFrame(rows)
    df["pf"] = df["pf"].replace([float("inf"), -float("inf")], 0).round(3)
    df["net_pnl"] = df["net_pnl"].round(0)
    df["max_dd"] = (df["max_dd"] * 100).round(2)

    # Best per strategy
    print("\n=== Best grid variant per strategy ===")
    for name in df["strategy"].unique():
        sub = df[df["strategy"] == name]
        # rank by net_pnl since pf=inf is meaningless when only wins
        best = sub.sort_values("net_pnl", ascending=False).head(5)
        print(f"\n{name}  (top 5 by net_pnl):")
        print(best.to_string(index=False))

    df.to_csv(ROOT / "data" / "grid_variants.csv", index=False)
    print(f"\nSaved data/grid_variants.csv")


if __name__ == "__main__":
    main()
