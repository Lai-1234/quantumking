"""Phase B: validate the MA_Trend Python port against the MT5 PF 1.83.

Run from the python/ folder with the venv:
    .venv/Scripts/python.exe scripts/01_validate_ma_trend.py

Requires MetaTrader 5 to be running and logged in (for first-time data
fetch). Subsequent runs use the parquet cache in python/data/.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.backtest import BacktestConfig, run
from quantumking.data import FetchSpec, load
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies.ma_trend import MAParams, generate_signals

START = datetime(2023, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 5, 27, tzinfo=timezone.utc)


def main() -> None:
    print(f"[1/4] Loading XAUUSD M15 + H4 from {START.date()} to {END.date()}...")
    m15 = load(FetchSpec("XAUUSD", "M15", START, END))
    h4 = load(FetchSpec("XAUUSD", "H4", START, END))
    print(f"      M15 bars: {len(m15):,}  H4 bars: {len(h4):,}")

    print("[2/4] Computing signals (MA_Trend optimized params)...")
    params = MAParams(
        fast_ema=10, slow_ema=40,
        kdj_period=7, kdj_d=2, kdj_s=2,
        stoch_ob=70, stoch_os=40,
        fibo_top=0.5, fibo_bottom=0.677,
        zone_buffer_pts=150, sl_buffer_pts=300, max_sl_pts=800,
    )
    sigs = generate_signals(m15, h4, params)
    n_signals = (sigs["signal"] != 0).sum()
    print(f"      Raw signals: {n_signals}  (longs={int((sigs['signal']==1).sum())}, "
          f"shorts={int((sigs['signal']==-1).sum())})")

    print("[3/4] Running backtest with regime + 23-00 UTC pause + trail(1400/1400/100)...")
    reg = regime(m15)
    cfg = BacktestConfig(
        initial_equity=10_000,
        trail=TrailParams(1400, 1400, 100),
    )
    result = run(m15, sigs, cfg, regime=reg, strategy_kind="trend")

    print("[4/4] Results:")
    s = result.stats
    print(f"      Trades        : {s['trades']}")
    print(f"      Profit factor : {s['pf']:.3f}")
    print(f"      Net PnL       : ${s['net_pnl']:.2f}")
    print(f"      Win rate      : {s['win_rate']*100:.1f}%")
    print(f"      Max DD        : {s['max_dd_pct']*100:.2f}%")
    print(f"      Sharpe        : {s['sharpe']:.2f}")
    print(f"      Final equity  : ${s['final_equity']:.2f}")
    print()
    pf_target = 1.83
    diff_pct = abs(s["pf"] - pf_target) / pf_target * 100 if s["pf"] > 0 else float("inf")
    if diff_pct <= 5:
        print(f"      OK  PF within ±5% of {pf_target} (diff {diff_pct:.1f}%) — port validated.")
    else:
        print(f"      WARN  PF off by {diff_pct:.1f}% from MT5's {pf_target}.")
        print("      This is expected if the MT5 backtest covered a different date range")
        print("      or different broker spread. Stop and align before porting other strategies.")

    out = ROOT / "data" / "ma_trend_trades.parquet"
    result.trades.to_parquet(out)
    print(f"      Trades saved to {out}")


if __name__ == "__main__":
    main()
