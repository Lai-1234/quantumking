"""Williams Fractal breakout (M15).

Find the most recent confirmed up and down fractals (5-bar pivots). Long
when price breaks above the up fractal + 30-pt buffer. Short for the
mirror. SL placed at the opposing fractal +/- 20 pts.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..indicators import fractals
from ..risk import TrailParams

KIND = "trend"
TRAIL = TrailParams(1000, 1000, 500)
USES_GRID = False
POINT = 0.01


@dataclass
class FractalParams:
    buffer_pts: int = 30
    sl_buffer_pts: int = 20


def generate_signals(df: pd.DataFrame,
                     p: FractalParams = FractalParams()) -> pd.DataFrame:
    f = fractals(df)
    # confirmed fractals are 2 bars old, so shift(2)
    last_up = f["up"].shift(2).ffill()
    last_dn = f["down"].shift(2).ffill()

    long_break = (df["close"].shift(1) < last_up) & (df["close"] >= last_up + p.buffer_pts * POINT)
    short_break = (df["close"].shift(1) > last_dn) & (df["close"] <= last_dn - p.buffer_pts * POINT)

    signal = pd.Series(0, index=df.index, dtype=int)
    signal[long_break] = 1
    signal[short_break] = -1

    sl_long = (df["close"] - last_dn) / POINT + p.sl_buffer_pts
    sl_short = (last_up - df["close"]) / POINT + p.sl_buffer_pts
    sl_pts = pd.Series(np.nan, index=df.index)
    sl_pts[signal == 1] = sl_long[signal == 1]
    sl_pts[signal == -1] = sl_short[signal == -1]
    sl_pts = sl_pts.where(sl_pts > 0)
    return pd.DataFrame({"signal": signal, "sl_pts": sl_pts})
