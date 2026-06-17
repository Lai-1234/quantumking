"""Re-run each strategy with its best optuna params to get unpenalized PF."""
from __future__ import annotations

import ast
import re
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

TRIALS = ROOT / "data" / "optuna"


def get_best_params(name: str) -> dict:
    p = TRIALS / f"{name}_trials.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    best_idx = df["value"].astype(float).idxmax()
    params = {}
    for col in df.columns:
        if col.startswith("params_"):
            val = df.loc[best_idx, col]
            if pd.isna(val):
                continue
            try:
                params[col.replace("params_", "")] = float(val) if "." in str(val) else int(val)
            except (ValueError, TypeError):
                params[col.replace("params_", "")] = val
    return params


def main():
    d = ROOT / "data"
    m1 = pd.read_parquet(d / "XAUUSD_M1.parquet")
    m15 = pd.read_parquet(d / "XAUUSD_M15.parquet")
    h1 = pd.read_parquet(d / "XAUUSD_H1.parquet")
    h4 = pd.read_parquet(d / "XAUUSD_H4.parquet")
    d1 = pd.read_parquet(d / "XAUUSD_D1.parquet")
    reg = regime(m15)

    results = []

    # MA_Trend
    p = get_best_params("MA_Trend")
    if p:
        params = ma_trend.MAParams(
            fast_ema=p["fast_ema"], slow_ema=p["slow_ema"],
            kdj_period=p["kdj_period"], kdj_d=p["kdj_d"], kdj_s=p["kdj_s"],
            stoch_ob=p["stoch_ob"], stoch_os=p["stoch_os"],
            fibo_top=p["fibo_top"], fibo_bottom=p["fibo_bottom"],
            zone_buffer_pts=p["zone_buffer_pts"],
            sl_buffer_pts=p["sl_buffer_pts"], max_sl_pts=p["max_sl_pts"],
        )
        trail = TrailParams(p["trail_start"], p["trail_start"], p["trail_step"])
        sigs = ma_trend.generate_signals(m15, h4, params)
        res = run(m15, sigs, BacktestConfig(trail=trail), regime=reg, strategy_kind="trend")
        s = res.stats; s["strategy"] = "MA_Trend"; results.append(s)

    # MACD
    p = get_best_params("MACD_Momentum")
    if p:
        params = macd_momentum.MacdParams(
            fast=p["fast"], slow=p["slow"], signal=p["signal"],
            sl_buffer_pts=p["sl_buffer"],
        )
        trail = TrailParams(p["ta"], p["td"], p["ts"])
        sigs = macd_momentum.generate_signals(m15, h1, h4, params)
        res = run(m15, sigs, BacktestConfig(trail=trail), regime=reg, strategy_kind="trend")
        s = res.stats; s["strategy"] = "MACD_Momentum"; results.append(s)

    # ADX
    p = get_best_params("ADX_Trend")
    if p:
        params = adx_trend.AdxParams(period=p["period"], threshold=p["threshold"], sl_buffer_pts=p["sl_buffer"])
        trail = TrailParams(p["ta"], p["td"], p["ts"])
        sigs = adx_trend.generate_signals(m15, params)
        res = run(m15, sigs, BacktestConfig(trail=trail), regime=reg, strategy_kind="trend")
        s = res.stats; s["strategy"] = "ADX_Trend"; results.append(s)

    # Asian
    p = get_best_params("Asian_Breakout")
    if p:
        params = asian_breakout.AsianParams(
            start_hour=p["start_hour"], end_hour=p["end_hour"],
            breakout_window_hours=p["breakout_window_hours"],
            min_body_ratio=p["min_body_ratio"], sl_buffer_pts=p["sl_buffer_pts"],
        )
        trail = TrailParams(p["trail_act"], p["trail_dist"], p["trail_step"])
        sigs = asian_breakout.generate_signals(m15, params)
        res = run(m15, sigs, BacktestConfig(trail=trail), regime=reg, strategy_kind="trend")
        s = res.stats; s["strategy"] = "Asian_Breakout"; results.append(s)

    # Fractal
    p = get_best_params("Fractal_Breakout")
    if p:
        params = fractal_breakout.FractalParams(buffer_pts=p["buffer"], sl_buffer_pts=p["sl_buffer"])
        trail = TrailParams(p["ta"], p["td"], p["ts"])
        sigs = fractal_breakout.generate_signals(m15, params)
        res = run(m15, sigs, BacktestConfig(trail=trail), regime=reg, strategy_kind="trend")
        s = res.stats; s["strategy"] = "Fractal_Breakout"; results.append(s)

    # SMC
    p = get_best_params("SMC_OrderBlock")
    if p:
        params = smc_orderblock.SmcParams(sl_buffer_pts=p["sl_buf"], fib_tolerance_pts=p["fib_tol"], scan_window=p["scan"])
        trail = TrailParams(p["ta"], p["td"], p["ts"])
        sigs = smc_orderblock.generate_signals(m15, params)
        res = run(m15, sigs, BacktestConfig(trail=trail), regime=reg, strategy_kind="trend")
        s = res.stats; s["strategy"] = "SMC_OrderBlock"; results.append(s)

    # Bands grid
    p = get_best_params("Bands_Extreme_GRID")
    if p:
        params = bands_extreme.BandsParams(
            bb_period=p["bb_period"], bb_dev=p["bb_dev"],
            rsi_period=p["rsi_period"], rsi_ob=p["rsi_ob"], rsi_os=p["rsi_os"],
            shadow_mult=p["shadow_mult"], sl_pts=1500,
        )
        sigs = bands_extreme.generate_signals(m15, params)
        res = run_grid(m15, sigs, GridConfig(), regime=reg, strategy_kind="reversion")
        s = res["stats"]; s["strategy"] = "Bands_Extreme_GRID"; results.append(s)

    # Pivot grid
    p = get_best_params("Pivot_Divergence_GRID")
    if p:
        params = pivot_divergence.PivotParams(rsi_period=p["rsi_period"], touch_buffer_pts=p["touch"], sl_pts=p["sl_pts"])
        sigs = pivot_divergence.generate_signals(m15, d1, params)
        res = run_grid(m15, sigs, GridConfig(), regime=reg, strategy_kind="reversion")
        s = res["stats"]; s["strategy"] = "Pivot_Divergence_GRID"; results.append(s)

    # VWAP grid
    p = get_best_params("VWAP_Reversion_GRID")
    if p:
        params = vwap_reversion.VwapParams(sigma_mult=p["sigma_mult"], shadow_mult=p["shadow_mult"], warmup_bars=p["warmup"], sl_pts=1500)
        sigs = vwap_reversion.generate_signals(m15, params)
        res = run_grid(m15, sigs, GridConfig(), regime=reg, strategy_kind="reversion")
        s = res["stats"]; s["strategy"] = "VWAP_Reversion_GRID"; results.append(s)

    # Pulse
    p = get_best_params("Pulse_Momentum")
    if p:
        params = pulse_momentum.PulseParams(streak=p["streak"], pulse_pts=p["pulse_pts"], sl_buffer_pts=p["sl_buffer"])
        trail = TrailParams(p["ta"], p["td"], p["ts"])
        sigs = pulse_momentum.generate_signals(m1, params)
        res = run(m1, sigs, BacktestConfig(trail=trail), regime=None, strategy_kind="trend")
        s = res.stats; s["strategy"] = "Pulse_Momentum"; results.append(s)

    df = pd.DataFrame(results)
    df = df[["strategy", "trades", "pf", "net_pnl", "win_rate", "expectancy", "max_dd_pct", "sharpe", "final_equity"]]
    df = df.sort_values("pf", ascending=False)
    df["pf"] = df["pf"].round(3)
    df["net_pnl"] = df["net_pnl"].round(0)
    df["win_rate"] = (df["win_rate"] * 100).round(1)
    df["expectancy"] = df["expectancy"].round(2)
    df["max_dd_pct"] = (df["max_dd_pct"] * 100).round(2)
    df["sharpe"] = df["sharpe"].round(2)
    df["final_equity"] = df["final_equity"].round(0)
    print(df.to_string(index=False))
    df.to_csv(ROOT / "data" / "optimized_results.csv", index=False)


if __name__ == "__main__":
    main()
