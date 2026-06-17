"""MACD zero-cross with MTF trend filter (M15 execution).

H4 EMA(50)>EMA(200) AND H1 EMA(50)>EMA(200): bullish MTF context.
Long when MACD main flips from <=0 to >0 AND histogram expanding.
SL: structure low of last 50 bars + 150 pt buffer.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..indicators import ema, macd
from ..risk import TrailParams

KIND = "trend"
TRAIL = TrailParams(1000, 1000, 500)
USES_GRID = False
POINT = 0.01


@dataclass
class MacdParams:
    fast: int = 12
    slow: int = 26
    signal: int = 9
    sl_buffer_pts: int = 150


def _mtf_align(higher: pd.Series, target_idx: pd.DatetimeIndex) -> pd.Series:
    return higher.reindex(target_idx, method="ffill")


def generate_signals(df_m15: pd.DataFrame, df_h1: pd.DataFrame,
                     df_h4: pd.DataFrame,
                     p: MacdParams = MacdParams()) -> pd.DataFrame:
    bull_h4 = _mtf_align((ema(df_h4["close"], 50) > ema(df_h4["close"], 200)), df_m15.index)
    bear_h4 = _mtf_align((ema(df_h4["close"], 50) < ema(df_h4["close"], 200)), df_m15.index)
    bull_h1 = _mtf_align((ema(df_h1["close"], 50) > ema(df_h1["close"], 200)), df_m15.index)
    bear_h1 = _mtf_align((ema(df_h1["close"], 50) < ema(df_h1["close"], 200)), df_m15.index)
    bull = bull_h4 & bull_h1
    bear = bear_h4 & bear_h1

    m = macd(df_m15["close"], p.fast, p.slow, p.signal)
    main = m["macd"]
    hist = m["hist"]

    main_1 = main.shift(1)
    main_2 = main.shift(2)
    hist_1 = hist.shift(1)
    hist_2 = hist.shift(2)

    long_sig = bull & (main_2 <= 0) & (main_1 > 0) & (hist_1 > 0) & (hist_1 > hist_2)
    short_sig = bear & (main_2 >= 0) & (main_1 < 0) & (hist_1 < 0) & (hist_1 < hist_2)

    signal = pd.Series(0, index=df_m15.index, dtype=int)
    signal[long_sig] = 1
    signal[short_sig] = -1

    swing_low = df_m15["low"].rolling(50, min_periods=10).min().shift(1)
    swing_high = df_m15["high"].rolling(50, min_periods=10).max().shift(1)
    sl_long = (df_m15["close"] - swing_low) / POINT + p.sl_buffer_pts
    sl_short = (swing_high - df_m15["close"]) / POINT + p.sl_buffer_pts
    sl_pts = pd.Series(np.nan, index=df_m15.index)
    sl_pts[signal == 1] = sl_long[signal == 1]
    sl_pts[signal == -1] = sl_short[signal == -1]

    return pd.DataFrame({"signal": signal, "sl_pts": sl_pts})
