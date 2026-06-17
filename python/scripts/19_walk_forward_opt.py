"""Walk-forward parameter optimization.

Split data into 6-month windows. Train (find best params) on first window,
test (locked params) on next window. Roll forward.

This is the gold-standard test for overfitting: if PF stays > 1.0
on each forward window with NO peeking, the edge is real.
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
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies import ma_trend


def objective_ma_trend(df_m15, df_h4, reg):
    def fn(trial):
        p = ma_trend.MAParams(
            fast_ema=trial.suggest_int("fast_ema", 10, 30, step=10),
            slow_ema=trial.suggest_int("slow_ema", 40, 70, step=10),
            kdj_period=trial.suggest_int("kdj_period", 5, 14, step=2),
            kdj_d=trial.suggest_int("kdj_d", 2, 6),
            kdj_s=trial.suggest_int("kdj_s", 2, 6),
            stoch_ob=trial.suggest_int("stoch_ob", 55, 85, step=5),
            stoch_os=trial.suggest_int("stoch_os", 20, 45, step=5),
            fibo_top=0.5, fibo_bottom=0.618,
            zone_buffer_pts=trial.suggest_int("zone_buf", 80, 200, step=40),
            sl_buffer_pts=trial.suggest_int("sl_buf", 200, 500, step=100),
            max_sl_pts=trial.suggest_int("max_sl", 700, 1000, step=50),
        )
        trail = TrailParams(
            activation_pts=trial.suggest_int("ta", 1200, 1600, step=200),
            distance_pts=trial.suggest_int("ta", 1200, 1600, step=200),
            step_pts=trial.suggest_int("ts", 100, 500, step=100),
        )
        sigs = ma_trend.generate_signals(df_m15, df_h4, p)
        res = run(df_m15, sigs, BacktestConfig(initial_equity=10_000, trail=trail),
                  regime=reg, strategy_kind="trend")
        s = res.stats
        if s["trades"] < 5:
            return 0
        return s["pf"]
    return fn


def main():
    d = ROOT / "data"
    m15 = pd.read_parquet(d / "XAUUSD_M15.parquet")
    h4 = pd.read_parquet(d / "XAUUSD_H4.parquet")

    # Windows: train 12 months, test 6 months, rolling forward
    starts = pd.date_range("2020-01-01", "2025-04-01", freq="6MS", tz="UTC")
    rows = []
    for i in range(len(starts) - 3):  # need at least train+test windows
        train_start = starts[i]
        train_end = starts[i + 2]  # 12 months train
        test_end = starts[i + 3]   # 6 months test

        m15_train = m15[(m15.index >= train_start) & (m15.index < train_end)]
        h4_train = h4[(h4.index >= train_start) & (h4.index < train_end)]
        m15_test = m15[(m15.index >= train_end) & (m15.index < test_end)]
        h4_test = h4[(h4.index >= train_end) & (h4.index < test_end)]
        reg_train = regime(m15_train)
        reg_test = regime(m15_test)

        if len(m15_train) < 1000 or len(m15_test) < 1000:
            continue

        print(f"Window {i}: train {train_start.date()}..{train_end.date()}, test {train_end.date()}..{test_end.date()}")

        # Optimize on train
        study = optuna.create_study(direction="maximize",
                                     sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective_ma_trend(m15_train, h4_train, reg_train),
                       n_trials=30, show_progress_bar=False)
        best = study.best_trial.params

        # Apply on test
        p = ma_trend.MAParams(
            fast_ema=best["fast_ema"], slow_ema=best["slow_ema"],
            kdj_period=best["kdj_period"], kdj_d=best["kdj_d"], kdj_s=best["kdj_s"],
            stoch_ob=best["stoch_ob"], stoch_os=best["stoch_os"],
            fibo_top=0.5, fibo_bottom=0.618,
            zone_buffer_pts=best["zone_buf"], sl_buffer_pts=best["sl_buf"],
            max_sl_pts=best["max_sl"],
        )
        trail = TrailParams(best["ta"], best["ta"], best["ts"])
        sigs_test = ma_trend.generate_signals(m15_test, h4_test, p)
        res_test = run(m15_test, sigs_test, BacktestConfig(initial_equity=10_000, trail=trail),
                       regime=reg_test, strategy_kind="trend")
        s_test = res_test.stats

        rows.append({
            "window": i,
            "train_start": train_start.date(),
            "train_end": train_end.date(),
            "test_start": train_end.date(),
            "test_end": test_end.date(),
            "train_pf": round(study.best_value, 3),
            "test_pf": round(s_test["pf"], 3),
            "test_trades": s_test["trades"],
            "test_net_pnl": round(s_test["net_pnl"], 0),
            "test_dd_pct": round(s_test["max_dd_pct"] * 100, 2),
            "best_params": str(best),
        })
        print(f"  train PF {study.best_value:.3f}  ->  test PF {s_test['pf']:.3f}  "
              f"({s_test['trades']} trades, ${s_test['net_pnl']:.0f}, DD {s_test['max_dd_pct']*100:.1f}%)")

    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "data" / "walk_forward_opt_ma_trend.csv", index=False)
    print()
    print("=== Walk-forward summary ===")
    print(df[["window", "train_start", "train_end", "test_start", "test_end",
              "train_pf", "test_pf", "test_trades", "test_net_pnl", "test_dd_pct"]].to_string(index=False))
    # Robustness ratio: median test_pf / median train_pf
    ratio = df["test_pf"].median() / df["train_pf"].median()
    profitable_windows = (df["test_pf"] > 1.0).mean() * 100
    print()
    print(f"Median train PF: {df['train_pf'].median():.3f}")
    print(f"Median test PF:  {df['test_pf'].median():.3f}")
    print(f"Test/Train ratio: {ratio:.2f}  (>=0.7 = robust)")
    print(f"Profitable test windows: {profitable_windows:.0f}%")


if __name__ == "__main__":
    main()
