"""Import HistData M1 CSVs, resample to M15 + H4, cache as parquet.

Run once after dropping HistData yearly folders into
``python/data/raw_histdata/``. Output:

    python/data/XAUUSD_M15.parquet
    python/data/XAUUSD_H4.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw_histdata"
OUT = ROOT / "data"

# HistData EST -> UTC. HistData docs say EST = UTC-5 year-round (no DST).
HISTDATA_TZ_OFFSET_HOURS = 5  # add 5 hours to EST to get UTC


def load_one(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        sep=";",
        header=None,
        names=["time", "open", "high", "low", "close", "volume"],
        dtype={"time": str},
    )
    df["time"] = pd.to_datetime(df["time"], format="%Y%m%d %H%M%S")
    df["time"] = df["time"] + pd.Timedelta(hours=HISTDATA_TZ_OFFSET_HOURS)
    df["time"] = df["time"].dt.tz_localize("UTC")
    return df.set_index("time")[["open", "high", "low", "close", "volume"]]


def main() -> None:
    csvs = sorted(RAW.rglob("DAT_ASCII_XAUUSD_M1_*.csv"))
    if not csvs:
        print(f"No HistData CSVs found in {RAW}")
        sys.exit(1)
    print(f"Found {len(csvs)} M1 file(s):")
    for c in csvs:
        print(f"  - {c.relative_to(ROOT)}")

    print("\nLoading and concatenating...")
    parts = [load_one(p) for p in csvs]
    m1 = pd.concat(parts).sort_index()
    # Deduplicate (rare overlap across year boundaries)
    m1 = m1[~m1.index.duplicated(keep="first")]
    print(f"M1 bars total: {len(m1):,}  "
          f"range: {m1.index[0]} -> {m1.index[-1]}")

    print("\nResampling to M15...")
    m15 = m1.resample("15min", label="left", closed="left").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna(subset=["open"])
    m15["spread"] = 0
    print(f"M15 bars: {len(m15):,}")
    m15_path = OUT / "XAUUSD_M15.parquet"
    m15.to_parquet(m15_path)
    print(f"  -> {m15_path.relative_to(ROOT)}")

    print("\nResampling to H4...")
    h4 = m1.resample("4h", label="left", closed="left").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna(subset=["open"])
    h4["spread"] = 0
    print(f"H4 bars: {len(h4):,}")
    h4_path = OUT / "XAUUSD_H4.parquet"
    h4.to_parquet(h4_path)
    print(f"  -> {h4_path.relative_to(ROOT)}")

    print("\nDone. You can now run scripts/03_benchmark_ma_trend.py")


if __name__ == "__main__":
    main()
