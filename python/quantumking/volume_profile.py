"""Volume Profile indicators (POC, Value Area) from OHLCV.

Since HistData provides tick-count volume (not real volume, no bid/ask
split), we approximate volume-at-price by distributing each bar's volume
across its high-low range, then aggregate per session (daily).

Outputs per bar:
- poc       : Point of Control (price level with most volume) for the
              session-to-date
- vah / val : Value Area High / Low (the 70% volume band)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _session_key(idx: pd.DatetimeIndex) -> pd.Series:
    day = idx.tz_convert("UTC").normalize() if idx.tz else idx.normalize()
    return pd.Series(day, index=idx)


def volume_profile_daily(df: pd.DataFrame, n_bins: int = 50,
                         value_area_pct: float = 0.70) -> pd.DataFrame:
    """Rolling intraday volume profile. For each bar, compute POC/VAH/VAL
    over the session up to (and including) that bar.

    Vectorized per-day with a running histogram. O(bars * bins).
    """
    idx = df.index
    grp = _session_key(idx)
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    vols = df["volume"].replace(0, 1).to_numpy()

    poc = np.full(len(df), np.nan)
    vah = np.full(len(df), np.nan)
    val = np.full(len(df), np.nan)

    # Process each day independently
    day_arr = grp.to_numpy()
    start = 0
    n = len(df)
    while start < n:
        end = start
        while end < n and day_arr[end] == day_arr[start]:
            end += 1
        # session [start, end)
        sess_hi = highs[start:end]
        sess_lo = lows[start:end]
        sess_vol = vols[start:end]
        day_low = sess_lo.min()
        day_high = sess_hi.max()
        if day_high <= day_low:
            poc[start:end] = closes[start:end]
            start = end
            continue
        bins = np.linspace(day_low, day_high, n_bins + 1)
        centers = (bins[:-1] + bins[1:]) / 2
        hist = np.zeros(n_bins)
        for i in range(start, end):
            # distribute this bar's volume uniformly across its range bins
            lo_b = np.searchsorted(bins, lows[i], side="right") - 1
            hi_b = np.searchsorted(bins, highs[i], side="right") - 1
            lo_b = max(0, min(lo_b, n_bins - 1))
            hi_b = max(0, min(hi_b, n_bins - 1))
            span = hi_b - lo_b + 1
            hist[lo_b:hi_b + 1] += vols[i] / span
            # POC/VA up to this bar
            poc_bin = int(np.argmax(hist))
            poc[i] = centers[poc_bin]
            # Value area: expand from POC until value_area_pct of volume
            total = hist.sum()
            target = total * value_area_pct
            lo_i = hi_i = poc_bin
            acc = hist[poc_bin]
            while acc < target and (lo_i > 0 or hi_i < n_bins - 1):
                left = hist[lo_i - 1] if lo_i > 0 else -1
                right = hist[hi_i + 1] if hi_i < n_bins - 1 else -1
                if right >= left:
                    hi_i += 1
                    acc += hist[hi_i]
                else:
                    lo_i -= 1
                    acc += hist[lo_i]
            val[i] = centers[lo_i]
            vah[i] = centers[hi_i]
        start = end

    return pd.DataFrame({"poc": poc, "vah": vah, "val": val}, index=idx)


def anchored_vwap(df: pd.DataFrame, anchor: str = "D") -> pd.Series:
    """Anchored VWAP resetting per period ('D' daily, 'W' weekly)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].replace(0, 1)
    if anchor == "D":
        key = _session_key(df.index)
    elif anchor == "W":
        iso = df.index.isocalendar()
        key = pd.Series(iso.year.astype(str) + "-" + iso.week.astype(str), index=df.index)
    else:
        key = _session_key(df.index)
    cum_pv = (typical * vol).groupby(key).cumsum()
    cum_v = vol.groupby(key).cumsum()
    return cum_pv / cum_v


def vwap_bands(df: pd.DataFrame, k_list=(1.0, 2.0, 3.0), anchor: str = "D") -> pd.DataFrame:
    """VWAP + volume-weighted standard-deviation bands at multiple k."""
    v = anchored_vwap(df, anchor)
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].replace(0, 1)
    key = _session_key(df.index)
    # volume-weighted variance to-date
    dev_sq = ((typical - v) ** 2) * vol
    cum_dev = dev_sq.groupby(key).cumsum()
    cum_v = vol.groupby(key).cumsum()
    sigma = np.sqrt(cum_dev / cum_v)
    out = {"vwap": v, "sigma": sigma}
    for k in k_list:
        out[f"upper_{k}"] = v + k * sigma
        out[f"lower_{k}"] = v - k * sigma
    return pd.DataFrame(out)
