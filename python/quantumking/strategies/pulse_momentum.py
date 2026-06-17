"""M1-level 5-bar pulse momentum.

Five consecutive M1 bullish bars whose net move >= 300 pts -> BUY.
Mirror for SELL. SL: 200 pts beyond the 5-bar extreme.

NOTE: runs on M1 timeframe (not M15). Backtest engine resampling needed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..risk import TrailParams

KIND = "trend"
TRAIL = TrailParams(300, 150, 50)
USES_GRID = False
POINT = 0.01
RUN_TIMEFRAME = "M1"


@dataclass
class PulseParams:
    streak: int = 5
    pulse_pts: int = 300
    sl_buffer_pts: int = 200


def generate_signals(df_m1: pd.DataFrame,
                     p: PulseParams = PulseParams()) -> pd.DataFrame:
    bull_bar = df_m1["close"] > df_m1["open"]
    bear_bar = df_m1["close"] < df_m1["open"]

    bull_streak = bull_bar.rolling(p.streak).sum() == p.streak
    bear_streak = bear_bar.rolling(p.streak).sum() == p.streak

    streak_open = df_m1["open"].shift(p.streak - 1)
    move = (df_m1["close"] - streak_open) / POINT

    long_sig = bull_streak & (move >= p.pulse_pts)
    short_sig = bear_streak & (-move >= p.pulse_pts)

    signal = pd.Series(0, index=df_m1.index, dtype=int)
    signal[long_sig] = 1
    signal[short_sig] = -1

    pulse_low = df_m1["low"].rolling(p.streak).min()
    pulse_high = df_m1["high"].rolling(p.streak).max()
    sl_long = (df_m1["close"] - pulse_low) / POINT + p.sl_buffer_pts
    sl_short = (pulse_high - df_m1["close"]) / POINT + p.sl_buffer_pts
    sl_pts = pd.Series(np.nan, index=df_m1.index)
    sl_pts[signal == 1] = sl_long[signal == 1]
    sl_pts[signal == -1] = sl_short[signal == -1]
    return pd.DataFrame({"signal": signal, "sl_pts": sl_pts})
