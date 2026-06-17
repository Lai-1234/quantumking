"""Re-run the 3 grid strategies with the grid engine."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.grid_backtest import GridConfig, run_grid
from quantumking.regime import regime
from quantumking.strategies import bands_extreme, pivot_divergence, vwap_reversion


def main() -> None:
    m15 = pd.read_parquet(ROOT / "data" / "XAUUSD_M15.parquet")
    d1 = pd.read_parquet(ROOT / "data" / "XAUUSD_D1.parquet")
    reg = regime(m15)

    results = []
    cfg = GridConfig()

    for name, sigs in [
        ("Bands_Extreme_GRID", bands_extreme.generate_signals(m15)),
        ("Pivot_Divergence_GRID", pivot_divergence.generate_signals(m15, d1)),
        ("VWAP_Reversion_GRID", vwap_reversion.generate_signals(m15)),
    ]:
        print(f"Running {name}...")
        res = run_grid(m15, sigs, cfg, regime=reg, strategy_kind="reversion")
        s = res["stats"]
        s["strategy"] = name
        results.append(s)
        # Save trades
        out = ROOT / "data" / "trades" / f"{name}.parquet"
        out.parent.mkdir(exist_ok=True)
        if not res["trades"].empty:
            res["trades"].to_parquet(out)
        eq_out = ROOT / "data" / "trades" / f"{name}_equity.parquet"
        res["equity_curve"].to_frame("equity").to_parquet(eq_out)

    df = pd.DataFrame(results)
    cols = ["strategy", "trades", "pf", "net_pnl", "win_rate", "expectancy",
            "max_dd_pct", "sharpe", "final_equity", "avg_layers", "kill_events"]
    df = df[cols]
    df["pf"] = df["pf"].round(3)
    df["net_pnl"] = df["net_pnl"].round(0)
    df["win_rate"] = (df["win_rate"] * 100).round(1)
    df["expectancy"] = df["expectancy"].round(2)
    df["max_dd_pct"] = (df["max_dd_pct"] * 100).round(2)
    df["sharpe"] = df["sharpe"].round(2)
    df["final_equity"] = df["final_equity"].round(0)
    df["avg_layers"] = df["avg_layers"].round(2)
    print("\n" + "=" * 110)
    print(df.to_string(index=False))
    print("=" * 110)

    out = ROOT / "data" / "grid_screening_summary.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
