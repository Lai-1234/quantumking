"""Diagnose why 4 strategies fired 0 trades."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quantumking.strategies import (
    bands_extreme, macd_momentum, adx_trend, pivot_divergence,
)


def main() -> None:
    d = ROOT / "data"
    m15 = pd.read_parquet(d / "XAUUSD_M15.parquet")
    h1 = pd.read_parquet(d / "XAUUSD_H1.parquet")
    h4 = pd.read_parquet(d / "XAUUSD_H4.parquet")
    d1 = pd.read_parquet(d / "XAUUSD_D1.parquet")

    print("=== Bands_Extreme ===")
    s = bands_extreme.generate_signals(m15)
    print(f"  signals: {(s['signal']!=0).sum()}  long={(s['signal']==1).sum()}  short={(s['signal']==-1).sum()}")
    # Inspect partial conditions
    from quantumking.indicators import bollinger, rsi
    bb = bollinger(m15["close"], 20, 2.5)
    r = rsi(m15["close"], 14)
    pierce_up = (m15["high"] > bb["upper"]).sum()
    close_back = ((m15["high"] > bb["upper"]) & (m15["close"] < bb["upper"])).sum()
    rsi_ob = (r > 80).sum()
    print(f"  pierce upper: {pierce_up}, close back inside: {close_back}, rsi>80: {rsi_ob}")
    rsi_os = (r < 20).sum()
    print(f"  rsi<20: {rsi_os}")
    sl_nans = s.loc[s["signal"]!=0, "sl_pts"].isna().sum()
    print(f"  signals with NaN sl_pts: {sl_nans}")

    print("\n=== MACD_Momentum ===")
    s = macd_momentum.generate_signals(m15, h1, h4)
    print(f"  signals: {(s['signal']!=0).sum()}")
    from quantumking.indicators import macd, ema
    m = macd(m15["close"])
    cross_up = ((m["macd"].shift(2)<=0) & (m["macd"].shift(1)>0)).sum()
    cross_dn = ((m["macd"].shift(2)>=0) & (m["macd"].shift(1)<0)).sum()
    print(f"  MACD cross up: {cross_up}, cross dn: {cross_dn}")
    bull_h4 = (ema(h4["close"], 50) > ema(h4["close"], 200))
    print(f"  H4 bullish ratio: {bull_h4.mean():.2f}")
    sl_nans = s.loc[s["signal"]!=0, "sl_pts"].isna().sum()
    print(f"  signals with NaN sl_pts: {sl_nans}")

    print("\n=== ADX_Trend ===")
    s = adx_trend.generate_signals(m15)
    print(f"  signals: {(s['signal']!=0).sum()}")
    from quantumking.indicators import adx
    a = adx(m15, 14)
    strong = (a["adx"] >= 25).sum()
    plus_cross = ((a["plus_di"].shift(1)>a["minus_di"].shift(1)) & (a["plus_di"].shift(2)<=a["minus_di"].shift(2))).sum()
    print(f"  ADX>=25 bars: {strong} (of {len(a)})")
    print(f"  +DI cross over -DI: {plus_cross}")
    sl_nans = s.loc[s["signal"]!=0, "sl_pts"].isna().sum()
    print(f"  signals with NaN sl_pts: {sl_nans}")

    print("\n=== Pivot_Divergence ===")
    s = pivot_divergence.generate_signals(m15, d1)
    print(f"  signals: {(s['signal']!=0).sum()}")
    sl_nans = s.loc[s["signal"]!=0, "sl_pts"].isna().sum()
    print(f"  signals with NaN sl_pts: {sl_nans}")


if __name__ == "__main__":
    main()
