"""MT5 data feed with parquet cache.

One-time fetch from a running MetaTrader 5 terminal, then reload from
disk on subsequent runs. All downstream code reads via :func:`load`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

TF_MAP_NAME = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "H4": "H4",
    "D1": "D1",
}


def _mt5_tf(tf: str):
    import MetaTrader5 as mt5  # local import so tests don't require it

    return {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }[tf]


@dataclass(frozen=True)
class FetchSpec:
    symbol: str = "XAUUSD"
    timeframe: str = "M15"
    start: datetime = datetime(2022, 1, 1, tzinfo=timezone.utc)
    end: datetime | None = None  # None => now


def _cache_path(spec: FetchSpec) -> Path:
    end = spec.end or datetime.now(timezone.utc)
    name = f"{spec.symbol}_{spec.timeframe}_{spec.start:%Y%m%d}_{end:%Y%m%d}.parquet"
    return DATA_DIR / name


def fetch(spec: FetchSpec) -> pd.DataFrame:
    """Fetch from MT5 terminal and write a parquet cache.

    Requires a running MT5 terminal on this machine.
    """
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise RuntimeError(
            f"MT5 initialize failed: {mt5.last_error()}. "
            "Make sure MetaTrader 5 is running and logged in."
        )

    end = spec.end or datetime.now(timezone.utc)
    rates = mt5.copy_rates_range(
        spec.symbol, _mt5_tf(spec.timeframe), spec.start, end
    )
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No data returned for {spec}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time").rename(
        columns={"tick_volume": "volume", "real_volume": "real_volume"}
    )
    df = df[["open", "high", "low", "close", "volume", "spread"]].astype(
        {"open": "float64", "high": "float64", "low": "float64", "close": "float64"}
    )

    out = _cache_path(spec)
    df.to_parquet(out)
    return df


def load(spec: FetchSpec, *, refresh: bool = False) -> pd.DataFrame:
    """Load from parquet cache; fetch from MT5 if missing or ``refresh``."""
    path = _cache_path(spec)
    if refresh or not path.exists():
        return fetch(spec)
    return pd.read_parquet(path)


def load_csv(path: str | Path, *, timeframe: str = "M15",
             symbol: str = "XAUUSD") -> pd.DataFrame:
    """Load XAUUSD bars from a CSV file (HistData / Dukascopy format).

    Expected columns (auto-detected):
    - HistData generic ASCII : ``DateTime;Open;High;Low;Close;Volume``
      (e.g. ``20230102 170000;1824.18;...``, UTC, no header)
    - Dukascopy CSV          : ``Gmt time,Open,High,Low,Close,Volume`` with
      header; time looks like ``02.01.2023 17:00:00.000``
    - Generic CSV with header containing time/open/high/low/close columns

    Writes a parquet cache for future fast loads.
    """
    path = Path(path)
    raw = pd.read_csv(path, sep=None, engine="python", header=None, nrows=2)
    has_header = any(isinstance(v, str) and not v.replace(".", "").replace(":", "")
                      .replace(" ", "").replace("-", "").isdigit()
                      for v in raw.iloc[0].tolist())

    if has_header:
        df = pd.read_csv(path, sep=None, engine="python")
        df.columns = [c.strip().lower() for c in df.columns]
        time_col = next((c for c in df.columns if "time" in c or "date" in c), df.columns[0])
        df = df.rename(columns={time_col: "time"})
    else:
        df = pd.read_csv(path, sep=None, engine="python", header=None,
                          names=["time", "open", "high", "low", "close", "volume"])

    # Time parsing: try a few common formats
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce",
                                  format="mixed")
    df = df.dropna(subset=["time"]).set_index("time").sort_index()

    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep].astype("float64")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["spread"] = 0  # not in external CSV

    out = DATA_DIR / f"{symbol}_{timeframe}_csv.parquet"
    df.to_parquet(out)
    return df
