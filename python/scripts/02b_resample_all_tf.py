"""Resample the loaded HistData M1 to M1/H1/D1 parquet caches.
(M15 and H4 already exist from 02_import_histdata.py.)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw_histdata"
OUT = ROOT / "data"

HISTDATA_TZ_OFFSET_HOURS = 5


def load_one(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path, sep=";", header=None,
        names=["time", "open", "high", "low", "close", "volume"],
        dtype={"time": str},
    )
    df["time"] = pd.to_datetime(df["time"], format="%Y%m%d %H%M%S")
    df["time"] = df["time"] + pd.Timedelta(hours=HISTDATA_TZ_OFFSET_HOURS)
    df["time"] = df["time"].dt.tz_localize("UTC")
    return df.set_index("time")[["open", "high", "low", "close", "volume"]]


def main() -> None:
    csvs = sorted(RAW.rglob("DAT_ASCII_XAUUSD_M1_*.csv"))
    print(f"Loading {len(csvs)} M1 files...")
    m1 = pd.concat([load_one(p) for p in csvs]).sort_index()
    m1 = m1[~m1.index.duplicated(keep="first")]
    m1["spread"] = 0
    print(f"M1 bars: {len(m1):,}")

    # Save M1 (large file ~30 MB)
    m1.to_parquet(OUT / "XAUUSD_M1.parquet")
    print(f"  -> XAUUSD_M1.parquet")

    for rule, name in [("1h", "H1"), ("1D", "D1")]:
        df = m1.resample(rule, label="left", closed="left").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        }).dropna(subset=["open"])
        df["spread"] = 0
        path = OUT / f"XAUUSD_{name}.parquet"
        df.to_parquet(path)
        print(f"  -> {path.name}  ({len(df):,} bars)")


if __name__ == "__main__":
    main()
