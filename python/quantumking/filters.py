"""Signal-level filters: MTF trend alignment, ATR confirmation, volume gate."""
from __future__ import annotations

import pandas as pd

from .indicators import atr, ema


def mtf_trend_filter(signal: pd.Series, df_higher: pd.DataFrame,
                     fast: int = 50, slow: int = 200) -> pd.Series:
    """Mask signal so longs only fire when higher TF EMA(fast) > EMA(slow)
    and shorts only when EMA(fast) < EMA(slow). Returns filtered signal."""
    bull = ema(df_higher["close"], fast) > ema(df_higher["close"], slow)
    bear = ema(df_higher["close"], fast) < ema(df_higher["close"], slow)
    bull_m = bull.reindex(signal.index, method="ffill").fillna(False)
    bear_m = bear.reindex(signal.index, method="ffill").fillna(False)
    out = signal.copy()
    out[(signal == 1) & ~bull_m] = 0
    out[(signal == -1) & ~bear_m] = 0
    return out


def atr_volatility_filter(signal: pd.Series, df: pd.DataFrame,
                           atr_period: int = 14, min_atr_pct: float = 0.0,
                           max_atr_pct: float = 999.0) -> pd.Series:
    """Block signals when ATR-to-price ratio is outside [min, max] (in %)."""
    a = atr(df, atr_period) / df["close"] * 100
    ok = (a >= min_atr_pct) & (a <= max_atr_pct)
    out = signal.copy()
    out[~ok] = 0
    return out


def apply_filters(sigs: pd.DataFrame, *,
                  df_h1: pd.DataFrame | None = None,
                  df_h4: pd.DataFrame | None = None,
                  atr_min_pct: float = 0.0,
                  atr_max_pct: float = 999.0,
                  atr_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Apply a chain of filters to a signal DataFrame."""
    s = sigs["signal"].copy()
    if df_h1 is not None:
        s = mtf_trend_filter(s, df_h1)
    if df_h4 is not None:
        s = mtf_trend_filter(s, df_h4)
    if atr_df is not None and (atr_min_pct > 0 or atr_max_pct < 999):
        s = atr_volatility_filter(s, atr_df, min_atr_pct=atr_min_pct,
                                    max_atr_pct=atr_max_pct)
    out = sigs.copy()
    out["signal"] = s
    out.loc[s == 0, "sl_pts"] = float("nan")
    return out
