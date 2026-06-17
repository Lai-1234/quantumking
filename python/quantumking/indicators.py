"""Technical indicators matched to MT5's built-in implementations.

Each function returns a pandas Series aligned to the input index. MT5
uses Wilder smoothing for ATR/RSI/ADX and SMA-of-K for stochastic's %D
by default in this codebase — we mirror those exact conventions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------

def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential MA matching MT5's iMA(MODE_EMA).

    MT5 seeds the EMA with an SMA over the first ``period`` non-NaN
    samples, then applies the standard recursion with ``alpha = 2/(period+1)``.
    """
    s = series.astype("float64").to_numpy()
    out = np.full(s.shape, np.nan, dtype="float64")
    if not series.notna().any():
        return pd.Series(out, index=series.index)
    first_valid = series.index.get_loc(series.first_valid_index())
    start = first_valid + period - 1
    if start >= len(s):
        return pd.Series(out, index=series.index)
    seed_window = s[first_valid: first_valid + period]
    if np.isnan(seed_window).any():
        return pd.Series(out, index=series.index)
    alpha = 2.0 / (period + 1.0)
    out[start] = seed_window.mean()
    for i in range(start + 1, len(s)):
        if np.isnan(s[i]):
            out[i] = out[i - 1]
        else:
            out[i] = out[i - 1] + alpha * (s[i] - out[i - 1])
    return pd.Series(out, index=series.index)


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


# ---------------------------------------------------------------------------
# Wilder-smoothed indicators (ATR, RSI, ADX)
# ---------------------------------------------------------------------------

def _wilder(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing: first value = SMA over the first ``period``
    non-NaN samples, then EMA with alpha=1/period.
    """
    s = series.astype("float64").to_numpy()
    out = np.full(s.shape, np.nan, dtype="float64")
    # Locate the first index where we have at least ``period`` non-NaN samples.
    first_valid = int(series.first_valid_index() is not None and
                       series.index.get_loc(series.first_valid_index())) if series.notna().any() else 0
    start = first_valid + period - 1
    if start >= len(s):
        return pd.Series(out, index=series.index)
    seed_window = s[first_valid: first_valid + period]
    if np.isnan(seed_window).any():
        return pd.Series(out, index=series.index)
    out[start] = seed_window.mean()
    for i in range(start + 1, len(s)):
        if np.isnan(s[i]):
            out[i] = out[i - 1]
        else:
            out[i] = (out[i - 1] * (period - 1) + s[i]) / period
    return pd.Series(out, index=series.index)


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return _wilder(true_range(df), period)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = _wilder(gain, period)
    avg_loss = _wilder(loss, period)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Returns columns: plus_di, minus_di, adx."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    tr = true_range(df)
    atr_ = _wilder(tr, period)
    plus_di = 100 * _wilder(plus_dm, period) / atr_
    minus_di = 100 * _wilder(minus_dm, period) / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_ = _wilder(dx, period)
    return pd.DataFrame(
        {"plus_di": plus_di, "minus_di": minus_di, "adx": adx_}, index=df.index
    )


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    macd_line = fast_ema - slow_ema
    sig_line = ema(macd_line, signal)
    hist = macd_line - sig_line
    return pd.DataFrame({"macd": macd_line, "signal": sig_line, "hist": hist})


# ---------------------------------------------------------------------------
# Stochastic (matches MT5 iStochastic with MODE_SMA + STO_LOWHIGH)
# ---------------------------------------------------------------------------

def stochastic(df: pd.DataFrame, k_period: int = 5, d_period: int = 3,
               slowing: int = 3) -> pd.DataFrame:
    """MT5-style stochastic: main = SMA(slowing) of raw %K, signal = SMA(d_period) of main."""
    low_n = df["low"].rolling(k_period, min_periods=k_period).min()
    high_n = df["high"].rolling(k_period, min_periods=k_period).max()
    raw_k = 100 * (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan)
    main = raw_k.rolling(slowing, min_periods=slowing).mean()
    sig = main.rolling(d_period, min_periods=d_period).mean()
    return pd.DataFrame({"main": main, "signal": sig})


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def bollinger(close: pd.Series, period: int = 20, dev: float = 2.0) -> pd.DataFrame:
    mid = sma(close, period)
    std = close.rolling(period, min_periods=period).std(ddof=0)
    return pd.DataFrame(
        {"upper": mid + dev * std, "middle": mid, "lower": mid - dev * std}
    )


# ---------------------------------------------------------------------------
# VWAP (session-anchored, daily reset on UTC midnight)
# ---------------------------------------------------------------------------

def vwap_daily(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].replace(0, np.nan).fillna(1)
    pv = typical * vol
    day = df.index.tz_convert("UTC").normalize() if df.index.tz else df.index.normalize()
    grp = pd.Series(day, index=df.index)
    cum_pv = pv.groupby(grp).cumsum()
    cum_v = vol.groupby(grp).cumsum()
    return cum_pv / cum_v


def vwap_sigma(df: pd.DataFrame, k: float = 3.0) -> pd.DataFrame:
    v = vwap_daily(df)
    diff_sq = ((df["close"] - v) ** 2)
    day = df.index.tz_convert("UTC").normalize() if df.index.tz else df.index.normalize()
    grp = pd.Series(day, index=df.index)
    var = diff_sq.groupby(grp).expanding().mean().reset_index(level=0, drop=True)
    sigma = np.sqrt(var)
    return pd.DataFrame({"vwap": v, "upper": v + k * sigma, "lower": v - k * sigma})


# ---------------------------------------------------------------------------
# Williams Fractals
# ---------------------------------------------------------------------------

def fractals(df: pd.DataFrame) -> pd.DataFrame:
    """Williams fractals: 5-bar high/low pivots. Up fractal at bar i requires
    high[i] > high[i-2..i-1] and high[i] > high[i+1..i+2]. Returns NaN where
    not a fractal, else the high/low value."""
    h = df["high"]
    l = df["low"]
    up = h.where(
        (h > h.shift(2)) & (h > h.shift(1)) & (h > h.shift(-1)) & (h > h.shift(-2))
    )
    dn = l.where(
        (l < l.shift(2)) & (l < l.shift(1)) & (l < l.shift(-1)) & (l < l.shift(-2))
    )
    return pd.DataFrame({"up": up, "down": dn})
