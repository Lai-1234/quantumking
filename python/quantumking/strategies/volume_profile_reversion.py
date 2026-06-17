"""Volume Profile reversion — fade moves far from Point of Control.

When price extends beyond the Value Area (VAH/VAL) and shows rejection,
fade it back toward the POC. Profits in range regime when price oscillates
around the high-volume node. NO grid; fixed SL.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..volume_profile import volume_profile_daily

KIND = "reversion"
POINT = 0.01


@dataclass
class VPParams:
    n_bins: int = 50
    value_area_pct: float = 0.70
    extension_pts: int = 200       # how far beyond VA before fading
    shadow_mult: float = 1.0
    sl_pts: int = 600
    warmup_bars: int = 8


def generate_signals(df: pd.DataFrame, p: VPParams = VPParams()) -> pd.DataFrame:
    vp = volume_profile_daily(df, n_bins=p.n_bins, value_area_pct=p.value_area_pct)
    vah = vp["vah"]
    val = vp["val"]

    body = (df["close"] - df["open"]).abs().replace(0, 1e-5)
    upper_shadow = df["high"] - df[["close", "open"]].max(axis=1)
    lower_shadow = df[["close", "open"]].min(axis=1) - df["low"]

    day = df.index.tz_convert("UTC").normalize() if df.index.tz else df.index.normalize()
    bar_in_day = pd.Series(day, index=df.index).groupby(day).cumcount()
    warm_ok = bar_in_day >= p.warmup_bars

    ext = p.extension_pts * POINT
    # SELL: high pierces above VAH+ext, closes back below VAH, upper wick rejection
    sell = ((df["high"] > vah + ext) & (df["close"] < vah) &
            (upper_shadow >= body * p.shadow_mult) & warm_ok)
    # BUY: low pierces below VAL-ext, closes back above VAL, lower wick rejection
    buy = ((df["low"] < val - ext) & (df["close"] > val) &
           (lower_shadow >= body * p.shadow_mult) & warm_ok)

    signal = pd.Series(0, index=df.index, dtype=int)
    signal[buy] = 1
    signal[sell] = -1
    sl_pts = pd.Series(np.where(signal != 0, p.sl_pts, np.nan), index=df.index)
    return pd.DataFrame({"signal": signal, "sl_pts": sl_pts})
