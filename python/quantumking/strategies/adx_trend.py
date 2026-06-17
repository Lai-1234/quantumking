"""ADX > 25 + DI crossover (M15).

Long: ADX > threshold AND +DI[1] <= -DI[1] AND +DI[0] > -DI[0].
Short: mirror.
SL: 50-bar structure low/high + 150 pt buffer.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..indicators import adx
from ..risk import TrailParams

KIND = "trend"
TRAIL = TrailParams(1000, 1000, 500)
USES_GRID = False
POINT = 0.01


@dataclass
class AdxParams:
    period: int = 14
    threshold: float = 25.0
    sl_buffer_pts: int = 150


def generate_signals(df: pd.DataFrame, p: AdxParams = AdxParams()) -> pd.DataFrame:
    a = adx(df, p.period)
    plus = a["plus_di"]
    minus = a["minus_di"]
    adx_ = a["adx"]

    plus_1 = plus.shift(1)
    minus_1 = minus.shift(1)
    plus_2 = plus.shift(2)
    minus_2 = minus.shift(2)

    strong = adx_.shift(1) >= p.threshold
    long_cross = strong & (plus_1 > minus_1) & (plus_2 <= minus_2)
    short_cross = strong & (minus_1 > plus_1) & (minus_2 <= plus_2)

    signal = pd.Series(0, index=df.index, dtype=int)
    signal[long_cross] = 1
    signal[short_cross] = -1

    swing_low = df["low"].rolling(50, min_periods=10).min().shift(1)
    swing_high = df["high"].rolling(50, min_periods=10).max().shift(1)
    sl_long = (df["close"] - swing_low) / POINT + p.sl_buffer_pts
    sl_short = (swing_high - df["close"]) / POINT + p.sl_buffer_pts
    sl_pts = pd.Series(np.nan, index=df.index)
    sl_pts[signal == 1] = sl_long[signal == 1]
    sl_pts[signal == -1] = sl_short[signal == -1]

    return pd.DataFrame({"signal": signal, "sl_pts": sl_pts})
