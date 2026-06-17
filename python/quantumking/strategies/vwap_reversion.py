"""Intraday VWAP + 3-sigma bands extreme reversal (M15).

Daily-anchored VWAP with volume-weighted standard deviation. Trigger on a
bar that pierces upper/lower band and closes back inside, with a wick
>= 1.5x body.

Original exit: grid. Screener uses fixed SL of 1500 pts.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..indicators import vwap_sigma
from ..risk import TrailParams

KIND = "reversion"
TRAIL = TrailParams(300, 150, 30)
USES_GRID = True


@dataclass
class VwapParams:
    sigma_mult: float = 3.0
    shadow_mult: float = 1.5
    warmup_bars: int = 4
    sl_pts: int = 1500


def generate_signals(df: pd.DataFrame, p: VwapParams = VwapParams()) -> pd.DataFrame:
    bands = vwap_sigma(df, p.sigma_mult)
    upper = bands["upper"]
    lower = bands["lower"]

    body = (df["close"] - df["open"]).abs().replace(0, 1e-5)
    upper_shadow = df["high"] - df[["close", "open"]].max(axis=1)
    lower_shadow = df[["close", "open"]].min(axis=1) - df["low"]

    sell = ((df["high"] > upper) & (df["close"] < upper) &
            (upper_shadow >= body * p.shadow_mult))
    buy = ((df["low"] < lower) & (df["close"] > lower) &
           (lower_shadow >= body * p.shadow_mult))

    # warm-up: skip first p.warmup_bars per day
    date = df.index.tz_convert("UTC").normalize() if df.index.tz else df.index.normalize()
    bar_in_day = pd.Series(date, index=df.index).groupby(date).cumcount()
    warm_ok = bar_in_day >= p.warmup_bars

    signal = pd.Series(0, index=df.index, dtype=int)
    signal[buy & warm_ok] = 1
    signal[sell & warm_ok] = -1
    sl_pts = pd.Series(np.where(signal != 0, p.sl_pts, np.nan), index=df.index)
    return pd.DataFrame({"signal": signal, "sl_pts": sl_pts})
