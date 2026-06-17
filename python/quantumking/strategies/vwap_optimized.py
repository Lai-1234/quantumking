"""Optimized VWAP reversion (no-grid) — the organization's core strategy.

Improvements over the v1 grid version that failed:
- Anchored VWAP (daily) with multi-band volume-weighted sigma
- Entry on band pierce + close-back-inside + wick rejection (price action)
- Optional volume confirmation (bar volume > rolling median)
- NO grid; fixed SL exit (sl_only style) — the grid was what killed v1
- Trades in RANGE regime (kind="reversion") to fill the coordination gap
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..volume_profile import vwap_bands

KIND = "reversion"
POINT = 0.01


@dataclass
class VwapOptParams:
    sigma_k: float = 2.5          # band distance
    shadow_mult: float = 1.2      # wick must be this x body
    vol_filter: bool = True       # require above-median volume
    vol_lookback: int = 50
    sl_pts: int = 600             # fixed SL (no grid)
    warmup_bars: int = 6


def generate_signals(df: pd.DataFrame, p: VwapOptParams = VwapOptParams()) -> pd.DataFrame:
    bands = vwap_bands(df, k_list=(p.sigma_k,), anchor="D")
    upper = bands[f"upper_{p.sigma_k}"]
    lower = bands[f"lower_{p.sigma_k}"]

    body = (df["close"] - df["open"]).abs().replace(0, 1e-5)
    upper_shadow = df["high"] - df[["close", "open"]].max(axis=1)
    lower_shadow = df[["close", "open"]].min(axis=1) - df["low"]

    # bar-in-day index for warmup
    day = df.index.tz_convert("UTC").normalize() if df.index.tz else df.index.normalize()
    bar_in_day = pd.Series(day, index=df.index).groupby(day).cumcount()
    warm_ok = bar_in_day >= p.warmup_bars

    vol_ok = pd.Series(True, index=df.index)
    if p.vol_filter:
        med = df["volume"].rolling(p.vol_lookback, min_periods=10).median()
        vol_ok = df["volume"] > med

    # SELL: pierce upper band, close back inside, big upper wick
    sell = ((df["high"] > upper) & (df["close"] < upper) &
            (upper_shadow >= body * p.shadow_mult) & warm_ok & vol_ok)
    # BUY: pierce lower band, close back inside, big lower wick
    buy = ((df["low"] < lower) & (df["close"] > lower) &
           (lower_shadow >= body * p.shadow_mult) & warm_ok & vol_ok)

    signal = pd.Series(0, index=df.index, dtype=int)
    signal[buy] = 1
    signal[sell] = -1
    sl_pts = pd.Series(np.where(signal != 0, p.sl_pts, np.nan), index=df.index)
    return pd.DataFrame({"signal": signal, "sl_pts": sl_pts})
