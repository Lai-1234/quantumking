"""Re-run concurrent portfolio with each strategy's variant-sweep-best filters/SL.

Earlier concurrent test used optuna params but no MTF filter scaling.
Variant sweep showed ADX, Fractal, VWAP improve massively with H1+H4 filter.
This test puts the best variant of each strategy into the portfolio.
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.filters import apply_filters
from quantumking.portfolio_engine import PortfolioConfig, StratSpec, run_portfolio
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import (
    adx_trend, asian_breakout, fractal_breakout, ma_trend, macd_momentum,
    smc_orderblock, vwap_reversion,
)


def main():
    d = ROOT / "data"
    m15 = pd.read_parquet(d / "XAUUSD_M15.parquet")
    h1 = pd.read_parquet(d / "XAUUSD_H1.parquet")
    h4 = pd.read_parquet(d / "XAUUSD_H4.parquet")
    reg = regime(m15)

    # Best-variant filtered signals per strategy (from variant_top10_per_strategy.csv)
    ma_sigs = apply_filters(ma_trend.generate_signals(m15, h4), df_h1=h1, df_h4=h4)
    macd_sigs = apply_filters(macd_momentum.generate_signals(m15, h1, h4), df_h1=h1, df_h4=h4)
    smc_sigs = apply_filters(smc_orderblock.generate_signals(m15), df_h1=h1, df_h4=h4)
    adx_sigs = apply_filters(adx_trend.generate_signals(m15), df_h1=h1, df_h4=h4)
    asian_sigs = asian_breakout.generate_signals(m15)  # no MTF for Asian per top-10
    fractal_sigs = apply_filters(fractal_breakout.generate_signals(m15), df_h1=h1, df_h4=h4)
    vwap_sigs = apply_filters(vwap_reversion.generate_signals(m15), df_h1=h1)

    ma_spec = StratSpec("MA_Trend", ma_sigs, TrailParams(1400, 1400, 300), kind="trend", weight=1.0)
    macd_spec = StratSpec("MACD_Momentum", macd_sigs, TrailParams(1400, 1400, 300), kind="trend", weight=0.5)
    smc_spec = StratSpec("SMC_OrderBlock", smc_sigs, TrailParams(2000, 1500, 500), kind="trend", weight=0.7)
    adx_spec = StratSpec("ADX_Trend", adx_sigs, TrailParams(1000, 1000, 200), kind="trend", weight=0.3)
    asian_spec = StratSpec("Asian_Breakout", asian_sigs, TrailParams(1400, 1400, 100), kind="trend", weight=0.3)
    fractal_spec = StratSpec("Fractal_Breakout", fractal_sigs, TrailParams(300, 150, 50), kind="trend", weight=0.3)

    catalogue = [ma_spec, macd_spec, smc_spec, adx_spec, asian_spec, fractal_spec]

    rows = []
    for k in range(1, len(catalogue) + 1):
        for combo in combinations(catalogue, k):
            names = "+".join(s.name for s in combo)
            res = run_portfolio(m15, list(combo), PortfolioConfig(initial_equity=10_000), regime=reg)
            rows.append({
                "portfolio": names,
                "n_strats": len(combo),
                "trades": res["trades"],
                "pf": round(res["pf"], 3),
                "net_pnl": round(res["net_pnl"], 0),
                "win_rate_pct": round(res["win_rate"] * 100, 1),
                "max_dd_pct": round(res["max_dd_pct"] * 100, 2),
                "sharpe": round(res["sharpe"], 2),
                "final_equity": round(res["final_equity"], 0),
            })

    df = pd.DataFrame(rows).sort_values(["sharpe", "pf"], ascending=False)
    df.to_csv(ROOT / "data" / "concurrent_best_variants.csv", index=False)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
