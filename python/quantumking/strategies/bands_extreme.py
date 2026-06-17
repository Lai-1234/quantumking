"""Bollinger Band extreme reversal (M15).

Entry:
- High pierces upper band, close falls back inside, upper shadow >=
  1.5x body, RSI > 80  -> SELL
- Low pierces lower band, close back inside, lower shadow >= 1.5x body,
  RSI < 20 -> BUY

Original exit: grid system (no fixed SL). For the screener we apply a
wide protective SL of 1500 pts -- the entry signal's edge is what we're
measuring, not the grid amplifier.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..indicators import bollinger, rsi
from ..risk import TrailParams

KIND = "reversion"
TRAIL = TrailParams(300, 150, 30)  # screener uses light trail since no grid
USES_GRID = True
SCREENER_SL_PTS = 1500


@dataclass
class BandsParams:
    bb_period: int = 20
    bb_dev: float = 2.5
    rsi_period: int = 14
    rsi_ob: int = 80
    rsi_os: int = 20
    shadow_mult: float = 1.5
    sl_pts: int = 1500


def generate_signals(df: pd.DataFrame, p: BandsParams = BandsParams()) -> pd.DataFrame:
    bb = bollinger(df["close"], p.bb_period, p.bb_dev)
    r = rsi(df["close"], p.rsi_period)

    body = (df["close"] - df["open"]).abs().replace(0, 1e-5)
    upper_shadow = df["high"] - df[["close", "open"]].max(axis=1)
    lower_shadow = df[["close", "open"]].min(axis=1) - df["low"]

    sell = ((df["high"] > bb["upper"]) & (df["close"] < bb["upper"]) &
            (upper_shadow >= body * p.shadow_mult) & (r > p.rsi_ob))
    buy = ((df["low"] < bb["lower"]) & (df["close"] > bb["lower"]) &
           (lower_shadow >= body * p.shadow_mult) & (r < p.rsi_os))

    signal = pd.Series(0, index=df.index, dtype=int)
    signal[buy] = 1
    signal[sell] = -1
    sl_pts = pd.Series(np.where(signal != 0, p.sl_pts, np.nan), index=df.index)
    return pd.DataFrame({"signal": signal, "sl_pts": sl_pts})
