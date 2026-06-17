"""Signal-coordination analysis.

For each pair of strategies, find bars where both signals fire within
+/- N bars of each other. Compare:
  - solo PF of strategy A (when A signals but B doesn't)
  - solo PF of strategy B (when B signals but A doesn't)
  - confluence PF (same direction within window)
  - opposite PF (opposite direction within window)

This shows whether running them together helps or hurts.

Also runs combined-portfolio backtests:
  - Strategy A alone
  - Strategy B alone
  - A + B running in parallel
  - A + B + C running in parallel
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.backtest import BacktestConfig, run
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import (
    adx_trend, asian_breakout, fractal_breakout, ma_trend, macd_momentum,
    smc_orderblock,
)


def load():
    d = ROOT / "data"
    return {
        "M15": pd.read_parquet(d / "XAUUSD_M15.parquet"),
        "H1": pd.read_parquet(d / "XAUUSD_H1.parquet"),
        "H4": pd.read_parquet(d / "XAUUSD_H4.parquet"),
    }


def signal_set(data):
    m15, h1, h4 = data["M15"], data["H1"], data["H4"]
    return {
        "MA_Trend": ma_trend.generate_signals(m15, h4)["signal"],
        "MACD_Momentum": macd_momentum.generate_signals(m15, h1, h4)["signal"],
        "SMC_OrderBlock": smc_orderblock.generate_signals(m15)["signal"],
        "ADX_Trend": adx_trend.generate_signals(m15)["signal"],
        "Asian_Breakout": asian_breakout.generate_signals(m15)["signal"],
        "Fractal_Breakout": fractal_breakout.generate_signals(m15)["signal"],
    }


def overlap_stats(sigs: dict, window: int = 4):
    """For every strategy pair, count overlaps and direction agreement."""
    names = list(sigs.keys())
    rows = []
    for a, b in combinations(names, 2):
        sa = sigs[a]
        sb = sigs[b]
        # window: a fires at bar i, b fires at some i' in [i-window, i+window]
        a_idx = sa.index[sa != 0]
        b_idx = sb.index[sb != 0]
        # For each a-fire, look in window of bars for any b-fire
        sa_arr = sa.to_numpy()
        sb_arr = sb.to_numpy()
        n = len(sa)
        agree_same = 0
        agree_opp = 0
        a_alone = 0
        for i in np.where(sa_arr != 0)[0]:
            lo = max(0, i - window)
            hi = min(n, i + window + 1)
            b_nearby = sb_arr[lo:hi]
            b_nearby = b_nearby[b_nearby != 0]
            if len(b_nearby) == 0:
                a_alone += 1
            else:
                # consider the closest one's direction
                if (b_nearby == sa_arr[i]).any():
                    agree_same += 1
                elif (b_nearby == -sa_arr[i]).any():
                    agree_opp += 1
        b_alone = (sb != 0).sum() - agree_same - agree_opp
        rows.append({
            "pair": f"{a} + {b}",
            "a_signals": int((sa != 0).sum()),
            "b_signals": int((sb != 0).sum()),
            "a_alone_pct": round(a_alone / max((sa != 0).sum(), 1) * 100, 1),
            "b_alone_pct": round(b_alone / max((sb != 0).sum(), 1) * 100, 1),
            "confluence_same": int(agree_same),
            "confluence_opp": int(agree_opp),
        })
    return pd.DataFrame(rows)


def combined_portfolio_backtest(data, strategies_to_combine, max_positions=3):
    """Run a portfolio backtest with multiple strategies firing simultaneously.

    Simplification: each strategy's PnL is computed independently then summed.
    This is the upper bound -- doesn't model the actual MQL5 global-position
    cap or grid lock. For exact coordination we'd need to run them in lockstep.
    """
    sigs_dict = signal_set(data)
    m15 = data["M15"]
    reg = regime(m15)
    h1, h4 = data["H1"], data["H4"]

    eq_curves = {}
    stats = {}

    for name in strategies_to_combine:
        if name == "MA_Trend":
            sigs = ma_trend.generate_signals(m15, h4)
            trail = TrailParams(1400, 1400, 300)
        elif name == "MACD_Momentum":
            sigs = macd_momentum.generate_signals(m15, h1, h4)
            trail = TrailParams(1000, 1000, 200)
        elif name == "SMC_OrderBlock":
            sigs = smc_orderblock.generate_signals(m15)
            trail = TrailParams(750, 1500, 500)
        elif name == "ADX_Trend":
            sigs = adx_trend.generate_signals(m15)
            trail = TrailParams(1250, 750, 300)
        elif name == "Asian_Breakout":
            sigs = asian_breakout.generate_signals(m15)
            trail = TrailParams(400, 100, 40)
        else:
            continue
        res = run(m15, sigs, BacktestConfig(initial_equity=10_000, trail=trail),
                  regime=reg, strategy_kind="trend")
        eq_curves[name] = res.equity_curve - 10_000  # PnL relative
        stats[name] = res.stats

    combined_eq = sum(eq_curves.values()) + 10_000
    combined_eq.name = "+".join(strategies_to_combine)
    rets = combined_eq.pct_change().dropna()
    running = combined_eq.cummax()
    dd = ((combined_eq - running) / running).min()
    sharpe = (rets.mean() / rets.std()) * np.sqrt(252 * 96) if rets.std() > 0 else 0
    total_pnl = combined_eq.iloc[-1] - 10_000
    # Implied PF: not straightforward without per-trade, approximate via win/loss ratios
    return {
        "portfolio": "+".join(strategies_to_combine),
        "total_pnl": round(total_pnl, 0),
        "final_equity": round(combined_eq.iloc[-1], 0),
        "max_dd_pct": round(dd * 100, 2),
        "sharpe": round(sharpe, 2),
    }, combined_eq


def main():
    data = load()
    sigs = signal_set(data)

    # 1) Overlap analysis
    print("=" * 80)
    print("PAIR OVERLAP ANALYSIS  (window = +/- 4 bars on M15 = 1 hour)")
    print("=" * 80)
    overlap_df = overlap_stats(sigs, window=4)
    print(overlap_df.to_string(index=False))
    overlap_df.to_csv(ROOT / "data" / "signal_overlap.csv", index=False)

    # 2) Combined-portfolio backtests
    print("\n" + "=" * 80)
    print("PORTFOLIO BACKTESTS (independent-sum approximation)")
    print("=" * 80)
    portfolios = [
        ["MA_Trend"],
        ["MACD_Momentum"],
        ["SMC_OrderBlock"],
        ["MA_Trend", "MACD_Momentum"],
        ["MA_Trend", "SMC_OrderBlock"],
        ["MACD_Momentum", "SMC_OrderBlock"],
        ["MA_Trend", "MACD_Momentum", "SMC_OrderBlock"],
        ["MA_Trend", "MACD_Momentum", "SMC_OrderBlock", "ADX_Trend"],
        ["MA_Trend", "MACD_Momentum", "SMC_OrderBlock", "ADX_Trend", "Asian_Breakout"],
    ]
    rows = []
    eq_curves = {}
    for pf in portfolios:
        result, eq = combined_portfolio_backtest(data, pf)
        rows.append(result)
        eq_curves[result["portfolio"]] = eq
    pf_df = pd.DataFrame(rows)
    print(pf_df.to_string(index=False))
    pf_df.to_csv(ROOT / "data" / "portfolio_combos.csv", index=False)

    # 3) Save combined equity curves
    eq_all = pd.DataFrame(eq_curves)
    eq_all.to_parquet(ROOT / "data" / "portfolio_equity_curves.parquet")
    print(f"\nSaved data/portfolio_combos.csv + portfolio_equity_curves.parquet")


if __name__ == "__main__":
    main()
