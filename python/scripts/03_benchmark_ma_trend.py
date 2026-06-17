"""Phase B benchmark: run the MA_Trend Python port on the imported
HistData 6-year XAUUSD M15 dataset and compare PF to MT5's 1.83.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.backtest import BacktestConfig, run
from quantumking.regime import regime
from quantumking.risk import TrailParams
from quantumking.strategies.ma_trend import MAParams, generate_signals


def main() -> None:
    m15 = pd.read_parquet(ROOT / "data" / "XAUUSD_M15.parquet")
    h4 = pd.read_parquet(ROOT / "data" / "XAUUSD_H4.parquet")
    print(f"M15: {len(m15):,} bars  ({m15.index[0]} -> {m15.index[-1]})")
    print(f"H4 : {len(h4):,} bars")
    print()

    params = MAParams(
        fast_ema=10, slow_ema=40,
        kdj_period=7, kdj_d=2, kdj_s=2,
        stoch_ob=70, stoch_os=40,
        fibo_top=0.5, fibo_bottom=0.677,
        zone_buffer_pts=150, sl_buffer_pts=300, max_sl_pts=800,
    )
    print("Computing signals (Fast10/Slow40, KDJ 7/2/2, Fibo 0.5-0.677)...")
    sigs = generate_signals(m15, h4, params)
    n = (sigs["signal"] != 0).sum()
    print(f"  raw signals: {n}  (long={int((sigs['signal']==1).sum())}, "
          f"short={int((sigs['signal']==-1).sum())})")
    print()

    print("Running bar-by-bar backtest with regime + 23-00 UTC pause + trail(1400/1400/100)...")
    reg = regime(m15)
    cfg = BacktestConfig(
        initial_equity=10_000,
        trail=TrailParams(1400, 1400, 100),
    )
    result = run(m15, sigs, cfg, regime=reg, strategy_kind="trend")

    s = result.stats
    print()
    print("=" * 50)
    print(f"  Trades        : {s['trades']}")
    print(f"  Profit factor : {s['pf']:.3f}")
    print(f"  Net PnL       : ${s['net_pnl']:,.2f}")
    print(f"  Win rate      : {s['win_rate']*100:.1f}%")
    print(f"  Expectancy    : ${s['expectancy']:.2f} / trade")
    print(f"  Max DD        : {s['max_dd_pct']*100:.2f}%")
    print(f"  Sharpe        : {s['sharpe']:.2f}")
    print(f"  Final equity  : ${s['final_equity']:,.2f}")
    print("=" * 50)

    pf_target = 1.83
    if s["pf"] > 0:
        diff = abs(s["pf"] - pf_target) / pf_target * 100
        print(f"\nMT5 reference PF: {pf_target}  |  Python PF: {s['pf']:.3f}  "
              f"|  diff: {diff:.1f}%")
        if diff <= 15:
            print("  OK  Within 15% of MT5 (acceptable on OHLC vs real-tick).")
        else:
            print("  WARN  Drift >15% -- investigate before porting other strategies.")

    out = ROOT / "data" / "ma_trend_trades.parquet"
    result.trades.to_parquet(out)
    print(f"\nTrades saved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
