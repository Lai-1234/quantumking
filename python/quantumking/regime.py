"""Market regime detection (ATR_fast vs ATR_slow * 1.2).

Port of CStrategyManager::GetCurrentMarketRegime.
Returns a boolean series: True = high-vol trend regime (trend strategies
allowed), False = low-vol range (reversion strategies allowed).
"""
from __future__ import annotations

import pandas as pd

from .indicators import atr


def regime(df: pd.DataFrame, *, fast: int = 7, slow: int = 50,
           mult: float = 1.2) -> pd.Series:
    a_fast = atr(df, fast)
    a_slow = atr(df, slow)
    return a_fast > a_slow * mult
