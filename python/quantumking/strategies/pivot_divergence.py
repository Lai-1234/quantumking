"""Daily pivot R2/S2 + RSI divergence (M15).

Compute classic pivot from previous day's H/L/C. When recent low pierces
near S2 AND recent low < prev swing low BUT recent RSI > prev RSI -> bullish
divergence -> BUY. Mirror for SELL at R2.

Original exit: grid. Screener uses wide protective SL of 1500 pts.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..indicators import rsi
from ..risk import TrailParams

KIND = "reversion"
TRAIL = TrailParams(300, 150, 30)
USES_GRID = True
POINT = 0.01


@dataclass
class PivotParams:
    rsi_period: int = 14
    touch_buffer_pts: int = 150
    sl_pts: int = 1500


def generate_signals(df_m15: pd.DataFrame, df_d1: pd.DataFrame,
                     p: PivotParams = PivotParams()) -> pd.DataFrame:
    # Previous-day pivot levels, broadcast to M15
    prev_h = df_d1["high"].shift(1)
    prev_l = df_d1["low"].shift(1)
    prev_c = df_d1["close"].shift(1)
    pivot = (prev_h + prev_l + prev_c) / 3
    r2 = pivot + (prev_h - prev_l)
    s2 = pivot - (prev_h - prev_l)

    daily = pd.DataFrame({"r2": r2, "s2": s2})
    aligned = daily.reindex(df_m15.index, method="ffill")
    r2_m15 = aligned["r2"]
    s2_m15 = aligned["s2"]

    r = rsi(df_m15["close"], p.rsi_period)
    # Use a 50-bar window: prev swing low in bars [5..45], recent low in [1..4]
    recent_low_idx = df_m15["low"].rolling(5).apply(lambda x: x.argmin(), raw=True)
    prev_low_min = df_m15["low"].rolling(40).min().shift(5)
    recent_low_min = df_m15["low"].rolling(4).min().shift(1)
    prev_high_max = df_m15["high"].rolling(40).max().shift(5)
    recent_high_max = df_m15["high"].rolling(4).max().shift(1)

    # RSI at the bar of recent extremes (approximation: use current rsi)
    rsi_now = r.shift(1)
    # Long: touched/broke S2, made lower low, RSI made higher low
    long_div = (
        (recent_low_min <= s2_m15 + p.touch_buffer_pts * POINT)
        & (recent_low_min < prev_low_min)
        & (rsi_now > rsi_now.rolling(40).min().shift(5))
    )
    short_div = (
        (recent_high_max >= r2_m15 - p.touch_buffer_pts * POINT)
        & (recent_high_max > prev_high_max)
        & (rsi_now < rsi_now.rolling(40).max().shift(5))
    )

    signal = pd.Series(0, index=df_m15.index, dtype=int)
    signal[long_div] = 1
    signal[short_div] = -1
    sl_pts = pd.Series(np.where(signal != 0, p.sl_pts, np.nan), index=df_m15.index)
    return pd.DataFrame({"signal": signal, "sl_pts": sl_pts})
