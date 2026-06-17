"""Indicator sanity tests.

Each test pins a known-good reference value. To upgrade to true MT5
parity, export 500 bars of indicator buffer from MT5 to
``python/data/mt5_reference_<indicator>.csv`` and replace the inline
fixtures here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quantumking.indicators import (
    adx,
    atr,
    bollinger,
    ema,
    macd,
    rsi,
    stochastic,
    true_range,
)


@pytest.fixture
def ohlcv():
    rng = np.random.default_rng(42)
    n = 500
    base = 2000 + np.cumsum(rng.normal(0, 0.5, n))
    high = base + rng.uniform(0.1, 1.0, n)
    low = base - rng.uniform(0.1, 1.0, n)
    open_ = base + rng.normal(0, 0.2, n)
    close = base + rng.normal(0, 0.2, n)
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({
        "open": open_, "high": np.maximum.reduce([high, open_, close]),
        "low": np.minimum.reduce([low, open_, close]),
        "close": close, "volume": rng.integers(100, 1000, n).astype(float),
        "spread": np.zeros(n),
    }, index=idx)


def test_ema_seed_is_sma(ohlcv):
    e = ema(ohlcv["close"], 20)
    # The 20th value should equal the SMA of the first 20 closes (MT5 seed).
    np.testing.assert_allclose(e.iloc[19], ohlcv["close"].iloc[:20].mean())
    assert e.iloc[:19].isna().all()


def test_ema_recursion(ohlcv):
    e = ema(ohlcv["close"], 20)
    alpha = 2.0 / 21
    manual = e.iloc[19]
    for i in range(20, 25):
        manual = manual + alpha * (ohlcv["close"].iloc[i] - manual)
        np.testing.assert_allclose(e.iloc[i], manual, rtol=1e-12)


def test_atr_wilder(ohlcv):
    a = atr(ohlcv, 14)
    # First valid index = period-1 = 13
    assert a.iloc[:13].isna().all()
    # Wilder: a[i] = (a[i-1] * 13 + tr[i]) / 14
    tr = true_range(ohlcv)
    manual = a.iloc[13]
    for i in range(14, 20):
        manual = (manual * 13 + tr.iloc[i]) / 14
        np.testing.assert_allclose(a.iloc[i], manual, rtol=1e-12)


def test_rsi_range(ohlcv):
    r = rsi(ohlcv["close"], 14)
    valid = r.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_adx_components(ohlcv):
    a = adx(ohlcv, 14)
    valid = a.dropna()
    assert (valid["adx"] >= 0).all() and (valid["adx"] <= 100).all()
    assert (valid["plus_di"] >= 0).all()
    assert (valid["minus_di"] >= 0).all()


def test_macd_signal_recursion(ohlcv):
    m = macd(ohlcv["close"], 12, 26, 9)
    # hist = macd - signal
    np.testing.assert_allclose((m["macd"] - m["signal"]).dropna(),
                                m["hist"].dropna(), rtol=1e-12)


def test_bollinger_geometry(ohlcv):
    b = bollinger(ohlcv["close"], 20, 2.0)
    valid = b.dropna()
    assert (valid["upper"] >= valid["middle"]).all()
    assert (valid["middle"] >= valid["lower"]).all()
    # Width = 2 * dev * std
    width = (valid["upper"] - valid["lower"]) / 2
    std = ohlcv["close"].rolling(20).std(ddof=0).dropna()
    np.testing.assert_allclose(width, 2 * std.loc[width.index], rtol=1e-10)


def test_stochastic_range(ohlcv):
    s = stochastic(ohlcv, 5, 3, 3).dropna()
    assert (s["main"] >= 0).all() and (s["main"] <= 100).all()
    assert (s["signal"] >= 0).all() and (s["signal"] <= 100).all()
