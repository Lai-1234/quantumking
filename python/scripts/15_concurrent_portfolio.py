"""Concurrent multi-strategy portfolio backtest (true interference).

Tests all keep-candidate combinations with the MQL5 manager logic:
- global cap 6 positions
- magic-number lock per strategy
- 23:00-00:00 pause
- regime gate
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import (
    adx_trend, asian_breakout, ma_trend, macd_momentum, smc_orderblock,
)


def main():
    d = ROOT / "data"
    m15 = pd.read_parquet(d / "XAUUSD_M15.parquet")
    h1 = pd.read_parquet(d / "XAUUSD_H1.parquet")
    h4 = pd.read_parquet(d / "XAUUSD_H4.parquet")
    reg = regime(m15)

    # Build optimized signal specs
    ma_spec = StratSpec(
        name="MA_Trend",
        signals=ma_trend.generate_signals(m15, h4),
        trail=TrailParams(1400, 1400, 300),
        kind="trend", weight=1.0,
    )
    macd_spec = StratSpec(
        name="MACD_Momentum",
        signals=macd_momentum.generate_signals(m15, h1, h4),
        trail=TrailParams(1000, 1000, 200),
        kind="trend", weight=0.5,
    )
    smc_spec = StratSpec(
        name="SMC_OrderBlock",
        signals=smc_orderblock.generate_signals(m15),
        trail=TrailParams(750, 1500, 500),
        kind="trend", weight=0.7,
    )
    adx_spec = StratSpec(
        name="ADX_Trend",
        signals=adx_trend.generate_signals(m15),
        trail=TrailParams(1250, 750, 300),
        kind="trend", weight=0.3,
    )
    asian_spec = StratSpec(
        name="Asian_Breakout",
        signals=asian_breakout.generate_signals(m15),
        trail=TrailParams(400, 100, 40),
        kind="trend", weight=0.3,
    )

    catalogue = [ma_spec, macd_spec, smc_spec, adx_spec, asian_spec]
    all_combos = []
    for k in range(1, len(catalogue) + 1):
        for combo in combinations(catalogue, k):
            all_combos.append(list(combo))

    rows = []
    for combo in all_combos:
        names = [s.name for s in combo]
        label = "+".join(names)
        res = run_portfolio(m15, combo, PortfolioConfig(initial_equity=10_000), regime=reg)
        rows.append({
            "portfolio": label,
            "n_strats": len(combo),
            "trades": res["trades"],
            "pf": round(res["pf"], 3),
            "net_pnl": round(res["net_pnl"], 0),
            "win_rate_pct": round(res["win_rate"] * 100, 1),
            "max_dd_pct": round(res["max_dd_pct"] * 100, 2),
            "sharpe": round(res["sharpe"], 2),
            "final_equity": round(res["final_equity"], 0),
        })
        print(f"  {label:60s}  PF={res['pf']:.2f}  DD={res['max_dd_pct']*100:.1f}%  PnL=${res['net_pnl']:.0f}")

    df = pd.DataFrame(rows)
    df = df.sort_values(["sharpe", "pf"], ascending=False)
    df.to_csv(ROOT / "data" / "concurrent_portfolio_results.csv", index=False)
    print("\n=== Ranked by Sharpe ===")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
