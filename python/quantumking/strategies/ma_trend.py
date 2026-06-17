"""Port of CStrategy_MA_Trend (the PF 1.83 benchmark).

Logic:
- H4 EMA(fast)/EMA(slow): bullish if fast > slow, bearish if fast < slow.
- M15 Stochastic(7, 2, 2): KDJ buy when main[1] < OS and main[1] > signal[1]
  and main[2] <= signal[2]; sell mirror.
- Entry: regime trigger + Fibonacci 0.5–0.677 retracement touch in last
  3 bars of a swing measured over the previous 100 bars.
- SL: (price - swing low) + 300 pt buffer, capped at 800 pts.
- Trail params handled by backtest engine (1400 / 1400 / 100).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..indicators import ema, stochastic

KIND = "trend"


@dataclass
class MAParams:
    fast_ema: int = 10
    slow_ema: int = 40
    kdj_period: int = 7
    kdj_d: int = 2
    kdj_s: int = 2
    stoch_ob: int = 70
    stoch_os: int = 40
    fibo_top: float = 0.5
    fibo_bottom: float = 0.677
    zone_buffer_pts: int = 150
    sl_buffer_pts: int = 300
    max_sl_pts: int = 800


POINT = 0.01


def generate_signals(df_m15: pd.DataFrame, df_h4: pd.DataFrame,
                     p: MAParams = MAParams()) -> pd.DataFrame:
    """``df_m15`` is the execution timeframe, ``df_h4`` provides the H4 trend."""
    ema_fast = ema(df_h4["close"], p.fast_ema)
    ema_slow = ema(df_h4["close"], p.slow_ema)
    bullish_h4 = (ema_fast > ema_slow).reindex(df_m15.index, method="ffill")
    bearish_h4 = (ema_fast < ema_slow).reindex(df_m15.index, method="ffill")

    st = stochastic(df_m15, p.kdj_period, p.kdj_d, p.kdj_s)
    main = st["main"]
    sig_ = st["signal"]
    # Mirror MQL5 CopyBuffer(handle,0,1,3,sm) -> sm[0]=bar1, sm[1]=bar2, sm[2]=bar3 (older).
    # In MQL5 series-mode arrays, [0]=most recent. We use shift(1), shift(2), shift(3).
    main_1 = main.shift(1)
    main_2 = main.shift(2)
    sig_1 = sig_.shift(1)
    sig_2 = sig_.shift(2)
    kdj_buy = (main_1 < p.stoch_os) & (main_1 > sig_1) & (main_2 <= sig_2)
    kdj_sell = (main_1 > p.stoch_ob) & (main_1 < sig_1) & (main_2 >= sig_2)

    raw_signal = pd.Series(0, index=df_m15.index, dtype=int)
    raw_signal[bullish_h4 & kdj_buy] = 1
    raw_signal[bearish_h4 & kdj_sell] = -1

    # Fibonacci touch + SL calculation per signal bar (window of 100 bars back).
    highs = df_m15["high"].to_numpy()
    lows = df_m15["low"].to_numpy()
    close = df_m15["close"].to_numpy()
    sig_arr = raw_signal.to_numpy()
    out_signal = np.zeros(len(df_m15), dtype=int)
    sl_pts = np.full(len(df_m15), np.nan)

    for i in range(100, len(df_m15)):
        s = sig_arr[i]
        if s == 0:
            continue
        # Find swing in indices [i-99 .. i-1]
        window_h = highs[i - 99: i]
        window_l = lows[i - 99: i]
        if s == 1:
            idx_h_local = int(np.argmax(window_h))
            # min of lows from idx_h_local onward
            tail_l = window_l[idx_h_local:]
            idx_l_local = idx_h_local + int(np.argmin(tail_l))
            swH = window_h[idx_h_local]
            swL = window_l[idx_l_local]
        else:
            idx_l_local = int(np.argmin(window_l))
            tail_h = window_h[idx_l_local:]
            idx_h_local = idx_l_local + int(np.argmax(tail_h))
            swH = window_h[idx_h_local]
            swL = window_l[idx_l_local]
        wave = swH - swL
        if wave < 1.0:
            continue
        price = close[i]
        if s == 1:
            zone_top = swH - wave * p.fibo_top + p.zone_buffer_pts * POINT
            zone_bot = swH - wave * p.fibo_bottom - p.zone_buffer_pts * POINT
            # Did any of last 3 lows touch the zone?
            touched = any(zone_bot <= lows[i - k] <= zone_top for k in range(3))
            if not touched:
                continue
            sl = (price - swL) / POINT + p.sl_buffer_pts
        else:
            zone_bot = swL + wave * p.fibo_top - p.zone_buffer_pts * POINT
            zone_top = swL + wave * p.fibo_bottom + p.zone_buffer_pts * POINT
            touched = any(zone_bot <= highs[i - k] <= zone_top for k in range(3))
            if not touched:
                continue
            sl = (swH - price) / POINT + p.sl_buffer_pts
        if sl > p.max_sl_pts:
            sl = p.max_sl_pts
        out_signal[i] = s
        sl_pts[i] = sl

    return pd.DataFrame({"signal": out_signal, "sl_pts": sl_pts}, index=df_m15.index)
