"""Optuna parameter optimization for every strategy.

Parameter ranges mirror the MT5 Strategy Tester optimizer screenshot the
user provided. 50 trials per strategy (~10-20 min total).
Objective: maximize PF * sqrt(min(trades,100)/10) -- penalize tiny trade
counts that look great by luck.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import optuna
import pandas as pd

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

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

N_TRIALS = 50  # per strategy


def load_data():
    d = ROOT / "data"
    return {
        "M1": pd.read_parquet(d / "XAUUSD_M1.parquet"),
        "M15": pd.read_parquet(d / "XAUUSD_M15.parquet"),
        "H1": pd.read_parquet(d / "XAUUSD_H1.parquet"),
        "H4": pd.read_parquet(d / "XAUUSD_H4.parquet"),
        "D1": pd.read_parquet(d / "XAUUSD_D1.parquet"),
    }


def score(stats: dict, min_trades: int = 20) -> float:
    t = stats.get("trades", 0)
    pf = stats.get("pf", 0)
    if not pf or pf != pf or pf == float("inf"):  # NaN or inf
        return -10.0
    if t < min_trades:
        return pf * 0.1  # heavily penalize low-trade outcomes
    # scale: penalize low trade count up to 100
    import math
    confidence = math.sqrt(min(t, 100) / 100)
    return pf * confidence


def optim_ma_trend(data, reg):
    def objective(trial):
        p = ma_trend.MAParams(
            fast_ema=trial.suggest_int("fast_ema", 10, 30, step=10),
            slow_ema=trial.suggest_int("slow_ema", 40, 60, step=10),
            kdj_period=trial.suggest_int("kdj_period", 5, 14, step=2),
            kdj_d=trial.suggest_int("kdj_d", 2, 7),
            kdj_s=trial.suggest_int("kdj_s", 2, 7),
            stoch_ob=trial.suggest_int("stoch_ob", 55, 85, step=5),
            stoch_os=trial.suggest_int("stoch_os", 20, 45, step=5),
            fibo_top=trial.suggest_float("fibo_top", 0.382, 0.5, step=0.059),
            fibo_bottom=trial.suggest_float("fibo_bottom", 0.618, 0.786, step=0.059),
            zone_buffer_pts=trial.suggest_int("zone_buffer_pts", 80, 200, step=40),
            sl_buffer_pts=trial.suggest_int("sl_buffer_pts", 200, 500, step=100),
            max_sl_pts=trial.suggest_int("max_sl_pts", 700, 1000, step=50),
        )
        trail = TrailParams(
            activation_pts=trial.suggest_int("trail_start", 1200, 1600, step=200),
            distance_pts=trial.suggest_int("trail_start", 1200, 1600, step=200),  # tied
            step_pts=trial.suggest_int("trail_step", 100, 500, step=100),
        )
        sigs = ma_trend.generate_signals(data["M15"], data["H4"], p)
        cfg = BacktestConfig(initial_equity=10_000, trail=trail)
        res = run(data["M15"], sigs, cfg, regime=reg, strategy_kind="trend")
        return score(res.stats)
    return objective


def optim_bands(data, reg):
    def objective(trial):
        p = bands_extreme.BandsParams(
            bb_period=trial.suggest_int("bb_period", 20, 200, step=20),
            bb_dev=trial.suggest_float("bb_dev", 1.5, 3.0, step=0.1),
            rsi_period=trial.suggest_int("rsi_period", 14, 50),
            rsi_ob=trial.suggest_int("rsi_ob", 65, 85),
            rsi_os=trial.suggest_int("rsi_os", 15, 35),
            shadow_mult=trial.suggest_float("shadow_mult", 1.0, 3.0, step=0.25),
            sl_pts=1500,
        )
        sigs = bands_extreme.generate_signals(data["M15"], p)
        # Grid engine
        cfg = GridConfig(initial_equity=10_000)
        res = run_grid(data["M15"], sigs, cfg, regime=reg, strategy_kind="reversion")
        return score(res["stats"])
    return objective


def optim_asian(data, reg):
    def objective(trial):
        p = asian_breakout.AsianParams(
            start_hour=trial.suggest_int("start_hour", 0, 2),
            end_hour=trial.suggest_int("end_hour", 6, 10),
            breakout_window_hours=trial.suggest_int("breakout_window_hours", 2, 6),
            min_body_ratio=trial.suggest_float("min_body_ratio", 0.4, 0.8, step=0.1),
            sl_buffer_pts=trial.suggest_int("sl_buffer_pts", 30, 200, step=30),
        )
        sigs = asian_breakout.generate_signals(data["M15"], p)
        trail = TrailParams(
            activation_pts=trial.suggest_int("trail_act", 100, 600, step=100),
            distance_pts=trial.suggest_int("trail_dist", 100, 500, step=100),
            step_pts=trial.suggest_int("trail_step", 20, 100, step=20),
        )
        cfg = BacktestConfig(initial_equity=10_000, trail=trail)
        res = run(data["M15"], sigs, cfg, regime=reg, strategy_kind="trend")
        return score(res.stats)
    return objective


def optim_macd(data, reg):
    def objective(trial):
        p = macd_momentum.MacdParams(
            fast=trial.suggest_int("fast", 8, 18, step=2),
            slow=trial.suggest_int("slow", 21, 35, step=2),
            signal=trial.suggest_int("signal", 5, 12),
            sl_buffer_pts=trial.suggest_int("sl_buffer", 50, 300, step=50),
        )
        sigs = macd_momentum.generate_signals(data["M15"], data["H1"], data["H4"], p)
        trail = TrailParams(
            activation_pts=trial.suggest_int("ta", 500, 1500, step=250),
            distance_pts=trial.suggest_int("td", 500, 1500, step=250),
            step_pts=trial.suggest_int("ts", 100, 500, step=100),
        )
        cfg = BacktestConfig(initial_equity=10_000, trail=trail)
        res = run(data["M15"], sigs, cfg, regime=reg, strategy_kind="trend")
        return score(res.stats)
    return objective


def optim_adx(data, reg):
    def objective(trial):
        p = adx_trend.AdxParams(
            period=trial.suggest_int("period", 7, 28),
            threshold=trial.suggest_float("threshold", 15.0, 40.0, step=2.5),
            sl_buffer_pts=trial.suggest_int("sl_buffer", 50, 300, step=50),
        )
        sigs = adx_trend.generate_signals(data["M15"], p)
        trail = TrailParams(
            activation_pts=trial.suggest_int("ta", 500, 1500, step=250),
            distance_pts=trial.suggest_int("td", 500, 1500, step=250),
            step_pts=trial.suggest_int("ts", 100, 500, step=100),
        )
        cfg = BacktestConfig(initial_equity=10_000, trail=trail)
        res = run(data["M15"], sigs, cfg, regime=reg, strategy_kind="trend")
        return score(res.stats)
    return objective


def optim_pivot(data, reg):
    def objective(trial):
        p = pivot_divergence.PivotParams(
            rsi_period=trial.suggest_int("rsi_period", 10, 21),
            touch_buffer_pts=trial.suggest_int("touch", 50, 300, step=50),
            sl_pts=trial.suggest_int("sl_pts", 800, 2500, step=200),
        )
        sigs = pivot_divergence.generate_signals(data["M15"], data["D1"], p)
        cfg = GridConfig(initial_equity=10_000)
        res = run_grid(data["M15"], sigs, cfg, regime=reg, strategy_kind="reversion")
        return score(res["stats"])
    return objective


def optim_vwap(data, reg):
    def objective(trial):
        p = vwap_reversion.VwapParams(
            sigma_mult=trial.suggest_float("sigma_mult", 1.5, 4.0, step=0.25),
            shadow_mult=trial.suggest_float("shadow_mult", 1.0, 3.0, step=0.25),
            warmup_bars=trial.suggest_int("warmup", 2, 16, step=2),
            sl_pts=1500,
        )
        sigs = vwap_reversion.generate_signals(data["M15"], p)
        cfg = GridConfig(initial_equity=10_000)
        res = run_grid(data["M15"], sigs, cfg, regime=reg, strategy_kind="reversion")
        return score(res["stats"])
    return objective


def optim_fractal(data, reg):
    def objective(trial):
        p = fractal_breakout.FractalParams(
            buffer_pts=trial.suggest_int("buffer", 10, 100, step=10),
            sl_buffer_pts=trial.suggest_int("sl_buffer", 10, 80, step=10),
        )
        sigs = fractal_breakout.generate_signals(data["M15"], p)
        trail = TrailParams(
            activation_pts=trial.suggest_int("ta", 500, 1500, step=250),
            distance_pts=trial.suggest_int("td", 500, 1500, step=250),
            step_pts=trial.suggest_int("ts", 100, 500, step=100),
        )
        cfg = BacktestConfig(initial_equity=10_000, trail=trail)
        res = run(data["M15"], sigs, cfg, regime=reg, strategy_kind="trend")
        return score(res.stats)
    return objective


def optim_pulse(data, _):
    def objective(trial):
        p = pulse_momentum.PulseParams(
            streak=trial.suggest_int("streak", 3, 8),
            pulse_pts=trial.suggest_int("pulse_pts", 100, 600, step=50),
            sl_buffer_pts=trial.suggest_int("sl_buffer", 100, 400, step=50),
        )
        sigs = pulse_momentum.generate_signals(data["M1"], p)
        trail = TrailParams(
            activation_pts=trial.suggest_int("ta", 150, 500, step=50),
            distance_pts=trial.suggest_int("td", 100, 300, step=50),
            step_pts=trial.suggest_int("ts", 20, 100, step=20),
        )
        cfg = BacktestConfig(initial_equity=10_000, trail=trail)
        res = run(data["M1"], sigs, cfg, regime=None, strategy_kind="trend")
        return score(res.stats)
    return objective


def optim_smc(data, reg):
    def objective(trial):
        p = smc_orderblock.SmcParams(
            sl_buffer_pts=trial.suggest_int("sl_buf", 10, 100, step=10),
            fib_tolerance_pts=trial.suggest_int("fib_tol", 50, 300, step=50),
            scan_window=trial.suggest_int("scan", 50, 100, step=10),
        )
        sigs = smc_orderblock.generate_signals(data["M15"], p)
        trail = TrailParams(
            activation_pts=trial.suggest_int("ta", 500, 1500, step=250),
            distance_pts=trial.suggest_int("td", 500, 1500, step=250),
            step_pts=trial.suggest_int("ts", 100, 500, step=100),
        )
        cfg = BacktestConfig(initial_equity=10_000, trail=trail)
        res = run(data["M15"], sigs, cfg, regime=reg, strategy_kind="trend")
        return score(res.stats)
    return objective


def main():
    data = load_data()
    reg = regime(data["M15"])
    print(f"Data loaded: M15={len(data['M15']):,} bars")

    studies = [
        ("MA_Trend", optim_ma_trend(data, reg)),
        ("MACD_Momentum", optim_macd(data, reg)),
        ("ADX_Trend", optim_adx(data, reg)),
        ("Asian_Breakout", optim_asian(data, reg)),
        ("Fractal_Breakout", optim_fractal(data, reg)),
        ("SMC_OrderBlock", optim_smc(data, reg)),
        ("Bands_Extreme_GRID", optim_bands(data, reg)),
        ("Pivot_Divergence_GRID", optim_pivot(data, reg)),
        ("VWAP_Reversion_GRID", optim_vwap(data, reg)),
        ("Pulse_Momentum", optim_pulse(data, None)),
    ]

    summary = []
    for name, obj in studies:
        print(f"\n=== Optimizing {name} ===")
        study = optuna.create_study(direction="maximize",
                                     sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(obj, n_trials=N_TRIALS, show_progress_bar=False)
        best = study.best_trial
        print(f"  best score: {best.value:.3f}")
        print(f"  best params: {best.params}")
        summary.append({
            "strategy": name,
            "best_score": best.value,
            "n_trials": N_TRIALS,
            "params": str(best.params),
        })
        out = ROOT / "data" / "optuna" / f"{name}_trials.csv"
        out.parent.mkdir(exist_ok=True)
        study.trials_dataframe().to_csv(out, index=False)

    df = pd.DataFrame(summary).sort_values("best_score", ascending=False)
    print("\n" + "=" * 80)
    print(df.to_string(index=False))
    print("=" * 80)
    df.to_csv(ROOT / "data" / "optuna_summary.csv", index=False)
    print("Saved data/optuna_summary.csv")


if __name__ == "__main__":
    main()
