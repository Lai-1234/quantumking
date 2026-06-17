"""Price-action reversion — pin bar / engulfing rejection at VWAP.

Pure candlestick price action, confirmed by proximity to daily VWAP
(institutional fair value). Fades exhaustion candles back to VWAP.
Range-regime strategy, no grid, fixed SL.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..volume_profile import anchored_vwap

KIND = "reversion"
POINT = 0.01


@dataclass
class PAParams:
    pin_ratio: float = 2.0         # wick >= pin_ratio * body for a pin bar
    vwap_dist_pts: int = 300       # must be at least this far from VWAP
    sl_pts: int = 500
    warmup_bars: int = 6


def generate_signals(df: pd.DataFrame, p: PAParams = PAParams()) -> pd.DataFrame:
    vwap = anchored_vwap(df, "D")
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    body = (c - o).abs().replace(0, 1e-5)
    upper_shadow = h - df[["close", "open"]].max(axis=1)
    lower_shadow = df[["close", "open"]].min(axis=1) - l

    day = df.index.tz_convert("UTC").normalize() if df.index.tz else df.index.normalize()
    bar_in_day = pd.Series(day, index=df.index).groupby(day).cumcount()
    warm_ok = bar_in_day >= p.warmup_bars

    dist = p.vwap_dist_pts * POINT

    # Bullish pin: long lower wick, price extended BELOW vwap -> expect bounce up
    bull_pin = ((lower_shadow >= p.pin_ratio * body) &
                (c < vwap - dist) & warm_ok)
    # Bearish pin: long upper wick, price extended ABOVE vwap -> expect drop
    bear_pin = ((upper_shadow >= p.pin_ratio * body) &
                (c > vwap + dist) & warm_ok)

    # Bullish engulfing far below VWAP
    prev_bear = c.shift(1) < o.shift(1)
    bull_engulf = (prev_bear & (c > o) & (c > o.shift(1)) & (o < c.shift(1)) &
                   (c < vwap - dist) & warm_ok)
    bear_engulf = ((c.shift(1) > o.shift(1)) & (c < o) & (c < o.shift(1)) &
                   (o > c.shift(1)) & (c > vwap + dist) & warm_ok)

    signal = pd.Series(0, index=df.index, dtype=int)
    signal[bull_pin | bull_engulf] = 1
    signal[bear_pin | bear_engulf] = -1
    sl_pts = pd.Series(np.where(signal != 0, p.sl_pts, np.nan), index=df.index)
    return pd.DataFrame({"signal": signal, "sl_pts": sl_pts})
