"""Equity-curve correlation matrix across all 10 strategies."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    trades_dir = ROOT / "data" / "trades"
    curves = {}
    for p in sorted(trades_dir.glob("*_equity.parquet")):
        name = p.stem.replace("_equity", "")
        eq = pd.read_parquet(p)["equity"]
        # daily returns
        daily = eq.resample("1D").last().ffill().pct_change().dropna()
        curves[name] = daily
    df = pd.DataFrame(curves)
    corr = df.corr()
    print("Daily-return correlation matrix:\n")
    print(corr.round(2).to_string())
    corr.to_csv(ROOT / "data" / "correlation_matrix.csv")

    # Identify near-duplicates (|corr| > 0.7) - redundant pairs
    pairs = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            c = corr.iloc[i, j]
            if abs(c) > 0.5:
                pairs.append((cols[i], cols[j], round(c, 3)))
    print("\nHigh-correlation pairs (|corr| > 0.5):")
    for p in sorted(pairs, key=lambda x: -abs(x[2])):
        print(f"  {p[0]:25s}  <->  {p[1]:25s}  corr={p[2]}")


if __name__ == "__main__":
    main()
