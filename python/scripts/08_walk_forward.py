"""Walk-forward validation: train 2020-01..2023-12, test 2024-01..2026-04.

Run each strategy with default params on both windows and compare PF.
A strategy that survives walk-forward (out-of-sample PF >= 80% of in-sample
PF) is robust. One that collapses is curve-fit.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.backtest import BacktestConfig, run
from quantumking.grid_backtest import GridConfig, run_grid
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import (
    adx_trend, asian_breakout, bands_extreme, fractal_breakout,
    ma_trend, macd_momentum, pivot_divergence, pulse_momentum,
    smc_orderblock, vwap_reversion,
)

SPLIT = pd.Timestamp("2024-01-01", tz="UTC")


def load_data():
    d = ROOT / "data"
    return {
        "M1": pd.read_parquet(d / "XAUUSD_M1.parquet"),
        "M15": pd.read_parquet(d / "XAUUSD_M15.parquet"),
        "H1": pd.read_parquet(d / "XAUUSD_H1.parquet"),
        "H4": pd.read_parquet(d / "XAUUSD_H4.parquet"),
        "D1": pd.read_parquet(d / "XAUUSD_D1.parquet"),
    }


def split(df, start_idx=None):
    if start_idx is None:
        return df[df.index < SPLIT], df[df.index >= SPLIT]
    return df[df.index < SPLIT], df[df.index >= SPLIT]


def run_phase(name, run_fn):
    data = load_data()
    rows = []
    for label, (df_m1_p, df_m15_p, df_h1_p, df_h4_p, df_d1_p) in {
        "IS": (data["M1"][data["M1"].index < SPLIT],
               data["M15"][data["M15"].index < SPLIT],
               data["H1"][data["H1"].index < SPLIT],
               data["H4"][data["H4"].index < SPLIT],
               data["D1"][data["D1"].index < SPLIT]),
        "OOS": (data["M1"][data["M1"].index >= SPLIT],
                data["M15"][data["M15"].index >= SPLIT],
                data["H1"][data["H1"].index >= SPLIT],
                data["H4"][data["H4"].index >= SPLIT],
                data["D1"][data["D1"].index >= SPLIT]),
    }.items():
        stats = run_fn(df_m1_p, df_m15_p, df_h1_p, df_h4_p, df_d1_p)
        stats["window"] = label
        rows.append(stats)
    return rows


def fn_ma_trend(m1, m15, h1, h4, d1):
    sigs = ma_trend.generate_signals(m15, h4)
    cfg = BacktestConfig(initial_equity=10_000, trail=TrailParams(1400, 1400, 100))
    res = run(m15, sigs, cfg, regime=regime(m15), strategy_kind="trend")
    return res.stats


def fn_bands(m1, m15, h1, h4, d1):
    sigs = bands_extreme.generate_signals(m15)
    res = run_grid(m15, sigs, GridConfig(), regime=regime(m15), strategy_kind="reversion")
    return res["stats"]


def fn_asian(m1, m15, h1, h4, d1):
    sigs = asian_breakout.generate_signals(m15)
    res = run(m15, sigs, BacktestConfig(trail=asian_breakout.TRAIL),
              regime=regime(m15), strategy_kind="trend")
    return res.stats


def fn_macd(m1, m15, h1, h4, d1):
    sigs = macd_momentum.generate_signals(m15, h1, h4)
    res = run(m15, sigs, BacktestConfig(trail=macd_momentum.TRAIL),
              regime=regime(m15), strategy_kind="trend")
    return res.stats


def fn_adx(m1, m15, h1, h4, d1):
    sigs = adx_trend.generate_signals(m15)
    res = run(m15, sigs, BacktestConfig(trail=adx_trend.TRAIL),
              regime=regime(m15), strategy_kind="trend")
    return res.stats


def fn_pivot(m1, m15, h1, h4, d1):
    sigs = pivot_divergence.generate_signals(m15, d1)
    res = run_grid(m15, sigs, GridConfig(), regime=regime(m15), strategy_kind="reversion")
    return res["stats"]


def fn_vwap(m1, m15, h1, h4, d1):
    sigs = vwap_reversion.generate_signals(m15)
    res = run_grid(m15, sigs, GridConfig(), regime=regime(m15), strategy_kind="reversion")
    return res["stats"]


def fn_fractal(m1, m15, h1, h4, d1):
    sigs = fractal_breakout.generate_signals(m15)
    res = run(m15, sigs, BacktestConfig(trail=fractal_breakout.TRAIL),
              regime=regime(m15), strategy_kind="trend")
    return res.stats


def fn_pulse(m1, m15, h1, h4, d1):
    sigs = pulse_momentum.generate_signals(m1)
    res = run(m1, sigs, BacktestConfig(trail=pulse_momentum.TRAIL), regime=None, strategy_kind="trend")
    return res.stats


def fn_smc(m1, m15, h1, h4, d1):
    sigs = smc_orderblock.generate_signals(m15)
    res = run(m15, sigs, BacktestConfig(trail=smc_orderblock.TRAIL),
              regime=regime(m15), strategy_kind="trend")
    return res.stats


def main():
    funcs = [
        ("MA_Trend", fn_ma_trend),
        ("MACD_Momentum", fn_macd),
        ("ADX_Trend", fn_adx),
        ("Asian_Breakout", fn_asian),
        ("Fractal_Breakout", fn_fractal),
        ("SMC_OrderBlock", fn_smc),
        ("Bands_Extreme_GRID", fn_bands),
        ("Pivot_Divergence_GRID", fn_pivot),
        ("VWAP_Reversion_GRID", fn_vwap),
        ("Pulse_Momentum", fn_pulse),
    ]
    all_rows = []
    for name, fn in funcs:
        print(f"WF: {name}...")
        for row in run_phase(name, fn):
            row["strategy"] = name
            all_rows.append(row)
    df = pd.DataFrame(all_rows)
    keep = ["strategy", "window", "trades", "pf", "net_pnl", "win_rate", "max_dd_pct"]
    keep = [c for c in keep if c in df.columns]
    df = df[keep]
    print("\n" + df.to_string(index=False))

    # Robust = OOS PF >= 80% of IS PF
    pivot = df.pivot(index="strategy", columns="window", values="pf").fillna(0)
    if "IS" in pivot.columns and "OOS" in pivot.columns:
        pivot["wf_ratio"] = pivot["OOS"] / pivot["IS"].replace(0, 1e-9)
        pivot["robust"] = pivot["wf_ratio"] >= 0.8
        print("\n\nWalk-forward ratio (OOS/IS):")
        print(pivot.round(3).to_string())
        pivot.to_csv(ROOT / "data" / "walk_forward.csv")
    df.to_csv(ROOT / "data" / "walk_forward_detail.csv", index=False)


if __name__ == "__main__":
    main()
