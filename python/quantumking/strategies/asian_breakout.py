"""Asian-session range box + London breakout (M15).

00:00-08:00 UTC: build the high/low box from M15 bars.
08:00-11:59 UTC: trigger on a solid-body M15 bar (body/range >= 0.60)
that closes outside the box. One trade per day max.

SL: 50 pts beyond the breakout bar's opposite extreme.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..risk import TrailParams

KIND = "trend"  # session breakout = momentum/trend in regime gating
TRAIL = TrailParams(200, 150, 30)
USES_GRID = False
POINT = 0.01


@dataclass
class AsianParams:
    start_hour: int = 0
    end_hour: int = 8
    breakout_window_hours: int = 4
    min_body_ratio: float = 0.60
    sl_buffer_pts: int = 50


def generate_signals(df: pd.DataFrame, p: AsianParams = AsianParams()) -> pd.DataFrame:
    idx = df.index
    hour = idx.hour
    date = idx.tz_convert("UTC").normalize() if idx.tz else idx.normalize()

    # Build daily box high/low using only bars in [start_hour, end_hour)
    in_asia = (hour >= p.start_hour) & (hour < p.end_hour)
    grp = pd.Series(date, index=idx)
    box_high = df["high"].where(in_asia).groupby(grp).cummax()
    box_low = df["low"].where(in_asia).groupby(grp).cummin()
    # ffill across the day so London-session bars see today's box
    box_high = box_high.groupby(grp).ffill()
    box_low = box_low.groupby(grp).ffill()

    in_window = (hour >= p.end_hour) & (hour <= p.end_hour + p.breakout_window_hours - 1)
    body = (df["close"] - df["open"]).abs()
    rng = (df["high"] - df["low"]).replace(0, 1e-5)
    solid = (body / rng) >= p.min_body_ratio

    long_break = in_window & (df["close"] > box_high) & (df["close"] > df["open"]) & solid
    short_break = in_window & (df["close"] < box_low) & (df["close"] < df["open"]) & solid

    signal = pd.Series(0, index=idx, dtype=int)
    sl_pts = pd.Series(np.nan, index=idx)

    # Enforce one trade per day: keep first signal per date only
    sig_raw = pd.Series(0, index=idx, dtype=int)
    sig_raw[long_break] = 1
    sig_raw[short_break] = -1
    first_per_day = (sig_raw != 0).groupby(grp).cumsum() == 1
    keep = (sig_raw != 0) & first_per_day
    signal[keep] = sig_raw[keep]

    sl_long = (df["close"] - df["low"]) / POINT + p.sl_buffer_pts
    sl_short = (df["high"] - df["close"]) / POINT + p.sl_buffer_pts
    sl_pts[signal == 1] = sl_long[signal == 1]
    sl_pts[signal == -1] = sl_short[signal == -1]

    return pd.DataFrame({"signal": signal, "sl_pts": sl_pts})
