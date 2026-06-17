"""SMC: Break of Market Structure (BMS) + Fair Value Gap (FVG) + OTE 0.705-0.786.

Stateful logic ported faithfully to a single-pass scan over bars.
This is the most complex strategy; tolerance for logic drift is highest.
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
class SmcParams:
    sl_buffer_pts: int = 15
    fib_tolerance_pts: int = 150
    scan_window: int = 80


def generate_signals(df: pd.DataFrame, p: SmcParams = SmcParams()) -> pd.DataFrame:
    f = fractals(df)
    up_arr = f["up"].shift(2).to_numpy()    # confirmed 2 bars later
    dn_arr = f["down"].shift(2).to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()

    n = len(df)
    signal = np.zeros(n, dtype=int)
    sl_pts = np.full(n, np.nan)

    bull_ob_active = False
    bear_ob_active = False
    bull_ob_high = bull_ob_low = 0.0
    bear_ob_high = bear_ob_low = 0.0

    # Track the index of the most recent confirmed up/dn fractal
    for i in range(p.scan_window, n):
        # Find most recent up/dn fractal within scan window
        up_idx = -1
        dn_idx = -1
        for k in range(3, p.scan_window):
            j = i - k
            if up_idx == -1 and not np.isnan(up_arr[j]):
                up_idx = j
            if dn_idx == -1 and not np.isnan(dn_arr[j]):
                dn_idx = j
            if up_idx != -1 and dn_idx != -1:
                break

        # Bullish BMS: close above the recent up fractal
        if up_idx != -1 and closes[i - 1] > highs[up_idx]:
            # find the lowest low between up_idx and i-1 -> order block candidate
            seg = lows[up_idx: i]
            lowest_local = np.argmin(seg)
            lowest_idx = up_idx + lowest_local
            # FVG check: low at lowest_idx-2 should be above high at lowest_idx
            if lowest_idx >= 2 and (lows[lowest_idx - 2] > highs[lowest_idx]):
                bull_ob_high = highs[lowest_idx]
                bull_ob_low = lows[lowest_idx]
                bull_ob_active = True
                bear_ob_active = False

        # Bearish BMS
        if dn_idx != -1 and closes[i - 1] < lows[dn_idx]:
            seg = highs[dn_idx: i]
            highest_local = np.argmax(seg)
            highest_idx = dn_idx + highest_local
            if highest_idx >= 2 and (highs[highest_idx - 2] < lows[highest_idx]):
                bear_ob_high = highs[highest_idx]
                bear_ob_low = lows[highest_idx]
                bear_ob_active = True
                bull_ob_active = False

        # Trigger: bull OB retest in OTE zone
        if bull_ob_active and lows[i] <= bull_ob_high and closes[i] > bull_ob_low:
            wave_low = bull_ob_low
            # find wave high since OB
            wave_high = highs[i - 50: i].max() if i > 50 else highs[:i].max()
            wave = wave_high - wave_low
            if wave > 1.0:
                fib_705 = wave_low + wave * 0.705
                fib_786 = wave_high - wave * 0.786
                lo = min(fib_705, fib_786) - p.fib_tolerance_pts * POINT
                hi = max(fib_705, fib_786) + p.fib_tolerance_pts * POINT
                if lo <= highs[i] <= hi:
                    signal[i] = 1
                    sl_pts[i] = (closes[i] - bull_ob_low) / POINT + p.sl_buffer_pts
                bull_ob_active = False

        if bear_ob_active and highs[i] >= bear_ob_low and closes[i] < bear_ob_high:
            wave_high = bear_ob_high
            wave_low = lows[i - 50: i].min() if i > 50 else lows[:i].min()
            wave = wave_high - wave_low
            if wave > 1.0:
                fib_705 = wave_high - wave * 0.705
                fib_786 = wave_low + wave * 0.786
                lo = min(fib_705, fib_786) - p.fib_tolerance_pts * POINT
                hi = max(fib_705, fib_786) + p.fib_tolerance_pts * POINT
                if lo <= highs[i] <= hi:
                    signal[i] = -1
                    sl_pts[i] = (bear_ob_high - closes[i]) / POINT + p.sl_buffer_pts
                bear_ob_active = False

    return pd.DataFrame({"signal": signal, "sl_pts": sl_pts}, index=df.index)
